# Round 4 follow-ups for Antigravity

Apply the two patched files (`app.py`, `ai_brain.py`) first, then do these. Each item has an acceptance check.

## 1. Avatar metrics at 60 Hz from the 50 ms audio blocks

**Problem.** The NDI audio pump now sends 2400-sample (50 ms) blocks and writes avatar metrics once per block, so the star/EQ update at 20 Hz instead of 60 Hz. Worse, `AudioAnalysisProcessor.process()` rolls a 1024-sample window by `min(1024, len(packet))`, so only the last 1024 of each 2400 samples are ever analysed. The main process no longer writes metrics (single-writer fix in `app.py`), so the pump must produce a proper 60 Hz signal.

**Fix.**
- Enlarge the shared-memory header from 160 to 4096 bytes (`AUDIO_METRICS_HEADER_SIZE`). Keep the ring-buffer control fields (`write_pos`, `read_pos`, `utterance_open`) at their current offsets 144/148/156. Place a **metrics ring of 8 slots** starting at offset 512; each slot: `float64 play_at_ts`, `float32 rms`, `uint8 is_speaking`, `float32[32] spectrum` (pack with `struct`, fixed slot stride 160 bytes). A `uint32 metrics_head` at offset 508.
- In the pump, for each 2400-sample block: split into three 800-sample hops, run the analyzer on each hop (so all samples are windowed), and write three slots with `play_at_ts = t_block_send + k * 800/48000` (k = 0,1,2), where `t_block_send` is `time.time()` at the `write_audio` call plus `ndi_audio_metrics_latency_sec` (config, default 0.0; tune ±50 ms by eye against the OBS output so the mouth/star lands on the audio).
- In the render loop, replace `shm.read()` with `shm.read_metrics_for(now)`: pick the slot with the greatest `play_at_ts <= now`; if none, use the oldest.
- Delete `AudioMetricsSharedMemory.write()` and `VisualizerProxy.write_audio_metrics()` plus their callers (there should be none left after the single-writer fix; `grep -n write_audio_metrics *.py` must be empty).

**Acceptance.** `tests/test_metrics_ring.py`: push a 1 s 1 kHz tone through the pump with a mocked NDI sender; sample `read_metrics_for(t)` at 60 Hz and assert ≥ 55 distinct rms updates per second and that `is_speaking` rises within 60 ms of the tone start. Visually, the EQ bars should move at frame rate again.

## 2. Promo cooldown must be stamped on completion, not on trigger

Not done from the earlier list. `_promo_overlay_monitor_task` sets `last_like_sub_time = now` when it calls `trigger_promo("like_sub")`. An interrupted promo therefore consumes the full `promo_sub_min_interval_sec`.

- Render worker: when a promo reaches ≥ 60 % of its display duration, write a `promo_completed:<type>:<ts>` marker back to the main process (a second `mp.Queue(maxsize=16)` from worker → proxy, drained by the proxy on each `sync_state` call; or a shared `mp.Value`). Proxy exposes `last_promo_completed(type) -> float`.
- The monitor uses `last_promo_completed("like_sub")` for the cooldown. Trigger-time is only used to prevent double-triggering within 10 s.
- Post-turn `like_sub` is skipped when `len(self.comment_queue) > 0` (there is already a heap; check it) and logged at DEBUG with the reason.
- Test in `tests/test_promo_cards.py`: interrupted promo does not consume cooldown.

## 3. Remove the legacy NDI paths

`send_frame_sync`, `send_frame`, and `send_audio` in `ndi_streamer.py` are dead in proxy mode and `send_frame_sync` still pads to 800 samples against a 2400-capacity frame. Delete all three and the `samples_per_frame` padding logic. `grep -n "send_frame\b\|send_frame_sync\|send_audio(" *.py` must return nothing. The in-process fallback pump in `app.py` already uses `send_audio_packet` with the streamer's block size.

## 4. Small cleanups

- Four `getattr(self.cfg, ...)` / `getattr(config, ...)` remain; replace with direct attribute access now that every key exists in `config.py`.
- `_tts_consumer` peeks `sentence_queue._queue` to estimate pending characters. Replace with a `pending_chars` counter maintained by the producer (increment on put, decrement in the consumer after `get`), so the estimate does not depend on a private attribute.
- `test_tts_buffer.py::test_concurrent_push_and_pop_latency` asserts `< 2.0 ms` for a single pop under a concurrent push. It flakes under load. Change to: 99th percentile < 2.0 ms and max < 10 ms.
