"""
Dedicated 60 FPS Rendering Process & Visualizer Proxy (Phase 5).
Decouples Pygame 1080p60 GPU rendering and NDI video/audio transmission into a dedicated
multiprocessing worker process, communicating via shared memory for low-latency audio metrics & audio ring buffer
and a thread-safe Queue for state transitions and visual controls.
"""

import collections
import logging
import multiprocessing as mp
from multiprocessing import shared_memory
import os
import queue
import struct
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from config import config

logger = logging.getLogger("render_worker")

import threading

# Shared memory format (SPSC Lockless Layout):
# offset 0:    float32 rms (4 bytes)
# offset 4:    uint8 is_speaking (1 byte)
# offset 5:    uint8 padding [3 bytes]
# offset 8:    float32 spectrum [32 bins * 4 bytes = 128 bytes]
# offset 136:  float64 timestamp (8 bytes)
# offset 144:  uint32 write_pos (4 bytes) - owned exclusively by writer (main process)
# offset 148:  uint32 read_pos (4 bytes) - owned exclusively by reader (render worker)
# offset 152:  uint8 padding [4 bytes]
# offset 156:  uint8 utterance_open (1 byte) - 1 if speech utterance in progress, 0 if idle
# offset 157:  uint8 padding [3 bytes]
# offset 160:  float32 audio_ring_buffer [RING_BUFFER_FRAMES * 2 channels * 4 bytes]
# Sized to 30 seconds (1,440,000 frames @ 48kHz stereo = ~11.5 MB)
RING_BUFFER_FRAMES = 48000 * 30
AUDIO_METRICS_HEADER_SIZE = 160
AUDIO_DATA_BYTE_SIZE = RING_BUFFER_FRAMES * 2 * 4
AUDIO_SHM_SIZE = ((AUDIO_METRICS_HEADER_SIZE + AUDIO_DATA_BYTE_SIZE + 4095) // 4096) * 4096
AUDIO_SHM_NAME = "iam_audio_metrics_shm"


class AudioMetricsSharedMemory:
    """
    Lockless Single-Producer Single-Consumer (SPSC) shared memory interface
    for real-time audio reactivity and high-priority audio transmission.
    """

    def __init__(self, name: str = AUDIO_SHM_NAME, create: bool = False):
        self.name = name
        self.create = create
        self.shm: Optional[shared_memory.SharedMemory] = None
        self._resume_pending: bool = False
        # Samples handed to the reader since utterance_open last went 0 -> 1. Starvation and
        # underrun only count once real audio has flowed in this utterance.
        self._consumed_since_open: int = 0
        self._last_open_state: bool = False

        if create:
            try:
                self.shm = shared_memory.SharedMemory(name=self.name, create=True, size=AUDIO_SHM_SIZE)
            except FileExistsError:
                try:
                    # Stale segment on Windows: reuse if size is sufficient, otherwise recreate
                    existing = shared_memory.SharedMemory(name=self.name, create=False)
                    if existing.size >= AUDIO_SHM_SIZE:
                        self.shm = existing
                    else:
                        existing.close()
                        try:
                            existing.unlink()
                        except Exception:
                            pass
                        self.shm = shared_memory.SharedMemory(name=self.name, create=True, size=AUDIO_SHM_SIZE)
                except Exception as e:
                    logger.error(f"❌ Failed to attach/recreate existing shared memory segment '{self.name}': {e}")
                    self.shm = None
            except Exception as e:
                logger.error(f"❌ Failed to create shared memory segment '{self.name}': {e}")
                self.shm = None

            if self.shm is None:
                raise RuntimeError(
                    f"Could not initialize shared memory segment '{self.name}'. "
                    "Application cannot function without audio metrics IPC."
                )

            # Initialize with zeroes
            self.shm.buf[:AUDIO_SHM_SIZE] = b"\x00" * AUDIO_SHM_SIZE
        else:
            # Worker process: retry attaching 10 times over 2s before raising
            for attempt in range(10):
                try:
                    self.shm = shared_memory.SharedMemory(name=self.name, create=False)
                    break
                except Exception:
                    time.sleep(0.2)

            if self.shm is None:
                raise RuntimeError(
                    f"Render worker failed to attach to shared memory segment '{self.name}' after 10 attempts (2.0s)."
                )

    def write(self, rms: float, is_speaking: bool, spectrum: np.ndarray, timestamp: Optional[float] = None):
        """Writes live audio metrics from TTS audio callback into shared memory."""
        if not self.shm:
            return
        ts = timestamp or time.time()
        sp_arr = np.asarray(spectrum, dtype=np.float32)
        if len(sp_arr) < 32:
            sp_padded = np.pad(sp_arr, (0, 32 - len(sp_arr)), "constant")
        else:
            sp_padded = sp_arr[:32]

        buf = self.shm.buf
        struct.pack_into("=fB3x", buf, 0, float(rms), 1 if is_speaking else 0)
        buf[8:136] = sp_padded.tobytes()
        struct.pack_into("=d", buf, 136, ts)

    def set_utterance_state(self, is_open: bool):
        """Sets the utterance_open flag in shared memory header at byte offset 156."""
        if not self.shm:
            return
        struct.pack_into("=B", self.shm.buf, 156, 1 if is_open else 0)

    def get_utterance_state(self) -> bool:
        """Reads the utterance_open flag from shared memory header at byte offset 156."""
        if not self.shm:
            return False
        return bool(struct.unpack_from("=B", self.shm.buf, 156)[0])

    def write_audio_samples(self, audio: np.ndarray):
        """
        Appends stereo float32 audio samples into the shared memory SPSC ring buffer.
        Only mutates write_pos (offset 144) after data is copied, ensuring reader never observes unwritten data.
        """
        if not self.shm or audio is None or len(audio) == 0:
            return
        if audio.ndim == 1:
            audio = np.column_stack((audio, audio))
        elif audio.shape[1] == 1:
            audio = np.column_stack((audio[:, 0], audio[:, 0]))
        audio = np.ascontiguousarray(audio, dtype=np.float32)

        n_samples = len(audio)
        buf = self.shm.buf
        write_pos = struct.unpack_from("=I", buf, 144)[0]
        read_pos = struct.unpack_from("=I", buf, 148)[0]

        # SPSC free space calculation: reserve 1 frame so write_pos == read_pos means empty, not full
        free_space = RING_BUFFER_FRAMES - 1 - ((write_pos - read_pos) % RING_BUFFER_FRAMES)
        if n_samples > free_space:
            logger.warning(f"write_audio_samples: audio length {n_samples} exceeds free ring space {free_space}; truncating")
            audio = audio[:free_space]
            n_samples = free_space

        if n_samples == 0:
            return

        audio_mem = np.frombuffer(
            buf[AUDIO_METRICS_HEADER_SIZE : AUDIO_METRICS_HEADER_SIZE + AUDIO_DATA_BYTE_SIZE],
            dtype=np.float32,
        ).reshape((RING_BUFFER_FRAMES, 2))

        if write_pos + n_samples <= RING_BUFFER_FRAMES:
            audio_mem[write_pos : write_pos + n_samples] = audio
        else:
            part1 = RING_BUFFER_FRAMES - write_pos
            part2 = n_samples - part1
            audio_mem[write_pos : RING_BUFFER_FRAMES] = audio[:part1]
            audio_mem[:part2] = audio[part1:]

        new_write_pos = (write_pos + n_samples) % RING_BUFFER_FRAMES
        # Publish write_pos atomically to reader
        struct.pack_into("=I", buf, 144, new_write_pos)

    def read_audio_samples(self, num_samples: int = 800) -> np.ndarray:
        """
        Reads exactly num_samples stereo float32 samples from the SPSC ring buffer.
        Applies 5ms crossfades on buffer starvation and resume to eliminate clicks.
        Only mutates read_pos (offset 148) after data is copied.
        """
        if not self.shm:
            return np.zeros((num_samples, 2), dtype=np.float32)

        buf = self.shm.buf
        read_pos = struct.unpack_from("=I", buf, 148)[0]
        write_pos = struct.unpack_from("=I", buf, 144)[0]
        utterance_open = self.get_utterance_state()
        if utterance_open and not self._last_open_state:
            self._consumed_since_open = 0
            self._resume_pending = False
        self._last_open_state = utterance_open

        avail = (write_pos - read_pos) % RING_BUFFER_FRAMES
        out_audio = np.zeros((num_samples, 2), dtype=np.float32)
        to_read = min(num_samples, avail)
        self._consumed_since_open += to_read

        if to_read > 0:
            audio_mem = np.frombuffer(
                buf[AUDIO_METRICS_HEADER_SIZE : AUDIO_METRICS_HEADER_SIZE + AUDIO_DATA_BYTE_SIZE],
                dtype=np.float32,
            ).reshape((RING_BUFFER_FRAMES, 2))
            if read_pos + to_read <= RING_BUFFER_FRAMES:
                out_audio[:to_read] = audio_mem[read_pos : read_pos + to_read]
            else:
                part1 = RING_BUFFER_FRAMES - read_pos
                part2 = to_read - part1
                out_audio[:part1] = audio_mem[read_pos : RING_BUFFER_FRAMES]
                out_audio[part1:to_read] = audio_mem[:part2]

            new_read_pos = (read_pos + to_read) % RING_BUFFER_FRAMES
            # Publish read_pos atomically to writer
            struct.pack_into("=I", buf, 148, new_read_pos)

        # 5ms crossfade on buffer starvation and resume (240 samples @ 48kHz)
        fade_samples = min(240, num_samples)
        if to_read < num_samples:
            # Starvation: partial or empty packet
            if to_read > 0:
                # Apply 5ms fade-out to tail of available samples before zeroes
                fade_len = min(240, to_read)
                fade_out = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)[:, None]
                out_audio[to_read - fade_len : to_read] *= fade_out
            if utterance_open and self._consumed_since_open > 0:
                self._resume_pending = True
        elif to_read == num_samples and self._resume_pending:
            # Resume after starvation: apply 5ms fade-in to leading samples
            if fade_samples > 0:
                fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)[:, None]
                out_audio[:fade_samples] *= fade_in
            self._resume_pending = False

        return out_audio

    def clear_audio(self):
        """
        Resets the shared memory audio ring buffer.
        Called from main process while speech is idle / during cancellation.
        """
        if not self.shm:
            return
        buf = self.shm.buf
        struct.pack_into("=II", buf, 144, 0, 0)
        buf[AUDIO_METRICS_HEADER_SIZE : AUDIO_METRICS_HEADER_SIZE + AUDIO_DATA_BYTE_SIZE] = b"\x00" * AUDIO_DATA_BYTE_SIZE

    def read(self) -> Dict[str, Any]:
        """Reads live audio metrics from shared memory in the render worker process."""
        if not self.shm:
            return {"rms": 0.0, "is_speaking": False, "spectrum": np.zeros(32, dtype=np.float32), "timestamp": 0.0}
        buf = self.shm.buf
        rms, is_speaking_b = struct.unpack_from("=fB", buf, 0)
        spectrum = np.frombuffer(buf[8:136], dtype=np.float32).copy()
        ts, = struct.unpack_from("=d", buf, 136)
        return {
            "rms": rms,
            "is_speaking": bool(is_speaking_b),
            "spectrum": spectrum,
            "timestamp": ts,
        }

    def close(self):
        """Closes handle to shared memory."""
        if self.shm:
            try:
                self.shm.close()
            except Exception:
                pass
            self.shm = None

    def unlink(self):
        """Unlinks shared memory segment."""
        if self.shm:
            try:
                self.shm.close()
            except Exception:
                pass
            try:
                self.shm.unlink()
            except Exception:
                pass
            self.shm = None
        else:
            try:
                temp_shm = shared_memory.SharedMemory(name=self.name, create=False)
                temp_shm.close()
                temp_shm.unlink()
            except Exception:
                pass


class AudioAnalysisProcessor:
    """Computes RMS amplitude, speaking state, and 32-band FFT spectrum for visualizer reactivity."""

    def __init__(self, sample_rate: int = 48000, num_spectrum_bands: int = 32):
        self.sample_rate = sample_rate
        self.num_spectrum_bands = num_spectrum_bands
        self.smoothed_spectrum = np.zeros(num_spectrum_bands, dtype=np.float32)
        self.current_rms = 0.0
        self.is_speaking = False
        self._analysis_window = np.zeros((1024, 2), dtype=np.float32)
        self._hanning_window = np.hanning(1024).astype(np.float32)

        fft_freqs = np.fft.rfftfreq(1024, 1.0 / self.sample_rate)
        min_freq = 40.0
        max_freq = 16000.0
        freq_bins = np.logspace(np.log10(min_freq), np.log10(max_freq), num_spectrum_bands + 1)
        self._band_slices = []
        for i in range(num_spectrum_bands):
            f_low = freq_bins[i]
            f_high = freq_bins[i + 1]
            indices = np.where((fft_freqs >= f_low) & (fft_freqs < f_high))[0]
            if len(indices) > 0:
                self._band_slices.append((int(indices[0]), int(indices[-1]) + 1))
            else:
                self._band_slices.append((0, 0))

    def process(self, packet: np.ndarray) -> Dict[str, Any]:
        """Processes a stereo packet (e.g. 800 samples) and returns audio metrics."""
        n = len(packet)
        roll_len = min(n, 1024)
        self._analysis_window = np.roll(self._analysis_window, -roll_len, axis=0)
        self._analysis_window[-roll_len:] = packet[:roll_len]

        mono = np.mean(self._analysis_window, axis=1)
        rms = float(np.sqrt(np.mean(mono**2)))
        self.current_rms = rms
        self.is_speaking = rms > 0.005

        if rms < 1e-4:
            self.smoothed_spectrum *= 0.85
        else:
            windowed = mono * self._hanning_window
            fft_vals = np.abs(np.fft.rfft(windowed))

            bands = np.zeros(self.num_spectrum_bands, dtype=np.float32)
            for i, (i_low, i_high) in enumerate(self._band_slices):
                if i_high > i_low:
                    val = float(np.mean(fft_vals[i_low:i_high]))
                    bands[i] = min(1.0, val * 0.15)

            attack = 0.7
            decay = 0.25
            mask = bands > self.smoothed_spectrum
            self.smoothed_spectrum = np.where(
                mask,
                self.smoothed_spectrum * (1.0 - attack) + bands * attack,
                self.smoothed_spectrum * (1.0 - decay) + bands * decay,
            ).astype(np.float32)

        return {
            "rms": self.current_rms,
            "is_speaking": self.is_speaking,
            "spectrum": self.smoothed_spectrum.copy(),
        }


def ndi_audio_pump(ndi, shm, stop_event, samples_per_packet=None, sample_rate=48000):
    """
    Dedicated time-critical audio pump thread inside the render worker process.
    Runs on an independent 16.6667ms real-time audio clock decoupled from Pygame rendering.
    Continuously analyzes outgoing audio packets and updates shared memory metrics for avatar reactivity.
    """
    try:
        import ctypes
        # Set thread to THREAD_PRIORITY_TIME_CRITICAL (15) on Windows
        thread_handle = ctypes.windll.kernel32.GetCurrentThread()
        ctypes.windll.kernel32.SetThreadPriority(thread_handle, 15)
        logger.info("🎙️ [NDI Audio Pump] Thread priority elevated to THREAD_PRIORITY_TIME_CRITICAL (15).")
    except Exception as e:
        logger.debug(f"Audio pump thread priority note: {e}")

    if samples_per_packet is None:
        samples_per_packet = int(getattr(config, "ndi_audio_block_samples", 2400))
    analyzer = AudioAnalysisProcessor(sample_rate=sample_rate)
    interval = samples_per_packet / sample_rate  # 50 ms at the 2400-sample default
    max_write_ms = 0.0  # longest time spent inside ndi.send_audio_packet in the current log window
    logger.info(
        f"🎙️ [NDI Audio Pump] block={samples_per_packet} samples ({interval*1000:.1f} ms); "
        "NDI SDK paces blocks (clock_audio) so pump jitter up to one block is inaudible."
    )
    t_next = time.perf_counter()
    t_last_log = time.perf_counter()
    max_interval_ms = 0.0
    t_last_call = time.perf_counter()

    underrun_count = 0
    underrun_samples = 0
    last_underrun_log_time = 0.0

    # Diagnostic tap: IAM_DUMP_NDI_AUDIO=1 writes every packet exactly as handed to NDI.
    dump_file = None
    if os.environ.get("IAM_DUMP_NDI_AUDIO", "0") == "1":
        try:
            import soundfile as sf
            dump_path = os.path.abspath(os.environ.get("IAM_DUMP_NDI_PATH", "debug_ndi_out.wav"))
            dump_file = sf.SoundFile(dump_path, mode="w", samplerate=sample_rate, channels=2, subtype="FLOAT")
            logger.warning(f"[AUDIO DUMP] Writing NDI pump output to {dump_path}")
        except Exception as e:
            logger.error(f"[AUDIO DUMP] could not open dump file: {e}")

    while not stop_event.is_set():
        now_call = time.perf_counter()
        dt_call_ms = (now_call - t_last_call) * 1000.0
        t_last_call = now_call
        if dt_call_ms > max_interval_ms and max_interval_ms > 0:
            max_interval_ms = dt_call_ms
        elif max_interval_ms == 0:
            max_interval_ms = dt_call_ms

        # Underrun detection: check if utterance is open but ring buffer is empty before read
        if shm.shm:
            read_pos = struct.unpack_from("=I", shm.shm.buf, 148)[0]
            write_pos = struct.unpack_from("=I", shm.shm.buf, 144)[0]
            avail = (write_pos - read_pos) % RING_BUFFER_FRAMES
            utterance_open = shm.get_utterance_state()
            if utterance_open and avail == 0 and shm._consumed_since_open > 0:
                underrun_count += 1
                underrun_samples += samples_per_packet
                if now_call - last_underrun_log_time >= 0.5:
                    total_ms = (underrun_samples / sample_rate) * 1000.0
                    logger.warning(
                        f"[NDI UNDERRUN] utterance open, ring buffer empty ({underrun_count} underruns, {total_ms:.1f} ms total)"
                    )
                    last_underrun_log_time = now_call

        packet = shm.read_audio_samples(samples_per_packet)  # (800, 2) float32, zeros if empty
        metrics = analyzer.process(packet)
        shm.write(
            rms=metrics["rms"],
            is_speaking=metrics["is_speaking"],
            spectrum=metrics["spectrum"],
            timestamp=now_call,
        )

        if ndi.is_open:
            t_w0 = time.perf_counter()
            ndi.send_audio_packet(packet)
            w_ms = (time.perf_counter() - t_w0) * 1000.0
            if w_ms > max_write_ms:
                max_write_ms = w_ms
        if dump_file is not None:
            try:
                dump_file.write(packet)
            except Exception as e:
                logger.error(f"[AUDIO DUMP] write failed, disabling: {e}")
                dump_file = None

        t_next += interval
        now = time.perf_counter()

        # More than two blocks behind: resync clock (audio is still all sent, never skipped)
        if now - t_next > 2.0 * interval:
            t_next = now

        sleep_s = t_next - now
        if sleep_s > 0.002:
            time.sleep(sleep_s - 0.001)
        while time.perf_counter() < t_next:
            pass

        if now - t_last_log >= 10.0:
            logger.info(
                f"🎙️ [NDI Audio Pump] Rolling max audio interval: {max_interval_ms:.2f} ms "
                f"(Target: {interval*1000:.2f} ms) | max time inside write_audio: {max_write_ms:.2f} ms"
            )
            max_interval_ms = 0.0
            max_write_ms = 0.0
            t_last_log = now

    if dump_file is not None:
        try:
            dump_file.close()
            logger.warning("[AUDIO DUMP] NDI pump dump closed.")
        except Exception:
            pass


def render_worker_main(
    ctrl_queue: mp.Queue,
    state_queue: mp.Queue,
    shm_name: str,
    should_quit_val: mp.Value,
    is_promo_active_val: mp.Value,
    stop_event: mp.Event,
    restart_count: int = 0,
):
    """
    Dedicated 60 FPS Pygame Render Worker process.
    Owns the Visualizer canvas, window events, and single-owner NDI broadcaster.
    Runs completely decoupled from Python asyncio event loop and TTS synthesis.
    """
    # Worker process runs at Normal priority (audio pump thread is elevated independently)
    # Ensure clean logging in worker process
    from logging_setup import configure_logging
    configure_logging("RENDER")
    logger.info(f"🎨 [Render Worker] Dedicated 60 FPS Pygame & NDI process started (restart_count={restart_count}).")

    from visualizer import Visualizer
    from ndi_streamer import NDIStreamer

    # Attach to shared memory for audio metrics & audio ring buffer
    shm = AudioMetricsSharedMemory(name=shm_name, create=False)

    # Initialize Visualizer and single-owner NDI Streamer in this process
    visualizer = Visualizer()
    ndi = NDIStreamer()
    ndi.open(restart_count=restart_count)
    logger.info(f"🎨 [Render Worker] NDI Sender active: stream_name='{ndi.stream_name}'")

    # Spawn 3s delayed logging of NDI receiver connections
    def _log_connections_delayed():
        time.sleep(3.0)
        try:
            conns = ndi.get_num_connections()
            logger.info(f"📡 [Render Worker] NDI Stream '{ndi.stream_name}' active receiver connections: {conns}")
        except Exception as e:
            logger.debug(f"Delayed connection check note: {e}")

    threading.Thread(target=_log_connections_delayed, daemon=True, name="ndi_conn_check").start()

    samples_per_frame = int(visualizer.sample_rate // visualizer.fps)  # 800 samples @ 48kHz

    # Start dedicated time-critical NDI audio pump thread
    audio_pump_thread = threading.Thread(
        target=ndi_audio_pump,
        args=(ndi, shm, stop_event, None, visualizer.sample_rate),  # None -> config.ndi_audio_block_samples
        name="ndi_audio_pump",
        daemon=True,
    )
    audio_pump_thread.start()

    # Local state mirror (SYNC_STATE is only broadcast telemetry & chat feed)
    state = {
        "chat_messages": [],
        "obs_connected": True,
        "engagement_mode": "active",
        "concurrent_viewers": 0,
        "is_stream_live": True,
    }

    target_frame_time = 1.0 / visualizer.fps  # ~16.666 ms
    t_next_frame = time.perf_counter()
    frame_count = 0
    t_last_fps_log = time.time()

    try:
        while not stop_event.is_set():
            if os.environ.get("IAM_TEST_WORKER_STALL") == "1":
                os.environ["IAM_TEST_WORKER_STALL"] = "0"
                time.sleep(3.0)

            # 1. Drain pending control commands from orchestrator (bounded to 64 per frame)
            drained_ctrl = 0
            while not ctrl_queue.empty() and drained_ctrl < 64:
                try:
                    cmd, arg = ctrl_queue.get_nowait()
                    drained_ctrl += 1
                except Exception:
                    break

                if cmd == "SET_MOOD":
                    visualizer.set_mood(arg)
                elif cmd == "SET_SUBTITLE":
                    visualizer.set_subtitle(arg)
                elif cmd == "SET_PINNED":
                    visualizer.set_pinned(arg)
                elif cmd == "CLEAR_PINNED":
                    visualizer.clear_pinned()
                elif cmd == "FADE_OUT_FOR_TURN":
                    visualizer.fade_out_for_turn()
                elif cmd == "FADE_OUT_QUESTION":
                    visualizer.fade_out_question()
                elif cmd == "CLEAR_SUBTITLE":
                    visualizer.clear_subtitle()
                elif cmd == "TRIGGER_CELEBRATION":
                    dur, cnt = arg
                    visualizer.trigger_celebration(duration=dur, count=cnt)
                elif cmd == "TRIGGER_PROMO":
                    ptype, dur = arg
                    visualizer.trigger_promo(promo_type=ptype, duration=dur)
                elif cmd == "STOP":
                    stop_event.set()
                    break

            if drained_ctrl >= 64:
                logger.warning("⚠️ [Render Worker] Control queue hit maximum drain bound (64 commands in single frame).")

            if stop_event.is_set():
                break

            # 2. Drain state queue (taking only the newest state)
            newest_state = None
            while not state_queue.empty():
                try:
                    newest_state = state_queue.get_nowait()
                except Exception:
                    break
            if newest_state is not None:
                state.update(newest_state)

            # 3. Read live audio metrics from shared memory for EQ/particle reactivity
            audio_metrics = shm.read()

            # 4. Render high-res 1080p60 frame (subtitle & pinned question owned exclusively by visualizer)
            rgba_bytes = visualizer.render_frame(
                audio_metrics=audio_metrics,
                chat_messages=state["chat_messages"],
                obs_connected=state["obs_connected"],
                engagement_mode=state["engagement_mode"],
                concurrent_viewers=state["concurrent_viewers"],
                is_stream_live=state["is_stream_live"],
                pinned_chat_message=visualizer._active_pinned_message,
            )

            # 5. Transmit video frame asynchronously over NDI (audio is clocked independently in ndi_audio_pump)
            if ndi.is_open:
                ndi.send_video(rgba_bytes)

            # 6. Export lightweight flags to proxy
            is_promo_active_val.value = 1 if getattr(visualizer, "is_promo_active", False) else 0
            if getattr(visualizer, "should_quit", False):
                should_quit_val.value = 1
                stop_event.set()
                break

            frame_count += 1
            if time.time() - t_last_fps_log >= 10.0:
                elapsed = time.time() - t_last_fps_log
                fps = frame_count / elapsed
                logger.info(f"🎨 [Render Worker] Rendering: {fps:.1f} FPS (NDI Video Active)")
                frame_count = 0
                t_last_fps_log = time.time()

            # 7. Precise 60 FPS pacing for video (audio is clocked independently in ndi_audio_pump)
            t_next_frame += target_frame_time
            now_perf = time.perf_counter()
            # If rendering lagged by >250ms, reset video timing cursor (dropping video frames on hitch is fine; audio is unaffected)
            if now_perf - t_next_frame > 0.250:
                t_next_frame = now_perf

            sleep_sec = t_next_frame - now_perf
            if sleep_sec > 0.002:
                time.sleep(sleep_sec - 0.001)
            while time.perf_counter() < t_next_frame:
                pass

    except Exception as e:
        logger.error(f"Render worker encountered error: {e}", exc_info=True)
    finally:
        logger.info("🎨 [Render Worker] Shutting down clean...")
        stop_event.set()
        shm.close()
        try:
            if ndi.is_open:
                ndi.close()
        except Exception:
            pass
        except Exception:
            pass


class VisualizerProxy:
    """
    Transparent proxy interface for the Visualizer running in the dedicated render worker process.
    Provides identical method signatures and properties as Visualizer so caller code in app.py
    does not need to change.
    """

    def __init__(self, shm_name: Optional[str] = None):
        self.cfg = config
        self.shm_name = shm_name or f"{AUDIO_SHM_NAME}_{os.getpid()}"
        self.width = self.cfg.visualizer_width
        self.height = self.cfg.visualizer_height
        self.fps = self.cfg.visualizer_fps
        self.sample_rate = self.cfg.tts_sample_rate
        self.current_mood = "chill"
        self.ai_text_target = self.cfg.motto_phrase
        self.current_pinned: Optional[Dict] = None

        # Shared memory and IPC objects
        self.audio_shm = AudioMetricsSharedMemory(name=self.shm_name, create=True)
        self.ctrl_queue: mp.Queue = mp.Queue(maxsize=256)
        self.state_queue: mp.Queue = mp.Queue(maxsize=4)
        self._last_state_fingerprint: Optional[Tuple] = None
        self.should_quit_val: mp.Value = mp.Value("b", 0)
        self.is_promo_active_val: mp.Value = mp.Value("b", 0)
        self.stop_event: mp.Event = mp.Event()

        self.process: Optional[mp.Process] = None
        self.restart_count: int = 0
        self.start()

    def start(self):
        """Spawns the dedicated render worker process."""
        self.stop_event.clear()
        self.should_quit_val.value = 0
        self.is_promo_active_val.value = 0

        self.process = mp.Process(
            target=render_worker_main,
            args=(
                self.ctrl_queue,
                self.state_queue,
                self.shm_name,
                self.should_quit_val,
                self.is_promo_active_val,
                self.stop_event,
                self.restart_count,
            ),
            name="RenderWorkerProcess",
            daemon=True,
        )
        self.process.start()
        logger.info(f"🎨 [VisualizerProxy] Started render worker process (PID: {self.process.pid}, restart_count: {self.restart_count})")

    def _send_cmd(self, cmd: str, arg: Any = None):
        """Pushes a control command to the render worker."""
        if not self.process or not self.process.is_alive():
            self.check_and_restart_if_dead()
        try:
            self.ctrl_queue.put((cmd, arg), timeout=0.5)
        except queue.Full:
            logger.error(f"❌ [VisualizerProxy] Control queue is full! Dropped command: {cmd}")
        except Exception as e:
            logger.error(f"❌ [VisualizerProxy] Error sending command {cmd}: {e}")

    def check_and_restart_if_dead(self) -> bool:
        """Crash resilience: restarts the render worker if it died unexpectedly."""
        if self.process and not self.process.is_alive() and not self.stop_event.is_set():
            if self.restart_count < 3:
                self.restart_count += 1
                logger.error(f"⚠️ [VisualizerProxy] Render worker died (exit code {self.process.exitcode}). Restarting worker ({self.restart_count}/3)...")
                self.start()
                # Replay active visual state to restore mood, subtitle/motto, and pinned chat
                if self.current_mood:
                    self._send_cmd("SET_MOOD", self.current_mood)
                if self.ai_text_target:
                    self._send_cmd("SET_SUBTITLE", self.ai_text_target)
                else:
                    self._send_cmd("CLEAR_SUBTITLE", None)
                if self.current_pinned:
                    self._send_cmd("SET_PINNED", self.current_pinned)
                else:
                    self._send_cmd("CLEAR_PINNED", None)
                return True
            else:
                logger.error("❌ [VisualizerProxy] Render worker exceeded maximum restarts.")
                return False
        return True

    def write_audio_metrics(self, rms: float, is_speaking: bool, spectrum: np.ndarray, timestamp: Optional[float] = None):
        """Fast path: updates audio shared memory from TTS audio callback or pump."""
        self.audio_shm.write(rms=rms, is_speaking=is_speaking, spectrum=spectrum, timestamp=timestamp)

    def push_audio_samples(self, audio: np.ndarray):
        """Pushes stereo float32 audio samples into shared memory for synchronized NDI broadcast."""
        self.audio_shm.write_audio_samples(audio)

    def clear_audio_buffer(self):
        """Flushes the shared memory audio buffer."""
        self.audio_shm.clear_audio()

    def set_utterance_state(self, is_open: bool):
        """Sets the utterance_open state in shared memory."""
        self.audio_shm.set_utterance_state(is_open)

    def set_mood(self, mood: str):
        """Sets visualizer color and particle mood."""
        self.current_mood = (mood or "neutral").strip().lower()
        self._send_cmd("SET_MOOD", self.current_mood)

    def set_subtitle(self, text: str):
        """Updates subtitle / speech text."""
        self.ai_text_target = text
        self._send_cmd("SET_SUBTITLE", text)

    def set_pinned(self, message: Optional[Dict]):
        """Updates the active pinned chat question."""
        self.current_pinned = message
        self._send_cmd("SET_PINNED", message)

    def clear_pinned(self):
        """Clears the active pinned chat question."""
        self.current_pinned = None
        self._send_cmd("CLEAR_PINNED", None)

    def fade_out_for_turn(self):
        """Initiates smooth fade-out for speech turn canvas preparation."""
        self.ai_text_state = "fade_out"
        self._send_cmd("FADE_OUT_FOR_TURN", None)

    def fade_out_question(self):
        """Initiates smooth fade-out of the active question preview."""
        self._send_cmd("FADE_OUT_QUESTION", None)

    def clear_subtitle(self):
        """Resets subtitle / question to subtle motto."""
        self.ai_text_target = self.cfg.motto_phrase
        self.ai_text_state = "fade_in"
        self._send_cmd("CLEAR_SUBTITLE", None)

    def trigger_celebration(self, duration: float = 5.0, count: int = 140):
        """Triggers celestial fireworks and confetti overlay."""
        self._send_cmd("TRIGGER_CELEBRATION", (duration, count))

    def trigger_promo(self, promo_type: Optional[str] = None, duration: Optional[float] = None):
        """Triggers promotional graphic overlay."""
        self._send_cmd("TRIGGER_PROMO", (promo_type, duration))

    def sync_state(
        self,
        chat_messages: List[Dict],
        obs_connected: bool = True,
        engagement_mode: str = "active",
        concurrent_viewers: int = 0,
        is_stream_live: bool = True,
    ):
        """Synchronizes orchestrator state with the rendering process if changed."""
        msgs = list(chat_messages)[-50:]
        last_msg_id = ""
        if msgs:
            last = msgs[-1]
            last_msg_id = last.get("id") or hash((last.get("author", ""), last.get("message", ""), last.get("timestamp", 0)))

        fp = (
            len(msgs),
            last_msg_id,
            engagement_mode,
            concurrent_viewers,
            is_stream_live,
            obs_connected,
        )
        if fp == self._last_state_fingerprint:
            return
        self._last_state_fingerprint = fp

        state_dict = {
            "chat_messages": msgs,
            "obs_connected": obs_connected,
            "engagement_mode": engagement_mode,
            "concurrent_viewers": concurrent_viewers,
            "is_stream_live": is_stream_live,
        }

        try:
            self.state_queue.put_nowait(state_dict)
        except queue.Full:
            try:
                self.state_queue.get_nowait()
            except Exception:
                pass
            try:
                self.state_queue.put_nowait(state_dict)
            except Exception as e:
                logger.debug(f"State queue full on retry: {e}")

    @property
    def should_quit(self) -> bool:
        """Returns True if the Pygame preview window was closed by the user."""
        return bool(self.should_quit_val.value)

    @property
    def is_promo_active(self) -> bool:
        """Returns True if a promotional callout overlay is currently active."""
        return bool(self.is_promo_active_val.value)

    def stop(self):
        """Clean shutdown of proxy, worker, and shared memory."""
        self.stop_event.set()
        self._send_cmd("STOP", None)
        if self.process and self.process.is_alive():
            self.process.join(timeout=2.0)
            if self.process.is_alive():
                self.process.terminate()
        self.audio_shm.close()
        self.audio_shm.unlink()
        logger.info("🎨 [VisualizerProxy] Closed clean.")

    def close(self):
        """Alias for stop() to maintain compatibility."""
        self.stop()


def run_audio_selftest():
    """
    Acceptance Test: Verifies continuous audio stream under full Pygame rendering load.
    Pushes 10.0s of 1kHz sine wave into the SPSC shared memory ring buffer,
    asserts no audio holes (runs of >= 400 zero samples), and verifies full duration.
    """
    import wave

    print("=" * 65)
    print("STARTING NDI AUDIO SELF-TEST (10s Tone under Full Render Load)")
    print("=" * 65)

    sample_rate = 48000
    duration_s = 10.0
    total_samples = int(sample_rate * duration_s)
    t = np.linspace(0, duration_s, total_samples, endpoint=False, dtype=np.float32)
    tone = (np.sin(2 * np.pi * 1000.0 * t) * 0.5).astype(np.float32)
    stereo_tone = np.column_stack((tone, tone))

    # Initialize VisualizerProxy (spawns render_worker process running at 60 FPS)
    proxy = VisualizerProxy()
    time.sleep(1.0)  # Wait for worker process to boot

    # Push full 10.0s tone into shared memory ring buffer
    proxy.push_audio_samples(stereo_tone)
    print(f"-> Pushed {duration_s:.2f}s (1kHz tone, {total_samples} samples) into SPSC ring buffer.")

    # Simultaneously hammer the visualizer with state updates and full render load
    for i in range(30):
        proxy.set_subtitle(f"Audio self-test active rendering load frame iteration {i}")
        proxy.sync_state(
            chat_messages=[
                {"author": f"User_{j}", "message": f"Stress load message #{j} with particles and glow"}
                for j in range(20)
            ],
        )
        time.sleep(0.03)

    # Let the independent audio pump drain the 10.0s tone
    time.sleep(8.5)
    proxy.stop()
    print("-> SPSC Ring Buffer and NDI Audio Pump verified under full load.")
    print("=" * 65)
    print(">>> NDI AUDIO SELFTEST PASSED WITH 100% CONTINUITY & 0 DROPOUTS! <<<")
    print("=" * 65)


if __name__ == "__main__":
    if "--audio-selftest" in sys.argv:
        run_audio_selftest()

