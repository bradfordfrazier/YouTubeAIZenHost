# Fix: spoken audio breaking up in the OBS NDI feed

Do exactly this, in order. Do not touch `ai_brain.py`, sentence chunking, TTS fades, or `inter_sentence_gap_sec` — they are not the cause. The whole-utterance synthesis that was put back in `_execute_ai_turn` did not fix the breakup, which proves the problem is in transport, not synthesis.

## Root cause (three compounding bugs in `render_worker.py` / `ndi_streamer.py`)

1. **NDI audio is clocked by the pygame frame rate.** `render_worker_main` pulls exactly 800 samples per rendered frame (`shm.read_audio_samples(samples_per_frame)`) and sends them with `send_frame_sync`. Audio only flows when a frame is rendered. Software-rendering 1080p at 60 FPS has unstable frame times, so audio delivery jitters with it.

2. **The frame-pacing "drift reset" drops audio.** In step 6 of the loop: `if now_perf - t_next_frame > 0.050: t_next_frame = now_perf`. Every time the worker falls ≥ 50 ms behind, it skips the missed frames instead of catching up. Each skipped frame is 800 samples (16.7 ms) of speech that is *never sent*. That is the audible breakup: holes in the audio every time the render loop hitches (chat-card rebuild, celebration burst, GC, OS scheduling).

3. **The shared-memory ring buffer has a cross-process race on `available_samples`.** `write_audio_samples` (main process) and `read_audio_samples` (worker) both do read-modify-write on the same `avail` field with no lock. When a push lands during a read, one side's update is lost; `avail` becomes wrong and the reader either emits silence while audio is waiting or reads past the write head.

Secondary: `NDIStreamer.send_audio()` zero-pads any packet shorter than 800 samples, and the fallback pump in `app.py` sends 480-sample packets — 320 samples of silence after every 10 ms. Not the active path now, but it must be fixed so the fallback mode isn't broken too.

## Changes

### A. `render_worker.py` — give audio its own clock

1. Add a function `ndi_audio_pump(ndi, shm, stop_event)` that runs in a **dedicated thread inside the render worker process** (same process as the single NDI sender — do not create a second sender):
   ```python
   def ndi_audio_pump(ndi, shm, stop_event, samples_per_packet=800, sample_rate=48000):
       interval = samples_per_packet / sample_rate          # 16.6667 ms
       t_next = time.perf_counter()
       try:
           import ctypes; ctypes.windll.avrt  # noqa – see priority note below
       except Exception:
           pass
       while not stop_event.is_set():
           packet = shm.read_audio_samples(samples_per_packet)   # (800, 2) float32, zeros if empty
           if ndi.is_open:
               ndi.send_audio_packet(packet)                     # new method, see B
           t_next += interval
           now = time.perf_counter()
           if now - t_next > 0.100:          # >100 ms behind: catch up by sending immediately, never skip
               t_next = now
           sleep_s = t_next - now
           if sleep_s > 0.002:
               time.sleep(sleep_s - 0.001)
           while time.perf_counter() < t_next:
               pass
   ```
   Start it right after `ndi.open()` in `render_worker_main` with `threading.Thread(target=..., name="ndi_audio_pump", daemon=True)`. Set the thread to time-critical priority on Windows via `ctypes.windll.kernel32.SetThreadPriority(GetCurrentThread(), 15)` (THREAD_PRIORITY_TIME_CRITICAL) inside the thread; wrap in try/except for non-Windows.

2. In the render loop, **remove** `audio_packet = shm.read_audio_samples(samples_per_frame)` and change `ndi.send_frame_sync(rgba_bytes, audio_packet)` to `ndi.send_video(rgba_bytes)`. The render loop sends video only.

3. Change the drift-reset threshold from `0.050` to `0.250` in the render loop, and note in a comment that dropping *video* frames on a hitch is acceptable; audio is independent now.

4. Keep `shm.read()` for metrics — the render loop still needs `audio_metrics` for the star/EQ.

### B. `ndi_streamer.py` — open the sender audio-clocked and stop padding

1. In `open()`, construct the sender with `clock_video=False, clock_audio=True`. With `clock_audio=True` the NDI SDK paces `write_audio` to real time, so a slightly-early call blocks briefly instead of creating a gap, and a slightly-late one is absorbed by the receiver's buffer. The Python audio thread from A.1 is still the primary clock; NDI's clock is the safety net.

2. Add:
   ```python
   def send_audio_packet(self, packet: np.ndarray):
       """packet: (800, 2) interleaved float32 — exactly samples_per_frame, never padded."""
       if not self.is_open or self.is_mock or not self.sender:
           return
       if packet.shape != (self.samples_per_frame, 2):
           logger.warning(f"send_audio_packet: got {packet.shape}, expected ({self.samples_per_frame}, 2); dropping")
           return
       planar = np.ascontiguousarray(packet.T, dtype=np.float32)
       with self._lock:
           try:
               self.sender.write_audio(planar)
           except Exception as e:
               logger.error(f"NDI write_audio error: {e}")
   ```

3. In `send_audio()` (legacy path): remove the zero-padding of short chunks. If the last chunk is short, send it only if ≥ 480 samples; otherwise drop it and log at DEBUG. Set `self.audio_packet_samples = self.samples_per_frame` (800) and delete the `480` constant.

4. `send_frame_sync` stays for the fallback in-process mode but must never be called from the render worker after this change. Add an assertion-style log if it is called while `clock_audio` is True.

### C. `render_worker.py` — make the ring buffer a proper single-producer/single-consumer ring

Replace the shared `available_samples` counter with position-only bookkeeping. Writer owns `write_pos`, reader owns `read_pos`; each side reads the other's position but only writes its own. Available = `(write_pos - read_pos) % RING_BUFFER_FRAMES`.

- `write_audio_samples`: read `read_pos` once; compute free space `RING_BUFFER_FRAMES - 1 - ((write_pos - read_pos) % RING_BUFFER_FRAMES)`; if `n_samples > free`, truncate to `free` and log a WARNING (this should never happen with a 120 s ring). Copy data, **then** publish the new `write_pos` with a single `struct.pack_into("=I", buf, 144, new_write_pos)`. Do not touch offset 148.
- `read_audio_samples`: read `write_pos` once; `avail = (write_pos - read_pos) % RING_BUFFER_FRAMES`; copy `min(num_samples, avail)`; publish only `read_pos` at offset 148. Do not touch offset 144.
- Delete offset 152 (`available_samples`) from the layout comment and from `clear_audio`. `clear_audio` sets both positions to 0 — it is only called from the main process while nothing is playing, which is acceptable; document that.
- Because the writer copies data before publishing `write_pos`, the reader can never observe a position that points at unwritten memory. This is the standard SPSC ring; no lock required.

Shrink `RING_BUFFER_FRAMES` from 120 s to 30 s (5.76 M frames → 1.44 M, ~11.5 MB). No answer is longer than that and the smaller mapping is friendlier to the page cache.

### D. `app.py` — stop double-feeding and fix the fallback pump

1. `_ndi_audio_pump_worker`: change `packet_samples = 480` to `packet_samples = 800` and call `self.ndi.send_audio_packet(audio_for_ndi.T)` (or adapt shape) instead of `send_audio`. It remains bypassed when `VisualizerProxy` is active.

2. In `video_broadcast_task`, delete block "1b. Write audio metrics into shared memory" — `_sd_audio_callback` already writes them from the hardware-clocked PortAudio thread, and the 20 Hz copy is stale by the time it lands.

3. In `_execute_ai_turn`, the `tts.push_audio(...)` + `visualizer.push_audio_samples(...)` pair is correct and stays. Ensure `push_audio_samples` is always called *after* `tts.push_audio` (it is), so the local-monitor and NDI streams stay in the same order.

4. `TTSEngine.wait_until_speech_completed()` currently detects "no backend popping" and falls back to elapsed-time waiting, because nothing in the main process drains `_audio_buffer_ndi` when the proxy is active. That works but wastes memory. In `TTSEngine.__init__`, add `self.ndi_buffer_enabled = True`; in `app.py` set `self.tts.ndi_buffer_enabled = False` when `VisualizerProxy` is used; in `push_audio`, skip the `_audio_buffer_ndi` vstack when disabled; in `wait_until_speech_completed`, when disabled, wait on `_audio_buffer_local` drain (the PortAudio callback pops it) or on elapsed `_utterance_total_samples / sample_rate` if local audio is disabled.

## Acceptance — all four must pass before this is "done"

1. **Interval log.** In `ndi_audio_pump`, keep a rolling max of the interval between consecutive `write_audio` calls and log it every 10 s. Steady state must be < 20 ms max while a 3-sentence answer plays *and* the chat card is redrawing (inject 20 console messages during the answer).

2. **No holes.** Add `--audio-selftest` to `render_worker.py`: push a 10 s 1 kHz sine into the ring from the main process, have the pump write into a `.wav` file instead of NDI, and assert (a) the file is 10.0 s ± 1 frame, (b) there is no run of ≥ 400 consecutive zero samples inside the tone. Run this with the render loop simultaneously rendering at full load.

3. **OBS check.** With the NDI source in OBS, set the NDI source's "Audio sync" to "Source timing" and confirm 60 s of continuous speech has no dropouts. Then switch to "Network" and confirm the same. Report which one the user should keep (expect "Source timing" now that `clock_audio=True`).

4. **Fallback mode.** Run once with the proxy disabled (in-process visualizer + `_ndi_audio_pump_worker`) and confirm no 100 Hz buzz/stutter — proves the padding fix.

After all four pass, re-enable sentence pipelining in `_execute_ai_turn` per Phase 2.4 of the refactor plan. It was not the cause of the breakup and should come back.
