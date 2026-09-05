# I AM — Post-Refactor Defect Fixes (Round 2)

Read this whole file before editing anything. These are defects found by reviewing `app.py`, `tts_engine.py`, `render_worker.py`, `ndi_streamer.py`, `visualizer.py`, and `config.py` after the Phase 1–7 refactor. Work through the items **in order**. Commit after each item with the app still runnable. Do not refactor beyond what each item asks.

Prerequisite: `FIX_ndi_audio_breakup.md` must be complete and all four of its acceptance checks passing before you start here. If it is not, do that first.

Rules that apply to every item:
- Do not add on-screen text for the AI's spoken answer. The subtitle card shows only the pinned chat question and the motto. This is intentional product design.
- Do not touch `ai_brain.py` except where an item explicitly names it.
- When you are unsure how something is used, `grep` for every caller before changing a signature.
- Run `python app.py` in simulation mode (no API keys) after every item and confirm it starts, renders, accepts console chat, and speaks.

---

## Item 1 — One processed audio stream for both NDI and local monitor

**Problem.** In `app.py::_execute_ai_turn`, the code does:
```python
self.tts.push_audio(s_audio)
if hasattr(self.visualizer, "push_audio_samples"):
    self.visualizer.push_audio_samples(s_audio)
```
`push_audio` fades the head/tail and prepends inter-sentence gap silence to its own copy. The raw, unprocessed `s_audio` is what goes into the shared-memory ring for NDI. NDI and the local monitor therefore receive different samples. When sentence chunking is restored, NDI will click at every sentence boundary and drift out of sync with the local monitor by `inter_sentence_gap_sec` per sentence.

**Fix.**
1. In `tts_engine.py`, change `push_audio` to `push_audio(self, audio) -> np.ndarray` and return the fully processed array (after fades and gap prepend). Do not change any other behaviour.
2. In `tts_engine.py`, add an optional sink: `self.ndi_sink: Optional[Callable[[np.ndarray], None]] = None`. At the end of `push_audio`, if `self.ndi_sink` is set, call `self.ndi_sink(processed)`.
3. In `app.py`, after the visualizer is constructed, set `self.tts.ndi_sink = self.visualizer.push_audio_samples` when the visualizer is a `VisualizerProxy`; otherwise leave it `None`.
4. Delete every direct call to `self.visualizer.push_audio_samples(...)` in `app.py` (there are two: cached-greeting path and normal path). `grep -n push_audio_samples app.py` must return nothing.
5. Make `clear_audio_buffer()` in `TTSEngine` also call a new optional `self.ndi_clear_sink` (set to `self.visualizer.clear_audio_buffer` in proxy mode) so both streams are flushed together. Remove the separate `self.visualizer.clear_audio_buffer()` calls in `app.py`.

**Acceptance.** Add `tests/test_audio_sink.py`: create a `TTSEngine`, attach a sink that appends to a list, push two 1 s chunks, and assert the concatenated sink output equals the concatenated `_audio_buffer_local` sample-for-sample (`np.array_equal`).

---

## Item 2 — Remove the lock-held `np.vstack` that stalls the real-time audio callback

**Problem.** `TTSEngine.push_audio` holds `_buffer_lock` while running `np.vstack` on the whole buffer (a 20 s answer is ~7.7 MB copied twice). `pop_local_audio` is called from the PortAudio real-time callback and needs the same lock. While the copy runs, the audio callback blocks and the local output underruns.

**Fix.** Replace both `_audio_buffer_ndi` and `_audio_buffer_local` with `collections.deque` of `(chunk: np.ndarray, offset: int)` items:
- `push_audio`: do all processing (fades, gap prepend, dtype conversion) **outside** the lock, then inside the lock only `deque.append((processed, 0))` and update counters. Lock hold time must be microseconds.
- `pop_local_audio` / `pop_audio_packet`: inside the lock, fill the output array by walking the deque head, advancing `offset`, and popping fully-consumed chunks. Return zeros for any shortfall. Keep every existing side effect (`is_speaking`, `_last_local_pop_time`, `_last_ndi_pop_time`, analysis window, metrics).
- `remaining_speech_duration`, `clear_audio_buffer`, and `wait_until_speech_completed` must be updated to compute buffered length as `sum(len(c) - off for c, off in deque)`.
- Keep the `ndi_buffer_enabled` flag from `FIX_ndi_audio_breakup.md` item D.4: when `False`, do not append to the NDI deque at all.

**Acceptance.** Add `tests/test_tts_buffer.py`: push a 5 s chunk, then in a thread call `pop_local_audio(480)` 500 times while the main thread pushes another 5 s chunk; assert no pop call took longer than 2 ms (`time.perf_counter` around the call) and the total popped audio equals the pushed audio in order.

---

## Item 3 — Control commands must never be silently dropped

**Problem.** `VisualizerProxy._send_cmd` uses `put_nowait` on a `maxsize=1000` queue and swallows the exception. `sync_state` is called every 50 ms and each call pickles up to 50 chat dicts. If the render worker stalls for a few seconds the queue fills and subsequent `SET_MOOD`, `FADE_OUT_QUESTION`, `TRIGGER_CELEBRATION` commands are thrown away, so the visuals silently desync from the audio.

**Fix.**
1. Split commands into two queues in `VisualizerProxy`: `ctrl_queue` (`maxsize=256`) for `SET_MOOD`, `SET_SUBTITLE`, `FADE_OUT_FOR_TURN`, `FADE_OUT_QUESTION`, `CLEAR_SUBTITLE`, `TRIGGER_CELEBRATION`, `TRIGGER_PROMO`, `STOP`; and `state_queue` (`maxsize=4`) for `SYNC_STATE`.
2. `ctrl_queue.put(item, timeout=0.5)`; on `queue.Full`, log at ERROR with the command name. Never drop silently.
3. For `state_queue`: compute a cheap fingerprint of the state dict before sending — `(len(chat_messages), last_message_id_or_hash, pinned_id, engagement_mode, concurrent_viewers, is_stream_live, obs_connected)`. Only send when the fingerprint differs from the last one sent. On `queue.Full`, drain one stale item with `get_nowait` and retry once (latest state wins).
4. In `render_worker_main`, drain `ctrl_queue` fully each frame (bounded to 64 items per frame to protect frame time, log if the bound is hit), then take **only the newest** item from `state_queue` and discard older ones.
5. Pass both queues into `render_worker_main`; update `start()`.

**Acceptance.** Stall the worker artificially (`time.sleep(3)` inserted behind an env flag `IAM_TEST_WORKER_STALL=1` in the render loop) while sending 20 `SET_MOOD` commands from the main process. All 20 must be applied in order after the stall; the ERROR path must never fire in that test. Remove the env flag hook after testing or leave it clearly guarded.

---

## Item 4 — Single owner for subtitle and pinned-question state

**Problem.** `set_subtitle()` sends a `SET_SUBTITLE` command that calls `visualizer.set_subtitle()` (which starts a fade animation), **and** the 20 Hz `SYNC_STATE` overwrites `state["ai_subtitle"]`, which `render_frame` also receives. The same is true for `pinned_chat_message`. Two writers race and you can get fade-in/fade-out fights on the question card.

**Fix.**
1. Remove `ai_subtitle` from `sync_state()` and from the `SYNC_STATE` dict. The only way subtitle/motto text changes is via `SET_SUBTITLE` / `CLEAR_SUBTITLE` commands.
2. Add explicit `SET_PINNED` and `CLEAR_PINNED` commands; `VisualizerProxy.set_pinned(msg)` and `clear_pinned()`; wire them where `app.py` currently sets `self.current_pinned_chat`. Remove `pinned_chat_message` from `SYNC_STATE`.
3. In `render_worker_main`, `render_frame` must take `ai_subtitle` and `pinned_chat_message` from the visualizer's own state (set by the commands), not from `state[...]`. If `Visualizer.render_frame` requires those as parameters, pass `visualizer.subtitle_target_text` / `visualizer.pinned_message` (or whatever the internal attributes are named — read `visualizer.py` to find them).
4. `SYNC_STATE` is now only: `chat_messages`, `obs_connected`, `engagement_mode`, `concurrent_viewers`, `is_stream_live`.

**Acceptance.** Ask a console question, watch the pinned card: it fades in once, holds, fades out once. Add a DEBUG log in `Visualizer.set_subtitle` and confirm it fires exactly once per turn.

---

## Item 5 — Shared memory creation must fail loudly, and must work on Windows

**Problem.** `AudioMetricsSharedMemory.__init__` (create path) handles `FileExistsError` by comparing `existing.size != AUDIO_SHM_SIZE`. `AUDIO_SHM_SIZE` is not page-aligned and Windows reports the mapped size rounded up, so the comparison always fails, `unlink()` is a no-op on Windows, the second `create=True` raises again, and `self.shm` becomes `None`. Every subsequent `write_audio_samples` returns early and the NDI feed is silent, with only a WARNING logged once at startup.

**Fix.**
1. Round the segment size: `AUDIO_SHM_SIZE = ((AUDIO_METRICS_HEADER_SIZE + AUDIO_DATA_BYTE_SIZE + 4095) // 4096) * 4096`.
2. In the stale-segment branch, treat `existing.size >= AUDIO_SHM_SIZE` as acceptable and reuse it (zero it first).
3. Give the segment a per-run name: `f"iam_audio_shm_{os.getpid()}"` created by the proxy and passed to the worker. That eliminates the stale-segment case entirely. Keep `AUDIO_SHM_NAME` only as a prefix.
4. If `self.shm` is `None` after `create=True`, **raise** `RuntimeError` — the app cannot function without it. In the worker (`create=False`), retry attaching 10 times over 2 s before raising.
5. Remove `RING_BUFFER_FRAMES = 48000 * 120`; use `48000 * 30` (already specified in the audio-breakup fix; confirm it landed).

**Acceptance.** Start the app twice concurrently in simulation mode; both must run with independent NDI names (`NDI_STREAM_NAME` suffixed with pid when a second instance is detected, or fail with a clear error — pick one and document it) and neither may silently lose audio.

---

## Item 6 — Worker restart must restore visual state and report NDI reconnection

**Problem.** `check_and_restart_if_dead` spawns a fresh `Visualizer` but never resends mood, subtitle, or pinned question. A crashed worker also never called `ndi.close()`, so the NDI runtime may register the restarted sender under a suffixed name (`AI_COHOST_FEED (2)`) and OBS will not auto-reconnect.

**Fix.**
1. `VisualizerProxy` already tracks `current_mood` and `ai_text_target`; add `current_pinned`. After a successful restart in `check_and_restart_if_dead`, replay `SET_MOOD`, `SET_SUBTITLE` (or `CLEAR_SUBTITLE`), and `SET_PINNED`/`CLEAR_PINNED`.
2. Call `check_and_restart_if_dead()` from the 20 Hz loop in `video_broadcast_task`, not only from `_send_cmd`, so a dead worker is noticed within 50 ms rather than at the next command.
3. In `render_worker_main`, after `ndi.open()`, log `ndi.stream_name` and, 3 s later, `ndi.get_num_connections()` at INFO. On restart this shows whether OBS re-attached.
4. In `NDIStreamer.open()`, before creating the sender, if a previous instance of this process crashed (the proxy passes `restart_count > 0` as an arg), sleep 1.5 s to give the NDI runtime time to drop the dead source before re-registering the same name.

**Acceptance.** Kill the worker with Task Manager while speaking. Within 2 s a new worker is up, the mood colour matches the mood in the log, and OBS shows the same source name without a "(2)" suffix (or the log clearly reports that it did not reconnect).

---

## Item 7 — Fix process/thread priorities

**Problem.** `render_worker_main` raises the whole render process to `ABOVE_NORMAL_PRIORITY_CLASS`. The main process (Gemini streaming, TTS, PortAudio callback, chat handling) stays at normal. On a loaded machine this starves the conversational side to keep the visuals smooth — the opposite of what the product needs.

**Fix.**
1. Remove the `SetPriorityClass` call from `render_worker_main`. The render process runs at normal priority.
2. In the NDI audio pump thread (added by `FIX_ndi_audio_breakup.md`), set thread priority to `THREAD_PRIORITY_TIME_CRITICAL` (Windows, via `ctypes.windll.kernel32.SetThreadPriority(ctypes.windll.kernel32.GetCurrentThread(), 15)`), wrapped in try/except. This is the only elevated thread in the worker.
3. Leave the PortAudio callback alone; PortAudio already runs it on an MMCSS thread.
4. Optionally, on Windows, call `SetPriorityClass(ABOVE_NORMAL_PRIORITY_CLASS)` on the **main** process in `main()` — only if `IAM_ELEVATE_MAIN=1` is set in `.env`, default off.

**Acceptance.** Task Manager → Details → Base priority: main process Normal (or Above normal if the flag is on), render worker Normal. Speech remains glitch-free with the render worker at Normal.

---

## Item 8 — `wait_until_speech_completed` correctness in proxy mode

**Problem.** With the proxy active, nothing pops `_audio_buffer_ndi` in the main process, so `ndi_active` is always false and completion is detected only via the local buffer. If `local_audio_enabled=false`, it degrades to an elapsed-time guess based on `last_synthesized_duration`, which is only the most recent chunk once sentence chunking returns.

**Fix.** Implement item D.4 from `FIX_ndi_audio_breakup.md` if not already done, then:
- In proxy mode with local audio enabled: done = local deque empty **and** `_utterance_open == False`.
- In proxy mode with local audio disabled: done = `(time.time() - _first_push_time) >= _utterance_total_samples / sample_rate` **and** `_utterance_open == False`.
- Add a hard timeout of `_utterance_total_samples / sample_rate + 3.0` after which the method logs a WARNING, clears buffers, and returns.
- `_first_push_time` and `_utterance_total_samples` must be reset in `begin_utterance()`, not in `push_audio`.

**Acceptance.** Extend `tests/test_tts_buffer.py`: with no pop thread running and `local_audio_enabled=False`, `begin_utterance(); push(1s); push(1s); push(1s); end_utterance(); await wait_until_speech_completed()` returns after ≥ 3.0 s and < 3.5 s wall time.

---

## Item 9 — Housekeeping that was skipped in the first pass

Do these last, each as a separate commit.

1. **Single logging setup.** `render_worker_main` calls `logging.basicConfig` again. Create `logging_setup.py` with `configure_logging(process_tag: str)`; call it once from `main()` in `app.py` with `"MAIN"` and once at the top of `render_worker_main` with `"RENDER"`. Remove every other `basicConfig` in the repo (`grep -rn basicConfig` must show only `logging_setup.py`).
2. **Bounded command drain.** In `render_worker_main`, the `while not cmd_queue.empty()` loop is unbounded. Item 3 replaces it with a bounded drain; confirm the bound (64) is enforced and logged when hit.
3. **Config `getattr` cleanup.** `grep -rn 'getattr(self.cfg' *.py` currently returns dozens of hits. Every key must exist as a dataclass field in `config.py` with its default; replace `getattr(self.cfg, "key", default)` with `self.cfg.key`. Generate `docs/config_reference.md` listing each key, default, env var, and the files that read it. Delete `tts_engine` (env `TTS_ENGINE`) in favour of `tts_backend`, and delete `gemini_thinking_budget` if nothing reads it.
4. **Verify Phase 3 landed.** Confirm `should_trigger_response` no longer contains `w`, `l`, `gg`, `lol`, `real`, `game`, `play`, `win`, `lose` as bare keywords, that `ai`/`bot`/`god` are whole-word and address-position matched, that viewer-count sampling exists, and that `_classify_prompt_depth` uses the ≥ 8-word + reduced-term rule. If any of this is missing, implement it per the original plan and add the tests listed there (`tests/test_triggers.py`).
5. **Restore sentence pipelining.** Only after Items 1, 2, and 8 are green: reinstate the producer/consumer in `_execute_ai_turn` per Phase 2.4 of the original refactor plan. The whole-utterance path that replaced it was a workaround for the NDI breakup, which is now fixed at the transport layer. Keep the cached-greeting single-chunk path.

---

## Final report

Write `docs/CHANGELOG_round2.md` with, per item: what changed, which tests were added, and measured numbers where an acceptance test asks for them (max pop latency, max audio-pump interval, restart time). If you skipped or altered any item, say so and why. Do not mark an item done if its acceptance test has not been run.
