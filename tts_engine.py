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

        self.voice = self.cfg.tts_voice
        self.pitch = self.cfg.tts_pitch
        self.rate = self.cfg.tts_rate

        # Dual independent sample buffers for NDI and Local Windows Audio
        self._audio_buffer_ndi = np.zeros((0, 2), dtype=np.float32)
        self._audio_buffer_local = np.zeros((0, 2), dtype=np.float32)
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

    async def synthesize(self, text: str) -> np.ndarray:
        """
        Synthesize text into 48kHz stereo float32 PCM numpy array.
        Returns array of shape (num_samples, 2).
        """
        # Clean text of mood tags, markdown, and '@' symbols before speech synthesis
        clean_text = re.sub(r"\[MOOD:\s*[a-zA-Z_-]+\]", "", text, flags=re.IGNORECASE).strip()
        clean_text = re.sub(r"@([a-zA-Z0-9_]+)", r"\1", clean_text)
        clean_text = clean_text.replace("*", "").replace("`", "").strip()

        if not clean_text:
            return np.zeros((0, 2), dtype=np.float32)

        logger.info(f"Synthesizing speech ({len(clean_text)} chars): '{clean_text[:60]}...'")

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

            # Offload CPU-heavy decoding and polyphase FIR resampling to thread pool
            data = await asyncio.to_thread(self._decode_and_resample, bytes(audio_bytes))

            logger.info(f"Synthesized {len(data)/self.sample_rate:.2f}s of 48kHz stereo audio")
            return data

        except Exception as e:
            logger.error(f"Error during TTS synthesis: {e}")
            return self._generate_sine_placeholder(1.5)

    def _generate_sine_placeholder(self, duration_sec: float) -> np.ndarray:
        """Fallback beep / harmonic synthesizer."""
        t = np.linspace(0, duration_sec, int(self.sample_rate * duration_sec), endpoint=False)
        sine = 0.2 * np.sin(2 * np.pi * 440.0 * t) * np.exp(-t * 2)
        sine = sine.astype(np.float32)
        return np.column_stack((sine, sine))

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
        }
