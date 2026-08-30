"""
Audio Synthesis Engine for AI Live Stream Co-Host.
Synthesizes speech into high-quality 48kHz stereo PCM audio,
buffers samples in synchronization with 60fps video frames (800 samples/frame),
and computes real-time FFT / RMS amplitude metrics for the visualizer.
"""

import asyncio
import io
import logging
import re
import threading
import time
from typing import Dict, Optional, Tuple

import aiohttp
import numpy as np
import scipy.signal
import soundfile as sf

from config import config

# Optional edge-tts import
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [TTS-ENGINE] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("tts_engine")


class TTSEngine:
    """Handles text-to-speech generation, high-precision frame slicing, and audio reactivity analysis."""

    def __init__(self):
        self.cfg = config
        self.sample_rate = self.cfg.tts_sample_rate  # 48000
        self.channels = 2  # Stereo
        self.fps = self.cfg.visualizer_fps  # 60
        self.samples_per_frame = self.sample_rate // self.fps  # 800 samples/frame

        # Dual-Backend Configuration (ChatterBox Turbo on LAN / Edge-TTS Local Fallback)
        self.tts_backend = getattr(self.cfg, "tts_backend", "chatterbox").lower()
        self.server_url = getattr(self.cfg, "tts_server_url", "http://192.168.0.115:8123").rstrip("/")
        self.reference_voice = getattr(self.cfg, "tts_reference_voice", "cohost.wav")
        self.timeout_floor = getattr(self.cfg, "tts_request_timeout_floor", 5.0)
        self.timeout_ceiling = getattr(self.cfg, "tts_request_timeout_ceiling", 30.0)
        self.exaggeration_default = getattr(self.cfg, "tts_exaggeration_default", 0.5)
        self.mood_exaggeration_map = getattr(self.cfg, "tts_mood_exaggeration_map", {})

        # Active backend state (tracks failover from chatterbox -> edge)
        self.active_backend = self.tts_backend
        self._health_checked = False
        self._warned_unhealthy = False

        # Edge-TTS settings
        self.voice = self.cfg.tts_voice
        self.pitch = self.cfg.tts_pitch
        self.rate = self.cfg.tts_rate

        # Dual independent sample buffers for NDI and Local Windows Audio
        self._audio_buffer_ndi = np.zeros((0, 2), dtype=np.float32)
        self._audio_buffer_local = np.zeros((0, 2), dtype=np.float32)
        self._last_ndi_pop_time = 0.0
        self._last_local_pop_time = 0.0
        self._buffer_lock = threading.RLock()

        # FFT & Dynamics Analysis State
        self.num_spectrum_bands = 32
        self.smoothed_spectrum = np.zeros(self.num_spectrum_bands, dtype=np.float32)
        self.current_rms = 0.0
        self.is_speaking = False
        self.last_audio_tick = time.time()

        # Analysis window (sliding 1024-sample window for smooth FFT)
        self._analysis_window = np.zeros((1024, 2), dtype=np.float32)
        self._hanning_window = np.hanning(1024).astype(np.float32)

        # Precompute FFT frequency band slice indices (40Hz to 16kHz) for ultra-fast vectorization
        fft_freqs = np.fft.rfftfreq(1024, 1.0 / self.sample_rate)
        min_freq = 40.0
        max_freq = 16000.0
        freq_bins = np.logspace(
            np.log10(min_freq), np.log10(max_freq), self.num_spectrum_bands + 1
        )
        self._band_slices = []
        for i in range(self.num_spectrum_bands):
            f_low = freq_bins[i]
            f_high = freq_bins[i + 1]
            indices = np.where((fft_freqs >= f_low) & (fft_freqs < f_high))[0]
            if len(indices) > 0:
                self._band_slices.append((int(indices[0]), int(indices[-1]) + 1))
            else:
                self._band_slices.append((0, 0))

    def _decode_and_resample(self, audio_bytes: bytes) -> np.ndarray:
        """Worker function executed in worker thread for zero-latency audio decoding."""
        with io.BytesIO(audio_bytes) as bio:
            data, src_sr = sf.read(bio, dtype="float32")

        # Convert mono to stereo if necessary
        if data.ndim == 1:
            data = np.column_stack((data, data))
        elif data.shape[1] == 1:
            data = np.column_stack((data[:, 0], data[:, 0]))

        # High-quality polyphase FIR resampling (e.g. 24kHz -> 48kHz is 2/1)
        if src_sr != self.sample_rate:
            gcd = np.gcd(int(self.sample_rate), int(src_sr))
            up = int(self.sample_rate // gcd)
            down = int(src_sr // gcd)
            data = scipy.signal.resample_poly(data, up, down, axis=0).astype(np.float32)

        # Prevent digital clipping: normalize peaks if exceeding 0.95
        max_val = float(np.max(np.abs(data)))
        if max_val > 0.95:
            data = (data / max_val) * 0.90

        # Apply subtle fade-in / fade-out (5ms = 240 samples) to eliminate click artifacts
        fade_samples = min(240, len(data) // 4)
        if fade_samples > 0:
            fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)[:, None]
            fade_out = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)[:, None]
            data[:fade_samples] *= fade_in
            data[-fade_samples:] *= fade_out

        return data.astype(np.float32)

    async def check_health(self) -> bool:
        """
        Queries the remote ChatterBox Turbo server health endpoint on GAMER.
        If unreachable, logs a single warning and sets active backend to 'edge'.
        """
        if self.tts_backend != "chatterbox":
            self.active_backend = "edge"
            return True

        url = f"{self.server_url}/health"
        try:
            timeout = aiohttp.ClientTimeout(total=2.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.active_backend = "chatterbox"
                        self._health_checked = True
                        logger.info(
                            f"✅ [TTS-ENGINE] ChatterBox Turbo server at {self.server_url} is ONLINE "
                            f"(warm: {data.get('warm')}, VRAM: {data.get('vram_used_mb')}MB)"
                        )
                        return True
                    else:
                        raise aiohttp.ClientError(f"Status {resp.status}")
        except Exception as e:
            if not self._warned_unhealthy:
                logger.warning(
                    f"⚠️ [TTS-ENGINE] ChatterBox Turbo server at {self.server_url} is UNREACHABLE ({e}). "
                    f"Falling back to local Edge-TTS backend for session."
                )
                self._warned_unhealthy = True
            self.active_backend = "edge"
            self._health_checked = True
            return False

    async def _synthesize_chatterbox(self, clean_text: str, exaggeration: float) -> Optional[np.ndarray]:
        """Synthesizes speech via remote ChatterBox Turbo GPU inference server."""
        url = f"{self.server_url}/synthesize"
        # Dynamic timeout proportional to text length with floor/ceiling
        calc_timeout = min(self.timeout_ceiling, max(self.timeout_floor, len(clean_text) * 0.08))
        timeout = aiohttp.ClientTimeout(total=calc_timeout)
        payload = {
            "text": clean_text,
            "voice": self.reference_voice,
            "exaggeration": exaggeration,
            "cfg_weight": 0.5,
            "format": "wav",
        }

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        raw_wav = await resp.read()
                        if not raw_wav:
                            return None
                        # Zero-latency polyphase FIR decoding & resampling in worker thread
                        data = await asyncio.to_thread(self._decode_and_resample, raw_wav)
                        logger.info(
                            f"[Chatterbox] Synthesized {len(data)/self.sample_rate:.2f}s audio "
                            f"(exaggeration={exaggeration:.2f}) from {self.server_url}"
                        )
                        return data
                    else:
                        err_text = await resp.text()
                        logger.warning(f"Chatterbox server returned error HTTP {resp.status}: {err_text}")
                        return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning(f"Chatterbox connection/timeout to {self.server_url} ({e}); falling back to local edge-tts.")
            return None
        except Exception as e:
            logger.error(f"Unexpected error calling Chatterbox server: {e}", exc_info=True)
            return None

    async def _synthesize_edge_tts(self, clean_text: str) -> np.ndarray:
        """Synthesizes speech locally via Microsoft edge-tts."""
        if not EDGE_TTS_AVAILABLE:
            logger.warning("edge-tts not available, generating synthesized tone placeholder")
            return self._generate_sine_placeholder(len(clean_text) * 0.06)

        try:
            communicate = edge_tts.Communicate(
                clean_text,
                self.voice,
                pitch=self.pitch,
                rate=self.rate,
            )

            audio_bytes = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_bytes.extend(chunk["data"])

            if not audio_bytes:
                logger.warning("No audio bytes received from edge-tts")
                return np.zeros((0, 2), dtype=np.float32)

            data = await asyncio.to_thread(self._decode_and_resample, bytes(audio_bytes))
            logger.info(f"[Edge-TTS] Synthesized {len(data)/self.sample_rate:.2f}s of 48kHz stereo audio")
            return data
        except Exception as e:
            logger.error(f"Error during edge-tts synthesis: {e}")
            return self._generate_sine_placeholder(len(clean_text) * 0.06)

    async def synthesize(self, text: str) -> np.ndarray:
        """
        Synthesize text into 48kHz stereo float32 PCM numpy array.
        Routes to ChatterBox Turbo GPU server or local Edge-TTS failback with mood mapping.
        """
        # Parse mood tag before cleaning
        mood_match = re.search(r"\[MOOD:\s*([a-zA-Z_-]+)\]", text, flags=re.IGNORECASE)
        active_mood = mood_match.group(1).lower() if mood_match else "neutral"
        exaggeration = self.mood_exaggeration_map.get(active_mood, self.exaggeration_default)

        # Clean text of mood tags, markdown, and '@' symbols before speech synthesis
        clean_text = re.sub(r"\[MOOD:\s*[a-zA-Z_-]+\]", "", text, flags=re.IGNORECASE).strip()
        clean_text = re.sub(r"@([a-zA-Z0-9_]+)", r"\1", clean_text)
        clean_text = clean_text.replace("*", "").replace("`", "").strip()

        if not clean_text:
            return np.zeros((0, 2), dtype=np.float32)

        logger.info(f"Synthesizing speech ({len(clean_text)} chars, mood={active_mood}): '{clean_text[:60]}...'")

        # 1. Primary: Remote Chatterbox Turbo GPU inference server
        if self.active_backend == "chatterbox":
            data = await self._synthesize_chatterbox(clean_text, exaggeration)
            if data is not None and len(data) > 0:
                return data
            # If Chatterbox failed, fall through to Edge-TTS fallback
            logger.info(f"Failing over to local Edge-TTS for utterance '{clean_text[:35]}...'")

        # 2. Fallback / Local Mode: Microsoft edge-tts
        data = await self._synthesize_edge_tts(clean_text)
        if len(data) > 0:
            return data

        # 3. Final safety: Sine placeholder (never silent)
        return self._generate_sine_placeholder(len(clean_text) * 0.06)

    def _generate_sine_placeholder(self, duration_sec: float) -> np.ndarray:
        """Fallback beep / harmonic synthesizer."""
        t = np.linspace(0, duration_sec, int(self.sample_rate * duration_sec), endpoint=False)
        sine = 0.2 * np.sin(2 * np.pi * 440.0 * t) * np.exp(-t * 2)
        sine = sine.astype(np.float32)
        return np.column_stack((sine, sine))

    @property
    def remaining_speech_duration(self) -> float:
        """Returns the duration in seconds of audio currently queued in the playback buffer."""
        with self._buffer_lock:
            return len(self._audio_buffer_ndi) / self.sample_rate

    def clear_audio_buffer(self):
        """Immediately flushes all queued speech samples and resets speaking state."""
        with self._buffer_lock:
            self._audio_buffer_ndi = np.zeros((0, 2), dtype=np.float32)
            self._audio_buffer_local = np.zeros((0, 2), dtype=np.float32)
            self.is_speaking = False

    async def wait_until_speech_completed(self, poll_interval: float = 0.05, timeout: Optional[float] = None):
        """Asynchronously waits until all buffered speech audio has finished broadcasting out through NDI/audio."""
        t0 = time.time()
        # Brief initial sleep so the pop_audio_packet / pop_local_audio threads register playback start
        await asyncio.sleep(0.15)

        expected_dur = getattr(self, "last_synthesized_duration", 0.0)
        # Cap wait timeout to avoid hanging indefinitely if a playback backend is inactive
        max_wait = (expected_dur + 2.5) if expected_dur > 0 else (timeout or 25.0)
        if timeout:
            max_wait = min(max_wait, timeout)

        while time.time() - t0 < max_wait:
            now = time.time()
            with self._buffer_lock:
                ndi_active = (now - getattr(self, "_last_ndi_pop_time", 0.0)) < 1.0
                local_active = (now - getattr(self, "_last_local_pop_time", 0.0)) < 1.0

                buf_len_ndi = len(self._audio_buffer_ndi) if ndi_active else 0
                buf_len_local = len(self._audio_buffer_local) if local_active else 0
                is_done = (buf_len_ndi == 0 and buf_len_local == 0)

            if is_done:
                with self._buffer_lock:
                    self.is_speaking = False
                    self._audio_buffer_ndi = np.zeros((0, 2), dtype=np.float32)
                    self._audio_buffer_local = np.zeros((0, 2), dtype=np.float32)
                # Safety padding for soundcard hardware driver ringbuffer drain before resolving
                await asyncio.sleep(0.35)
                break
            await asyncio.sleep(poll_interval)
        else:
            with self._buffer_lock:
                self.is_speaking = False
                self._audio_buffer_ndi = np.zeros((0, 2), dtype=np.float32)
                self._audio_buffer_local = np.zeros((0, 2), dtype=np.float32)

    async def queue_speech(self, text: str):
        """Synthesizes text and pushes audio to dual synchronized NDI and Local playback buffers."""
        audio = await self.synthesize(text)
        if len(audio) > 0:
            with self._buffer_lock:
                # Seamless crossfade stitching if buffer already contains pending audio
                self._audio_buffer_ndi = np.vstack((self._audio_buffer_ndi, audio))
                self._audio_buffer_local = np.vstack((self._audio_buffer_local, audio))
            logger.debug(f"Queued audio buffer now at {len(self._audio_buffer_ndi)/self.sample_rate:.2f}s")

    def pop_audio_packet(self, num_samples: int = 800) -> Tuple[np.ndarray, np.ndarray]:
        """
        Pops exactly `num_samples` (default 800 = 16.666ms at 48kHz / 60fps) from the NDI audio buffer.
        Thread-safe for call from visualizer or audio OS thread.
        Returns:
            - audio_for_ndi: shape (2, num_samples) planar float32 for cyndilib
            - packet_audio: shape (num_samples, 2) interleaved float32
        """
        n = num_samples
        self._last_ndi_pop_time = time.time()
        with self._buffer_lock:
            if len(self._audio_buffer_ndi) >= n:
                packet_audio = self._audio_buffer_ndi[:n]
                self._audio_buffer_ndi = self._audio_buffer_ndi[n:]
                self.is_speaking = True
            elif len(self._audio_buffer_ndi) > 0:
                rem = len(self._audio_buffer_ndi)
                packet_audio = np.zeros((n, 2), dtype=np.float32)
                packet_audio[:rem] = self._audio_buffer_ndi
                self._audio_buffer_ndi = np.zeros((0, 2), dtype=np.float32)
                self.is_speaking = True
            else:
                packet_audio = np.zeros((n, 2), dtype=np.float32)
                self.is_speaking = False

        # Update sliding analysis window
        roll_len = min(n, 1024)
        self._analysis_window = np.roll(self._analysis_window, -roll_len, axis=0)
        self._analysis_window[-roll_len:] = packet_audio[:roll_len]

        # Calculate metrics for visualizer
        self._update_metrics()

        # Output shape (num_channels, num_samples) -> (2, num_samples) contiguous float32 for cyndilib
        audio_for_ndi = np.ascontiguousarray(packet_audio.T, dtype=np.float32)
        return audio_for_ndi, packet_audio

    def pop_local_audio(self, num_samples: int, volume: float = 1.0) -> np.ndarray:
        """
        Pops exactly `num_samples` from the local audio buffer for the Windows PortAudio callback.
        Guarantees zero buffer underruns, zero drift, and smooth audio scaling.
        """
        n = num_samples
        self._last_local_pop_time = time.time()
        with self._buffer_lock:
            if len(self._audio_buffer_local) >= n:
                packet_audio = self._audio_buffer_local[:n]
                self._audio_buffer_local = self._audio_buffer_local[n:]
            elif len(self._audio_buffer_local) > 0:
                rem = len(self._audio_buffer_local)
                packet_audio = np.zeros((n, 2), dtype=np.float32)
                packet_audio[:rem] = self._audio_buffer_local
                self._audio_buffer_local = np.zeros((0, 2), dtype=np.float32)
            else:
                packet_audio = np.zeros((n, 2), dtype=np.float32)

        if volume != 1.0:
            vol = max(0.0, min(2.0, volume))
            packet_audio = packet_audio * vol

        return np.ascontiguousarray(packet_audio, dtype=np.float32)

    def pop_frame_samples(self) -> Tuple[np.ndarray, np.ndarray]:
        """Pops exactly `samples_per_frame` (800) audio samples for the current 60fps tick."""
        return self.pop_audio_packet(self.samples_per_frame)

    def _update_metrics(self):
        """Vectorized computation of RMS amplitude and multi-band FFT energy for the visualizer."""
        mono = np.mean(self._analysis_window, axis=1)

        # RMS Amplitude
        rms = float(np.sqrt(np.mean(mono**2)))
        self.current_rms = rms

        if rms < 1e-4:
            self.smoothed_spectrum *= 0.85
            return

        # 1024-point FFT with precomputed Hanning window
        windowed = mono * self._hanning_window
        fft_vals = np.abs(np.fft.rfft(windowed))

        # Vectorized frequency band energy computation
        bands = np.zeros(self.num_spectrum_bands, dtype=np.float32)
        for i, (i_low, i_high) in enumerate(self._band_slices):
            if i_high > i_low:
                val = float(np.mean(fft_vals[i_low:i_high]))
                bands[i] = min(1.0, val * 0.15)

        # Vectorized exponential smoothing (fast attack, smooth decay)
        attack = 0.7
        decay = 0.25
        mask = bands > self.smoothed_spectrum
        self.smoothed_spectrum = np.where(
            mask,
            self.smoothed_spectrum * (1.0 - attack) + bands * attack,
            self.smoothed_spectrum * (1.0 - decay) + bands * decay,
        ).astype(np.float32)

    def get_audio_metrics(self) -> Dict:
        """Returns instantaneous audio metrics dictionary for the Visualizer."""
        return {
            "is_speaking": self.is_speaking,
            "rms": self.current_rms,
            "spectrum": self.smoothed_spectrum.copy(),
            "buffer_duration_sec": len(self._audio_buffer_ndi) / self.sample_rate,
            "active_backend": self.active_backend,
        }
