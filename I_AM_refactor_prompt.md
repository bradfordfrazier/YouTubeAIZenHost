# I AM Co-Host — Refactor & Performance Implementation Plan

You are working on an all-local AI livestream host ("I AM") built in Python. The core files are `app.py` (asyncio orchestrator, ~2,500 lines), `ai_brain.py` (Gemini context builder + streaming), and `visualizer.py` (pygame 1080p60 renderer, NDI output). `config.py` and `tts_engine.py` have been reviewed and the plan below reflects them. Supporting modules you must still read before changing anything: `cast_engine.py`, `greeting_cache.py`, `reflection_cache.py`, `memory_manager.py`, `chatter_db.py`, `session_log.py`, `ndi_streamer.py`.

Read all of these fully first. Then implement the phases below **in order**, committing after each phase with the app still runnable. Do not skip ahead. Do not "improve" things outside the scope of each phase.

---

## Product intent (do not violate)

- The show is a single AI host performing for a YouTube live audience, like a stand-up comedian. Attention must stay on the animated avatar (the central star/core) while it speaks.
- **The AI's spoken text is intentionally NOT displayed on screen.** The subtitle card shows only (a) the pinned chat question currently being answered and (b) the motto phrase when idle. Do not add captions, typewriter answer text, word-by-word chunks, or any rendering of the AI's reply. Any existing code paths that could display the AI's answer text should remain disabled/removed; do not reintroduce them.
- The human host / co-host interaction layer (mic transcript, host questions, "Recent Host & Guest Dialogue") is being **removed**, not just disabled. The product is an AI host, not an AI co-host.
- Chat-driven responses, superchat/membership celebrations, new-chatter greetings, spontaneous reflections, chat-encouragement CTAs, the synthetic cast, ECO/STANDBY token gating, and the OBS stream-state monitor all stay.

---

## Phase 1 — Remove the human host / co-host layer

Goal: consolidate on a single AI host and free CPU, memory, and event-loop time.

### 1.1 `app.py`
- Delete `transcript_file_task` and all state it feeds: `last_transcript_text`, `last_file_position`, `current_host_transcript`, and any `.env`/config keys that exist only for it (e.g. transcript file path, host mic device). Remove the task from `start()`.
- Remove the `"host"` tier from the priority map in `_trigger_ai_turn`. Renumber remaining tiers so `superchat` is priority 1. Update the tier comment block to match.
- Remove every call to `self.brain.add_transcript(...)`.
- Remove the `"Host" in trigger_str` branch in `_generate_simulated_stream` (in `ai_brain.py`, see 1.2).
- Keep `console_chat_task` — it is the local testing path — but it should inject messages as *viewer* chat only. Remove any console command that simulates host speech.
- Keep `obs_monitor_task` for stream live/scene state (STANDBY gating depends on it). Remove any OBS FX that were only triggered by host speech; keep FX triggered by AI turns, celebrations, and mood changes.
- Keep `_wake_up_and_trigger_comment`, `_on_viewer_count_update`, `_update_engagement_state`, `youtube_chat_task`, `youtube_viewer_poller_task`, `cast_scheduler_task`, `idle_reflection_monitor_task`, `comment_queue_scheduler_task`, `video_broadcast_task`, audio pump, and observability.

### 1.2 `ai_brain.py`
- Delete `transcript_buffer`, `add_transcript`, `last_speech_time`.
- In `_build_context_prompt`, remove the "Recent Host & Guest Dialogue" section entirely. Remove references to `host_streamer_handle` / `host_streamer_name` as a *second persona*. The channel handle and channel display name remain (the AI *is* the channel). Simplify the "CRITICAL CHANNEL & ADDRESSING RULES" block accordingly: the AI's handle is the channel handle; it never addresses itself; it always addresses the viewer it is replying to.
- In `should_trigger_response`: remove the `is_host` parameter and the entire `host_question` branch. All callers become chat-only. Remove host-name/host-handle entries from `direct_triggers`, `exempt_names`, and `host_entities` in `is_member_reply` **except** the channel handle(s), cohost name, and generic audience terms.
- Remove the `"Host"` branch of `_generate_simulated_stream`. Remove `self.streamer_name` unless it is still used as the channel display name; if so rename it `channel_display_name` for clarity.
- Remove instruction text in the special-mode prompt blocks that mentions the streamer as a separate person (e.g. "with {self.streamer_name}", "roast {host_name}"). The chat-encouragement CTA should invite viewers to ask the AI questions or "roast the universe," not roast a human host.

### 1.3 `visualizer.py`
- Delete `_draw_host_transcript_card` and the `host_transcript` parameter of `render_frame`. Remove `host_connected` from `render_frame` and `_draw_top_header` (if the header is kept, show only OBS/live status, viewers, and mode).
- Remove any fonts, surfaces, or layout constants that existed only for the host card. Re-check the 16:9 and 9:16 layouts so nothing now sits in an empty gap; if the host card occupied real estate, reflow the chat panel or leave the area clean — do not fill it with new text elements.

### 1.4 `config.py` / `.env.example`
- Remove these host-only keys and every reader of them: `host_streamer_name` (`HOST_STREAMER_NAME`), `transcript_file_path` (`TRANSCRIPT_FILE_PATH`), `obs_transcript_source_name` (`OBS_TRANSCRIPT_SOURCE`), `show_host_transcript_card` (`SHOW_HOST_TRANSCRIPT_CARD`).
- `host_streamer_handle` and `youtube_channel_handle` both default to `@MassiveGodComplex` — they are the same identity. Keep only `youtube_channel_handle`; in `__post_init__`, drop `host_streamer_handle` from the `channel_handles` normalisation loop. Add a one-time startup warning if `HOST_STREAMER_HANDLE` is still set in `.env` and it differs from `YOUTUBE_CHANNEL_HANDLE`.
- Rename `ai_cohost_name` → `ai_host_name` (env `AI_HOST_NAME`, still accepting `AI_COHOST_NAME` with a deprecation warning). Update all readers (`ai_brain.py`, `visualizer.py`, `app.py`).
- Rewrite the default `ai_system_prompt` so it describes a solo host, not a co-host alongside a streamer. Keep the persona voice exactly as it is; only remove references to a second human host.
- General deprecation handling: if any removed env key is present, log one warning at startup and ignore it.

### Phase 1 acceptance
- `python app.py` starts with no API keys, renders at 60 FPS, accepts console chat, and responds in simulation mode.
- `grep -rn "transcript\|host_streamer\|is_host" *.py` returns only the channel-identity uses you intentionally kept (list them in the commit message).
- No `AttributeError` for removed config keys anywhere in the codebase (run every task at least once).

---

## Phase 2 — Fix the mood → voice bug, then sentence-pipeline the TTS

### 2.0 Bug fix first: mood exaggeration never reaches the voice
`TTSEngine.synthesize()` reads the mood by regex-matching `[MOOD: x]` inside the text it receives. But `ai_brain.py` strips the mood tag before emitting `full_text`, and `app.py` passes that stripped text to `synthesize()`. Result: `active_mood` is always `"neutral"` and the entire `tts_mood_exaggeration_map` in `config.py` (hyped 0.8, deadpan 0.3, savage 0.85, …) is dead code. Every line is delivered at exaggeration 0.5. For a comedy persona this is the single most audible defect in the product.

- Change the signature to `synthesize(text: str, mood: str = "neutral") -> np.ndarray` and derive `exaggeration` from the `mood` argument. Keep the regex path only as a fallback when `mood` is not supplied.
- Pass `active_mood` from `_execute_ai_turn` (and from `greeting_cache.py` / `reflection_cache.py` pre-synthesis paths — read them and fix both).
- Log the resolved exaggeration on every synthesis call.
- Acceptance: a `[MOOD: deadpan]` and a `[MOOD: hyped]` answer produce audibly different deliveries, and the log shows 0.3 vs 0.8.

### 2.1 Why chunking is feasible here
The Chatterbox backend is a **stateless HTTP POST** to a LAN GPU server (`POST {tts_server_url}/synthesize`, one WAV back per request), and the Edge-TTS fallback is likewise per-request. There is no model to reload and no session state, so per-sentence requests are safe. The buffer layer (`push_audio` → `_audio_buffer_ndi` / `_audio_buffer_local`, popped 800 samples per frame) already appends, so multiple pushes per turn work mechanically. Three things do **not** currently support chunking and must be fixed in 2.2:
1. `wait_until_speech_completed()` uses `last_synthesized_duration`, which `push_audio` **overwrites** on every push — with chunks it would only wait for the last sentence.
2. `push_audio`'s comment says "seamless crossfade stitching" but the code is a bare `np.vstack`; chunk boundaries will click if the Chatterbox WAV has a non-zero first/last sample.
3. `synthesize()` runs one request at a time; the app must be able to synthesize sentence N+1 while sentence N plays.

### 2.2 `tts_engine.py`
- Add explicit utterance bookkeeping: `begin_utterance()` resets `_utterance_total_samples = 0` and `_utterance_open = True`; `push_audio()` adds `len(audio)` to the total; `end_utterance()` sets `_utterance_open = False`. `wait_until_speech_completed()` waits until `end_utterance()` has been called **and** both buffers are drained (or, when no backend is popping, until `_utterance_total_samples / sample_rate` has elapsed since the first push). Remove the dependence on `last_synthesized_duration` for this purpose; keep the attribute for logging only.
- In `push_audio`, before appending: apply a 5 ms linear fade-in to the chunk head and 5 ms fade-out to the chunk tail (skip the fade-in if the buffer is currently empty and this is the first chunk — the speech onset should stay crisp). Then append `inter_sentence_gap_sec` of silence (new config key, default 0.15 s) **after** every chunk except the last; `end_utterance()` is what tells `push_audio` the previous chunk was the last, so implement the gap as "prepend gap silence to chunk N when N > 1" rather than appending to chunk N-1.
- `synthesize()` is already `async` and does the decode in `asyncio.to_thread`; add `max_concurrent_synth` (config, default 2) and wrap the Chatterbox request in an `asyncio.Semaphore` so the app can keep one request in flight while another plays without flooding the GPU server. Do not exceed 2 unless the server is confirmed to batch.
- Chatterbox timeout is `len(text) * 0.08` clamped to 5–30 s. Per-sentence requests will almost always hit the 5 s floor; that is fine, but lower `tts_request_timeout_floor` default to 4.0 and make sure a timeout on sentence N does not abort the turn — fall through to Edge-TTS for that sentence only, log it, and continue.
- `clear_audio_buffer()` must also call `end_utterance()` so a cancelled turn cannot leave `wait_until_speech_completed()` hanging.
- Remove the dead `queue_speech()` method if nothing calls it after the refactor.

### 2.3 `ai_brain.py`
- `generate_response_stream` already yields `{"type": "sentence", "text": ..., "mood": ...}` events. Audit them so that:
  - The first `sentence` event is emitted as soon as a terminal `.`, `!`, or `?` is seen **after** the mood tag has been stripped, never before the mood tag is resolved.
  - Sentence splitting does not break on decimals, ellipses, `@handle.` at the end of a mention, or abbreviations. Use a small guard (minimum 3 words, at least 12 chars) before emitting a sentence; otherwise hold it and merge with the next.
  - The `complete` event still carries the full cleaned text for logging and memory.
- Replace the "discard whole reply if it doesn't end in terminal punctuation" behaviour with a **repair** step: if the final fragment is ≥ 3 words, append a period and emit it as the last sentence; only fall back to the simulated stream if the total valid text is empty. Log at WARNING when repair happens.
- Make the legacy-SDK branch emit `sentence` events too (it currently only emits `token`), or drop legacy-SDK support entirely if `google-genai` is pinned in `requirements.txt`. Prefer dropping it.

### 2.4 `app.py` — `_execute_ai_turn`
- Rework the generation block into a producer/consumer:
  - Producer: iterate `generate_response_stream`; on `mood` → set visualizer mood; on `sentence` → put text on an `asyncio.Queue`; on `complete` → put a sentinel.
  - Consumer: pull sentences, `await tts.synthesize(text, mood)`, then `tts.push_audio(...)`. Run synthesis of sentence N+1 concurrently with playback of sentence N (the semaphore in 2.2 bounds this).
  - Call `tts.begin_utterance()` before the first push and `tts.end_utterance()` after the sentinel is consumed and the last chunk pushed.
- The **question display hold** must still be honoured: do not push the first audio chunk until `min_time_before_fade_out` has elapsed and the question fade-out (if any) has completed. Synthesis of sentence 1 may (and should) run during the hold; only the push waits.
- `wait_until_speech_completed()` is awaited after `end_utterance()`.
- The cached-greeting fast path (`cached_g.audio`) becomes `begin_utterance(); push_audio(audio); end_utterance()` and must still work.
- Record `record_completed_turn`, session log, and chatter DB using the full text from the `complete` event, unchanged. Note the session log currently recomputes `exaggeration` from the mood map for logging — after 2.0 this value is finally the one actually used.
- Add timing logs at INFO on every turn: `TTFT` (first token), `TTFS` (first sentence), `TTFA` (first audio pushed), and total turn time.

### Phase 2 acceptance
- With a real Gemini key and a 2-sentence answer, the INFO log shows TTFA well below total turn time.
- No audible clicks between sentences at 48 kHz: render a 3-sentence answer to WAV via a test harness that calls `push_audio` and drains with `pop_audio_packet`, then assert the first and last 5 samples of each chunk region are within ±0.01 after the fades.
- `wait_until_speech_completed()` returns only after the **last** chunk has drained, verified by a test that pushes three 1 s chunks and measures ≥ 3.3 s wall time with the pop loop running.
- Visualizer RMS/spectrum reacts continuously across the chunk boundary (the star does not "drop" between sentences).
- Simulation mode still works and is also chunked.

---

## Phase 3 — Trigger and cost hygiene

### 3.1 Tighten `should_trigger_response` (`ai_brain.py`)
- Remove single-letter and ultra-common tokens from `chat_keywords`: `w`, `l`, `gg`, `lol`, `lmao`, `real`, `fake`, `game`, `play`, `win`, `lose`. Keep question words and explicit asks (`roast`, `explain`, `opinion`, `thoughts`, `tell`, `think`).
- Remove bare `"ai"`, `"bot"`, and `"god"` from `direct_triggers` as substring matches — they match "again," "robot," "godzilla." Match them as whole words (`\b...\b`) and only when the message is addressed to the AI (starts with the word, or is `@`-prefixed, or is followed by a comma/colon/question).
- Add a config-driven **sampling** layer for the fallthrough `live_chat_interaction` case: when concurrent viewers exceed `chat_sampling_viewer_threshold` (default 25), respond to a random `chat_sampling_probability` (default 0.35) of non-question, non-mention messages. Questions, mentions, superchats, and new-chatter greetings are never sampled out.
- Precompute the `exempt_names` and `host_entities` sets once in `__init__` (and rebuild only in `update_channel_identity`) instead of rebuilding them on every message.

### 3.2 Deep-vs-fast classifier (`_classify_prompt_depth`)
- Replace the current keyword list with a stricter rule: classify as DEEP only if **both** (a) the message is ≥ 8 words and (b) it contains a term from a reduced list: `death, die, dying, grief, loss, meaning, purpose, consciousness, free will, soul, suffering, enlightenment, who am i, what am i, impermanence, forgive`. Drop `mind, real, fear, nothing, truth, universe, reality, ego, exist, god, quantum, void, observer, destiny` from the deep list — they fire on casual banter.
- Everything else, including all special-mode events, is FAST.
- Log the classification decision and the matched term on each turn.

### 3.3 Queue implementation (`app.py`)
- Replace the list-based `comment_queue` (re-sorted per push) with `heapq` keyed on `(priority, created_at, seq)`. Keep TTL pruning. Preserve FIFO within the same priority.

### Phase 3 acceptance
- Unit tests (pytest, add `tests/test_triggers.py`): "again lol" → no trigger; "@IAM why do we dream?" → direct_mention; "I am scared of dying and losing everyone I love, what's the point" → DEEP; "god that game was trash" → FAST and no trigger; superchat → always triggers regardless of sampling.
- Queue test: superchat enqueued after 3 cast events is dequeued first.

---

## Phase 4 — Synthetic cast transparency

Goal: keep the cast as an openly fictional ensemble and remove any perception of fake engagement.

- `visualizer.py` `_draw_live_chat_card`: cast messages must carry a small, always-visible badge (text `CAST` or a 🎭 glyph, in the existing purple accent) next to the author name, both in the scrolling feed and in the pinned-question box. Do not rely on colour alone.
- `ai_brain.py`: in the cast prompt path, tell the model the asker is a recurring fictional cast character and may be addressed as such (light fourth-wall breaks are welcome; never imply they are a real viewer). Add a `cast_persona` field to the chat buffer entries so the prompt renders `Cast @ExistentialDave` instead of `Viewer @ExistentialDave`.
- `chatter_db.py`: ensure cast handles are excluded from any "returning viewer" / relationship stats used in the continuity brief so the AI never greets a cast character as a real regular.
- Add `cast_badge_label` to config (default `CAST`).

### Acceptance
- Screenshot both 16:9 and 9:16 with a pinned cast question and a pinned real question; the cast badge is legible at 1080p and absent on the real one.

---

## Phase 5 — Rendering performance (decouple from the conversational loop)

Goal: the 60 FPS pygame render must not compete with chat handling, Gemini streaming, or TTS on the asyncio event loop.

### 5.1 Move rendering to a dedicated process
- Create `render_worker.py` containing the pygame loop. It owns the `Visualizer` instance and the NDI video sender.
- Communication from `app.py` via `multiprocessing` with:
  - A **shared memory** block (`multiprocessing.shared_memory`) for audio metrics (`rms`, 32-bin spectrum, `is_speaking`) written by the TTS audio callback ~every 10–20 ms.
  - A `multiprocessing.Queue` (or `Pipe`) for low-rate state: chat history diffs, pinned question, mood, subtitle target (motto/question only), engagement mode, viewer count, celebration/promo triggers, fade commands (`fade_out_for_turn`, `fade_out_question`, `clear_subtitle`).
- `app.py` keeps a thin `VisualizerProxy` exposing the same method names the orchestrator already calls (`set_mood`, `set_subtitle`, `fade_out_for_turn`, `fade_out_question`, `trigger_celebration`, `trigger_promo`, `is_promo_active`, `should_quit`) so call sites do not change.
- Audio stays in the main process (PortAudio callback + NDI audio pump). Verify lip-sync is unaffected: the star reacts from the shared metrics, which are written from the same callback that feeds the speakers/NDI.
- Handle worker crash: if the render process dies, log at ERROR, restart it once, and keep the audio/chat pipeline alive.

### 5.2 Cheap wins inside `visualizer.py`
- Cache the `ColorPalette.get(mood)` lookup per frame (currently called multiple times).
- Pre-render the god-circle surface at a small set of quantized radii instead of allocating/redrawing when `r_outer` changes by a pixel; or draw it once per frame into a persistent surface without reallocation.
- Only call `pygame.transform.smoothscale` for the preview window at ≤ 30 FPS (preview is for the operator, not the broadcast). The NDI frame remains 60 FPS from the full-res surface.
- Skip re-rendering chat text surfaces when the chat list and pinned message are unchanged (hash the inputs; keep the existing cache pattern but make it cover the whole card).
- Profile before/after with `cProfile` for 600 frames and include the top-20 cumulative table in the PR description.

### Acceptance
- Measured render FPS ≥ 58 sustained with a 3-sentence answer playing and 50 chat messages in history, on the current host machine.
- Main-process event loop lag (measure with a 100 ms heartbeat task and log max drift per 10 s) stays under 20 ms during rendering.

---

## Phase 6 — Context-aware promo cards

- `_update_promo_state` currently rotates "Ask Anything" and "Like & Subscribe" on a timer. Change to event-driven:
  - "Ask Anything" shows only when chat has been silent for ≥ `promo_ask_quiet_sec` (default 45 s), viewers ≥ 1, and no turn is active.
  - "Like & Subscribe" shows within `promo_sub_after_turn_sec` (default 3 s) after a completed non-spontaneous turn or celebration, at most once per `promo_sub_min_interval_sec` (default 300 s).
  - Keep the existing rule that promos never overlap speech or a pinned question.
- Expose these in `config.py`; keep the old timer mode reachable via `promo_mode = "timer" | "event"` (default `event`).

---

## Phase 7 — Housekeeping

- There are three separate `logging.basicConfig` calls across modules; move to a single `logging_setup.py` called once from `main()`. Module loggers keep their `[AI-BRAIN]`-style prefixes via a formatter that reads `record.name`.
- Consolidate every `getattr(self.cfg, "key", default)` into real attributes with defaults in `config.py`, then replace with `self.cfg.key`. `config.py` already defines most of them (e.g. `tts_backend`, `tts_server_url`, `gemini_fast_thinking_budget`), so the `getattr` guards in `tts_engine.py` and `ai_brain.py` are pure noise.
- Resolve the `tts_engine` (env `TTS_ENGINE`, "edge-tts") vs `tts_backend` (env `TTS_BACKEND`, "chatterbox"|"edge") duplication in `config.py`: keep `tts_backend`, delete `tts_engine`, and make sure `tts_engine.py` reads only the survivor.
- `gemini_thinking_budget` (128) appears to be superseded by `gemini_fast_thinking_budget` / `gemini_deep_thinking_budget`; confirm nothing reads it and delete it. Produce a table of every key, its default, and the file(s) that read it, saved as `docs/config_reference.md`.
- Normalise line endings to LF (files currently have CRLF) and add `.gitattributes`.
- Add `tests/` with the trigger, queue, and sentence-splitter tests from Phases 2–3, runnable with `pytest -q`.

---

## Reporting

After each phase, write a short section in `docs/CHANGELOG_refactor.md`: what changed, measured numbers (FPS, TTFA, loop lag), and anything you chose not to do and why. If you find that a supporting module (e.g. `tts_engine.py`) makes a phase infeasible as written, stop and explain the constraint before working around it.
