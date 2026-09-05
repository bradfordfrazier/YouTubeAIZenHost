# Fix: residual audio breakup — TTS supply underruns

The NDI transport is now clean. The remaining breakup is the ring buffer running empty between sentences because Chatterbox cannot always synthesize sentence N+1 faster than sentence N plays. Evidence from the Chatterbox server log: a sentence synthesized alone runs at 1.9× real time; the same-length sentence synthesized while a second job (a cache refill) shares the GPU runs at 1.1×. At 1.1× the pipeline cannot keep up.

Implement all five items. Do not disable sentence pipelining — the fix is to feed it correctly.

---

## 1. Prove it first — underrun detector (do this before anything else)

In the NDI audio pump thread in `render_worker.py`, and in `TTSEngine.pop_local_audio`, detect the case "utterance open but buffer empty":

- `TTSEngine`: add `self.underrun_count` and `self.underrun_samples`. In `pop_local_audio`, if `_utterance_open` is True and the deque is empty, increment both (samples += `num_samples`) and, at most once per 500 ms, log at WARNING: `"[TTS UNDERRUN] utterance open, local buffer empty (N underruns, X ms total)"`.
- Ring buffer in `render_worker.py`: add a byte at header offset 156 (currently padding) `utterance_open` (uint8), written by `push_audio`'s sink on `begin_utterance`/`end_utterance` via two new `VisualizerProxy` methods. In the pump thread, if `utterance_open == 1` and `avail == 0`, log the same WARNING with `[NDI UNDERRUN]`.
- In `app.py::_execute_ai_turn`, log at the end of every turn: `underruns=<n> underrun_ms=<x>` alongside the existing TTFT/TTFS/TTFA/total line.

Run a 3-sentence answer. The WARNING lines will land at sentence boundaries. That confirms the diagnosis; keep the detector permanently.

---

## 2. Live turns get the GPU exclusively

Background pre-synthesis (`greeting_cache.py`, `reflection_cache.py`, and anything else that calls `tts.synthesize` outside `_execute_ai_turn`) must never overlap a live turn.

- Add to `TTSEngine`: `self.live_turn_active = asyncio.Event()` (cleared = no turn) and `self.gpu_lock = asyncio.Lock()`.
- `_execute_ai_turn` sets `live_turn_active` at entry and clears it in `finally`. Live synthesis calls acquire `gpu_lock`.
- Every background synthesis call must: (a) wait until `live_turn_active` is clear, (b) acquire `gpu_lock`, (c) after acquiring, re-check `live_turn_active`; if a turn started while waiting, release and go back to (a). Implement this once as `TTSEngine.synthesize_background(text, mood)` and make the caches call that instead of `synthesize`.
- Additionally, background refills must not start within `cache_refill_cooldown_sec` (config, default 8.0) after a turn ends — a viewer question often follows an answer immediately, and the GPU should be free for it.
- Log every background synthesis at INFO with the tag `[TTS BG]` so it is visually distinct from `[TTS LIVE]` in the server-side timing correlation.

Acceptance: during a live turn the Chatterbox server log shows exactly one `Sampling:` progress bar at a time.

---

## 3. Serial live synthesis, and an honest timeout

- Set `max_concurrent_synth` default to **1**. Two concurrent live requests halve each one's throughput and gain nothing on a single GPU. The producer/consumer in `_execute_ai_turn` still overlaps synthesis of N+1 with *playback* of N — that is the only overlap we want.
- Replace the Chatterbox timeout formula. Current: `min(30, max(4, len(text) * 0.08))`. New: estimate audio seconds as `len(text) * tts_sec_per_char` (config, default 0.065 — calibrate: the log shows ~9.7 s for ~150 chars), then `timeout = est_audio_sec * 2.0 + 4.0`, clamped to [8, 45]. A slow-but-succeeding sentence must not be abandoned for an Edge-TTS fallback that changes the voice mid-answer.
- If Chatterbox does time out mid-turn, log at ERROR (not WARNING) with the sentence and elapsed time, because a voice switch mid-answer is a visible defect.

---

## 4. Adaptive playback start (lead buffer)

Do not start playback the instant sentence 1 is ready. Start when the buffered audio is enough to cover the expected synthesis time of what is still to come.

- `TTSEngine` keeps a rolling real-time factor: after each live synthesis, `rtf = audio_sec / wall_sec`; store the last 8 in a deque; use the **minimum** of the last 8 as `rtf_conservative` (default 1.5 before any samples exist).
- In `_execute_ai_turn`, the consumer does not call `begin_utterance`/first `push_audio` until **either**:
  - all sentences have been synthesized (sentinel received), **or**
  - `buffered_audio_sec >= estimated_remaining_synth_sec * lead_safety` where `estimated_remaining_synth_sec = sum(len(s) * tts_sec_per_char for s in sentences_not_yet_synthesized) / rtf_conservative`, and `lead_safety` is config (default 1.25).
  - Sentences not yet *received* from Gemini count as one average sentence (`tts_avg_sentence_chars`, config default 110) each until the sentinel arrives; cap the estimate at 3 pending sentences so a long answer still starts within reason.
- Subsequent chunks push immediately as they finish; the lead calculation only gates the **first** push.
- Log the decision: `"[TTS LEAD] starting playback with 9.6s buffered, est. remaining synth 6.4s (rtf 1.7)"`.
- Keep the question-display hold logic; the lead gate and the display hold are both satisfied before the first push (whichever is later).

Acceptance: with the detector from item 1, a 4-sentence answer produces zero `[NDI UNDERRUN]` lines. TTFA rises slightly versus the naïve pipeline; report the before/after TTFA in the changelog.

---

## 5. Graceful underrun instead of a hard gap

Even with items 2–4, a GPU hiccup can still starve the buffer. Make the failure mode inaudible instead of a click-gap:

- In the ring-buffer reader (`read_audio_samples`) and `pop_local_audio`, when the buffer empties while `utterance_open`, apply a 5 ms fade-out to the last available samples before emitting zeros, and on resume apply a 5 ms fade-in to the first samples. Track `_resume_pending` for this.
- Do not attempt time-stretching or resampling; the small fades are enough.

---

## Report

Add to `docs/CHANGELOG_round2.md`: underrun counts before and after (from the item 1 detector) for the same 3-sentence test answer, the measured `rtf` values for solo vs. overlapped synthesis, and the new TTFA. If the GPU server can be given a streaming (chunked-WAV) endpoint, note it as a future improvement — it would remove most of the lead requirement — but do not implement it in this pass.
