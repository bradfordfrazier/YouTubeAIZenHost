# Verify and close out the TTS supply fix

The five items from `FIX_tts_supply_underrun.md` are reported as implemented. This pass closes the two gaps in that report and produces the measurements that prove the stream is clean. Do these in order. Do not begin new feature work until Part C is delivered.

---

## Part A — Every non-turn synthesis must go through `synthesize_background`

The summary says `synthesize_background` was integrated into `greeting_cache.py`. `reflection_cache.py` was not mentioned, and it is the more likely source of GPU contention: reflections are ~9 s of audio each and the cache refills after every idle reflection plays.

1. Run `grep -rn "\.synthesize(" --include=*.py .` and list every hit in the changelog.
2. The only permitted callers of `TTSEngine.synthesize` are:
   - `_tts_consumer` (the live-turn consumer in `app.py`), and
   - `TTSEngine.synthesize_background` itself.
   Every other caller — `reflection_cache.py`, `greeting_cache.py`, any warm-up or self-test path, anything in `ai_brain.py` — must call `synthesize_background(text, mood)` instead.
3. Make `synthesize` refuse misuse: add a keyword-only parameter `_from_live_turn: bool = False`. `_tts_consumer` passes `True`; `synthesize_background` passes `True` after it has acquired the lock. If called with `False`, log at ERROR with a stack trace (`logger.error(..., stack_info=True)`) and still perform the synthesis — do not break production, just make the violation impossible to miss.
4. Add `tests/test_gpu_exclusivity.py`:
   - Start a `synthesize_background` call (mock the Chatterbox HTTP call with a 2 s sleep). While it is waiting, set `live_turn_active`. Assert a `synthesize(_from_live_turn=True)` call completes in < 2.5 s and the background call completes only after `live_turn_active` is cleared plus `cache_refill_cooldown_sec`.
   - Assert `synthesize_background` never holds `gpu_lock` while blocked on `live_turn_active` (instrument with a flag set inside the lock and asserted from the test while the event is set).

---

## Part B — Confirm the hang safeguards survived

The earlier hang was fixed by adding a turn watchdog and a hard turn timeout. Neither is mentioned in the latest summary. Confirm they still exist and are tested.

1. `grep -n "turn_phase\|turn_max_sec\|wait_for" app.py` must show:
   - `self.turn_phase` being set at each stage: `"gemini"`, `"synth"`, `"lead_gate"`, `"display_hold"`, `"push"`, `"wait_complete"`, `"done"`.
   - `_execute_ai_turn`'s body wrapped in `asyncio.wait_for(..., timeout=self.cfg.turn_max_sec)`.
   - A watchdog in `comment_queue_scheduler_task` that logs at WARNING every 15 s when a turn has been active > 60 s, including `turn_phase`.
2. On timeout the cleanup must, in this order: log ERROR with `turn_phase`; `tts.clear_audio_buffer()`; `tts.end_utterance()`; clear `live_turn_active`; ensure `gpu_lock` is released (it must be acquired with `async with`, never manual `acquire()`); clear the pinned question via the proxy; return normally so the scheduler continues.
3. Add `tests/test_turn_watchdog.py` if it does not exist: stub the lead gate so it never opens, set `turn_max_sec = 2`, run one turn, and assert (a) it returns within 3 s, (b) `live_turn_active` is clear afterwards, (c) `gpu_lock.locked()` is `False`, (d) a second turn then completes normally.

---

## Part C — Produce the measurements

Run the app against the real Chatterbox server with a real Gemini key. Send one console question that produces a 3–4 sentence answer (e.g. "Tell me three things you've learned about being human, one sentence each, then a punchline."). Capture and paste verbatim into `docs/CHANGELOG_round2.md` under a heading **"TTS supply verification"**:

1. From the main-process log, for that one turn:
   - the `[TTS LEAD]` line (buffered seconds, estimated remaining, rtf),
   - every `[TTS LIVE]` synthesis line with its wall time and `rtf`,
   - every `[TTS UNDERRUN]` and `[NDI UNDERRUN]` line (or state explicitly that there were none),
   - the turn summary line with `TTFT`, `TTFS`, `TTFA`, `total`, `underruns`, `underrun_ms`.
2. From the Chatterbox server log, the same 30-second window. Confirm in one sentence whether more than one `Sampling:` progress bar was ever active at the same time.
3. From the render-worker log, the audio-pump interval line (max interval between `write_audio` calls) for the 10 s bucket covering the answer.

Then repeat the same question **while a reflection-cache refill is due** (empty the reflection cache first via a console command or by lowering `reflection_cache_size` to 1 and letting one play) and paste the same three items. This is the contention scenario that caused the original breakup; it must now show the background refill starting only after the turn ends plus the cooldown.

**Pass criteria** — all of the following, in both runs:
- `underruns=0` in the turn summary.
- No `[NDI UNDERRUN]` lines.
- Exactly one `Sampling:` bar at a time on the server during the turn.
- Audio-pump max interval < 20 ms.
- No `Chatterbox … timeout` at ERROR level.

If any criterion fails, do not adjust config values to make it pass. Report which criterion failed, the log lines around it, and stop — the fix will be decided from the evidence.

---

## Part D — Small follow-ups (only after Part C passes)

1. `TTS_SEC_PER_CHAR` calibration: from the `[TTS LIVE]` lines, compute actual `audio_sec / len(text)` for each sentence and set the default to the median. Record the samples in the changelog.
2. If the median `rtf_conservative` after 20+ syntheses is consistently > 1.6, lower `LEAD_SAFETY` from 1.25 to 1.15 to recover a little TTFA. If it is < 1.3, leave it.
3. Remove the `IAM_TEST_WORKER_STALL` hook if it is still present, or move it behind a clearly named test-only config flag.
