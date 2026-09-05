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
import struct
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from config import config

logger = logging.getLogger("render_worker")

# Shared memory format:
# Shared memory format:
# offset 0:    float32 rms (4 bytes)
# offset 4:    uint8 is_speaking (1 byte)
# offset 5:    uint8 padding [3 bytes]
# offset 8:    float32 spectrum [32 bins * 4 bytes = 128 bytes]
# offset 136:  float64 timestamp (8 bytes)
# offset 144:  uint32 write_pos (4 bytes)
# offset 148:  uint32 read_pos (4 bytes)
# offset 152:  uint32 available_samples (4 bytes)
# offset 156:  uint8 padding [4 bytes]
# offset 160:  float32 audio_ring_buffer [RING_BUFFER_FRAMES * 2 channels * 4 bytes]
# Sized to 120 seconds (5,760,000 frames @ 48kHz stereo = ~46 MB) to effortlessly hold full-length AI reflections & answers
RING_BUFFER_FRAMES = 48000 * 120
AUDIO_METRICS_HEADER_SIZE = 160
AUDIO_DATA_BYTE_SIZE = RING_BUFFER_FRAMES * 2 * 4
AUDIO_SHM_SIZE = AUDIO_METRICS_HEADER_SIZE + AUDIO_DATA_BYTE_SIZE
AUDIO_SHM_NAME = "iam_audio_metrics_shm"


class AudioMetricsSharedMemory:
    """Fast zero-copy shared memory interface for real-time audio reactivity and audio transmission."""

    def __init__(self, name: str = AUDIO_SHM_NAME, create: bool = False):
        self.name = name
        self.create = create
        self.shm: Optional[shared_memory.SharedMemory] = None

        if create:
            try:
                self.shm = shared_memory.SharedMemory(name=self.name, create=True, size=AUDIO_SHM_SIZE)
            except FileExistsError:
                try:
                    # Stale segment on Windows may persist with old size; recreate if size differs
                    existing = shared_memory.SharedMemory(name=self.name, create=False)
                    if existing.size != AUDIO_SHM_SIZE:
                        existing.close()
                        existing.unlink()
                        self.shm = shared_memory.SharedMemory(name=self.name, create=True, size=AUDIO_SHM_SIZE)
                    else:
                        self.shm = existing
                except Exception as e:
                    logger.warning(f"Could not attach/recreate shared memory {self.name}: {e}")
                    self.shm = None
            except Exception as e:
                logger.warning(f"Could not create shared memory {self.name}: {e}")
                self.shm = None

            if self.shm is not None:
                # Initialize with zeroes
                self.shm.buf[:AUDIO_SHM_SIZE] = b"\x00" * AUDIO_SHM_SIZE
        else:
            try:
                self.shm = shared_memory.SharedMemory(name=self.name, create=False)
            except Exception as e:
                logger.debug(f"Shared memory attach note ({self.name}): {e}")
                self.shm = None

    def write(self, rms: float, is_speaking: bool, spectrum: np.ndarray, timestamp: Optional[float] = None):
        """Writes live audio metrics from TTS audio pump into shared memory."""
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

    def write_audio_samples(self, audio: np.ndarray):
        """Appends stereo float32 audio samples into the shared memory ring buffer."""
        if not self.shm or audio is None or len(audio) == 0:
            return
        if audio.ndim == 1:
            audio = np.column_stack((audio, audio))
        elif audio.shape[1] == 1:
            audio = np.column_stack((audio[:, 0], audio[:, 0]))
        audio = np.ascontiguousarray(audio, dtype=np.float32)

        n_samples = len(audio)
        buf = self.shm.buf
        write_pos, read_pos, avail = struct.unpack_from("=III", buf, 144)

        audio_mem = np.frombuffer(
            buf[AUDIO_METRICS_HEADER_SIZE : AUDIO_METRICS_HEADER_SIZE + AUDIO_DATA_BYTE_SIZE],
            dtype=np.float32,
        ).reshape((RING_BUFFER_FRAMES, 2))

        if n_samples >= RING_BUFFER_FRAMES:
            # Audio clip exceeds entire ring buffer capacity; preserve most recent 2 minutes
            audio = audio[-RING_BUFFER_FRAMES:]
            n_samples = RING_BUFFER_FRAMES
            audio_mem[:] = audio
            write_pos = 0
            read_pos = 0
            avail = RING_BUFFER_FRAMES
            struct.pack_into("=III", buf, 144, write_pos, read_pos, avail)
            return

        if write_pos + n_samples <= RING_BUFFER_FRAMES:
            audio_mem[write_pos : write_pos + n_samples] = audio
        else:
            part1 = RING_BUFFER_FRAMES - write_pos
            part2 = n_samples - part1
            audio_mem[write_pos : RING_BUFFER_FRAMES] = audio[:part1]
            audio_mem[:part2] = audio[part1:]

        new_write_pos = (write_pos + n_samples) % RING_BUFFER_FRAMES
        new_avail = min(RING_BUFFER_FRAMES, avail + n_samples)
        struct.pack_into("=III", buf, 144, new_write_pos, read_pos, new_avail)

    def read_audio_samples(self, num_samples: int = 800) -> np.ndarray:
        """Reads exactly num_samples stereo float32 samples from the shared memory ring buffer."""
        if not self.shm:
            return np.zeros((num_samples, 2), dtype=np.float32)

        buf = self.shm.buf
        write_pos, read_pos, avail = struct.unpack_from("=III", buf, 144)

        out_audio = np.zeros((num_samples, 2), dtype=np.float32)
        to_read = min(num_samples, avail)

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
            new_avail = max(0, avail - to_read)
            struct.pack_into("=III", buf, 144, write_pos, new_read_pos, new_avail)

        return out_audio

    def clear_audio(self):
        """Resets the shared memory audio ring buffer."""
        if not self.shm:
            return
        buf = self.shm.buf
        struct.pack_into("=III", buf, 144, 0, 0, 0)
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


def render_worker_main(
    cmd_queue: mp.Queue,
    shm_name: str,
    should_quit_val: mp.Value,
    is_promo_active_val: mp.Value,
    stop_event: mp.Event,
):
    """
    Dedicated 60 FPS Pygame Render Worker process.
    Owns the Visualizer canvas, window events, and single-owner NDI broadcaster.
    Runs completely decoupled from Python asyncio event loop and TTS synthesis.
    """
    # Set process title and Windows process priority for rock-solid 60 FPS cadence
    try:
        import win32api, win32process, win32con
        pid = win32api.GetCurrentProcessId()
        handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, True, pid)
        win32process.SetPriorityClass(handle, win32process.ABOVE_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass

    # Ensure clean logging in worker process
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [RENDER-WORKER] %(message)s",
        datefmt="%H:%M:%S",
    )
    logger.info("🎨 [Render Worker] Dedicated 60 FPS Pygame & NDI process started.")

    from visualizer import Visualizer
    from ndi_streamer import NDIStreamer

    # Attach to shared memory for audio metrics & audio ring buffer
    shm = AudioMetricsSharedMemory(name=shm_name, create=False)

    # Initialize Visualizer and single-owner NDI Streamer in this process
    visualizer = Visualizer()
    ndi = NDIStreamer()
    ndi.open()

    # Local state mirror
    state = {
        "chat_messages": [],
        "pinned_chat_message": None,
        "ai_subtitle": "",
        "obs_connected": True,
        "engagement_mode": "active",
        "concurrent_viewers": 0,
        "is_stream_live": True,
    }

    target_frame_time = 1.0 / visualizer.fps  # ~16.666 ms
    samples_per_frame = int(visualizer.sample_rate // visualizer.fps)  # 800 samples per 60fps frame @ 48kHz
    t_next_frame = time.perf_counter()
    frame_count = 0
    t_last_fps_log = time.time()

    try:
        while not stop_event.is_set():
            # 1. Drain all pending control commands from orchestrator
            while not cmd_queue.empty():
                try:
                    cmd, arg = cmd_queue.get_nowait()
                except Exception:
                    break

                if cmd == "SET_MOOD":
                    visualizer.set_mood(arg)
                elif cmd == "SET_SUBTITLE":
                    visualizer.set_subtitle(arg)
                    state["ai_subtitle"] = arg
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
                elif cmd == "SYNC_STATE":
                    state.update(arg)
                elif cmd == "STOP":
                    stop_event.set()
                    break

            if stop_event.is_set():
                break

            # 2. Read live audio metrics and synchronized frame audio packet from shared memory
            audio_metrics = shm.read()
            audio_packet = shm.read_audio_samples(samples_per_frame)

            # 3. Render high-res 1080p60 frame
            rgba_bytes = visualizer.render_frame(
                audio_metrics=audio_metrics,
                chat_messages=state["chat_messages"],
                ai_subtitle=state["ai_subtitle"],
                obs_connected=state["obs_connected"],
                engagement_mode=state["engagement_mode"],
                concurrent_viewers=state["concurrent_viewers"],
                is_stream_live=state["is_stream_live"],
                pinned_chat_message=state["pinned_chat_message"],
            )

            # 4. Transmit frame-locked synchronized video + audio atomically over NDI
            if ndi.is_open:
                ndi.send_frame_sync(rgba_bytes, audio_packet)

            # 5. Export lightweight flags to proxy
            is_promo_active_val.value = 1 if getattr(visualizer, "is_promo_active", False) else 0
            if getattr(visualizer, "should_quit", False):
                should_quit_val.value = 1
                stop_event.set()
                break

            frame_count += 1
            if time.time() - t_last_fps_log >= 10.0:
                elapsed = time.time() - t_last_fps_log
                fps = frame_count / elapsed
                logger.info(f"🎨 [Render Worker] Rendering: {fps:.1f} FPS (NDI Video & Audio Active)")
                frame_count = 0
                t_last_fps_log = time.time()

            # 6. Precise 60 FPS pacing with clock drift reset
            t_next_frame += target_frame_time
            now_perf = time.perf_counter()
            # If render worker lagged by >50ms (3+ frames), reset timing cursor to current clock to avoid hitch bursts
            if now_perf - t_next_frame > 0.050:
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
        shm.close()
        try:
            if ndi.is_open:
                ndi.close()
        except Exception:
            pass


class VisualizerProxy:
    """
    Transparent proxy interface for the Visualizer running in the dedicated render worker process.
    Provides identical method signatures and properties as Visualizer so caller code in app.py
    does not need to change.
    """

    def __init__(self, shm_name: str = AUDIO_SHM_NAME):
        self.cfg = config
        self.shm_name = shm_name
        self.width = self.cfg.visualizer_width
        self.height = self.cfg.visualizer_height
        self.fps = self.cfg.visualizer_fps
        self.sample_rate = getattr(self.cfg, "tts_sample_rate", 48000)
        self.current_mood = "chill"
        self.ai_text_target = getattr(self.cfg, "motto_phrase", "Everything is perfect.")

        # Shared memory and IPC objects
        self.audio_shm = AudioMetricsSharedMemory(name=self.shm_name, create=True)
        self.cmd_queue: mp.Queue = mp.Queue(maxsize=1000)
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
                self.cmd_queue,
                self.shm_name,
                self.should_quit_val,
                self.is_promo_active_val,
                self.stop_event,
            ),
            name="RenderWorkerProcess",
            daemon=True,
        )
        self.process.start()
        logger.info(f"🎨 [VisualizerProxy] Started render worker process (PID: {self.process.pid})")

    def _send_cmd(self, cmd: str, arg: Any = None):
        """Pushes a control command to the render worker."""
        if not self.process or not self.process.is_alive():
            self.check_and_restart_if_dead()
        try:
            self.cmd_queue.put_nowait((cmd, arg))
        except Exception:
            pass

    def check_and_restart_if_dead(self) -> bool:
        """Crash resilience: restarts the render worker if it died unexpectedly."""
        if self.process and not self.process.is_alive() and not self.stop_event.is_set():
            if self.restart_count < 3:
                self.restart_count += 1
                logger.error(f"⚠️ [VisualizerProxy] Render worker died (exit code {self.process.exitcode}). Restarting worker ({self.restart_count}/3)...")
                self.start()
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

    def set_mood(self, mood: str):
        """Sets visualizer color and particle mood."""
        self.current_mood = (mood or "neutral").strip().lower()
        self._send_cmd("SET_MOOD", self.current_mood)

    def set_subtitle(self, text: str):
        """Updates subtitle / speech text."""
        self.ai_text_target = text
        self._send_cmd("SET_SUBTITLE", text)

    def fade_out_for_turn(self):
        """Initiates smooth fade-out for speech turn canvas preparation."""
        self.ai_text_state = "fade_out"
        self._send_cmd("FADE_OUT_FOR_TURN", None)

    def fade_out_question(self):
        """Initiates smooth fade-out of the active question preview."""
        self._send_cmd("FADE_OUT_QUESTION", None)

    def clear_subtitle(self):
        """Resets subtitle / question to subtle motto."""
        self.ai_text_target = getattr(self.cfg, "motto_phrase", "Everything is perfect.")
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
        pinned_chat_message: Optional[Dict] = None,
        obs_connected: bool = True,
        engagement_mode: str = "active",
        concurrent_viewers: int = 0,
        is_stream_live: bool = True,
        ai_subtitle: str = "",
    ):
        """Synchronizes orchestrator state with the rendering process."""
        state_dict = {
            "chat_messages": list(chat_messages)[-50:],
            "pinned_chat_message": pinned_chat_message,
            "obs_connected": obs_connected,
            "engagement_mode": engagement_mode,
            "concurrent_viewers": concurrent_viewers,
            "is_stream_live": is_stream_live,
            "ai_subtitle": ai_subtitle,
        }
        self._send_cmd("SYNC_STATE", state_dict)

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
