"""
Audio Synthesis Engine for AI Live Stream Co-Host.
Synthesizes speech into high-quality 48kHz stereo PCM audio,
buffers samples in synchronization with 60fps video frames (800 samples/frame),
and computes real-time FFT / RMS amplitude metrics for the visualizer.
"""

import asyncio
from collections import deque
import io
import os
import logging
import re
import threading
import time
from typing import Callable, Dict, Optional, Tuple

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
        self.tts_backend = self.cfg.tts_backend.lower()
        self.server_url = self.cfg.tts_server_url.rstrip("/")
        self.reference_voice = self.cfg.tts_reference_voice
        self.timeout_floor = self.cfg.tts_request_timeout_floor
        self.timeout_ceiling = self.cfg.tts_request_timeout_ceiling
        self.exaggeration_default = self.cfg.tts_exaggeration_default
        self.mood_exaggeration_map = self.cfg.tts_mood_exaggeration_map
        self.mood_cfg_weight_map = self.cfg.tts_mood_cfg_weight_map
        self.max_concurrent_synth = self.cfg.max_concurrent_synth
        self._synth_semaphore = asyncio.Semaphore(self.max_concurrent_synth)

        # Active backend state (tracks failover from chatterbox -> edge)
        self.active_backend = self.tts_backend
        self._health_checked = False
        self._warned_unhealthy = False

        # Edge-TTS settings
        self.voice = self.cfg.tts_voice
        self.pitch = self.cfg.tts_pitch
        self.rate = self.cfg.tts_rate

        # Utterance bookkeeping for sentence-pipelined speech playback
        self._utterance_total_samples: int = 0
        self._utterance_open: bool = False
        self._utterance_chunk_count: int = 0
        self._first_push_time: float = 0.0
        self.last_synthesized_duration: float = 0.0

        # Underrun detector & metrics
        self.underrun_count: int = 0
        self.underrun_samples: int = 0
        self._last_underrun_log_time: float = 0.0
        self._local_resume_pending: bool = False

        # GPU exclusivity & Background synthesis control
        self.live_turn_active: asyncio.Event = asyncio.Event()
        self.gpu_lock: asyncio.Lock = asyncio.Lock()
        self.last_live_turn_end_time: float = 0.0
        self._bg_inside_gpu_lock: bool = False

        # Rolling Real-Time Factor (RTF) history
        self._rtf_history: deque = deque(maxlen=8)
        self.last_peak: float = 0.0
        self.last_clip_frac: float = 0.0

        # Dual independent sample buffers for NDI and Local Windows Audio (lock-free deque of [chunk, offset])
        self.ndi_buffer_enabled: bool = True
        self.ndi_sink: Optional[Callable[[np.ndarray], None]] = None
        # Called with True after the FIRST chunk of an utterance is in the buffers (so the
        # render worker never sees "open but empty"), and with False on end/clear.
        self.utterance_state_sink: Optional[Callable[[bool], None]] = None
        self.ndi_clear_sink: Optional[Callable[[], None]] = None
        self._audio_buffer_ndi: deque = deque()
        self._audio_buffer_local: deque = deque()
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

        # Peak analysis. Hard clipping at the SOURCE (e.g. int16 wraparound on the TTS server)
        # cannot be repaired here, but it can be detected: a run of samples pinned at full scale.
        max_val = float(np.max(np.abs(data))) if len(data) else 0.0
        clip_frac = float(np.mean(np.abs(data) >= 0.985)) if len(data) else 0.0
        ceiling = float(self.cfg.tts_peak_ceiling)
        if clip_frac > 0.0005:  # >0.05% of samples at full scale = source was clipped/wrapped
            logger.warning(
                f"[TTS PEAK] Source audio arrived already clipped: peak={max_val:.3f}, "
                f"{clip_frac*100:.2f}% of samples at full scale (src_sr={src_sr}). "
                "Fix on the TTS server (clamp before int16 WAV write) or lower exaggeration."
            )
        elif max_val > ceiling:
            logger.info(f"[TTS PEAK] normalised {max_val:.3f} -> {ceiling:.2f}")

        # Prevent downstream digital clipping: normalise peaks above the ceiling
        if max_val > ceiling:
            data = (data / max_val) * ceiling
        self.last_peak = max_val
        self.last_clip_frac = clip_frac

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

    @property
    def rtf_conservative(self) -> float:
        """Returns the conservative (minimum) real-time factor over the last 8 syntheses."""
        with self._buffer_lock:
            if self._rtf_history:
                return float(min(self._rtf_history))
        return 1.5

    def record_rtf(self, rtf: float):
        """Records a completed synthesis real-time factor."""
        if rtf > 0.05:
            with self._buffer_lock:
                self._rtf_history.append(float(rtf))

    async def _synthesize_chatterbox(self, clean_text: str, exaggeration: float,
                                     cfg_weight: Optional[float] = None, is_live: bool = True) -> Optional[np.ndarray]:
        """Synthesizes speech via remote ChatterBox Turbo GPU inference server."""
        url = f"{self.server_url}/synthesize"
        # Calibrated timeout: estimate audio length and give generous headroom clamped to [8, 45]s
        est_audio_sec = len(clean_text) * float(self.cfg.tts_sec_per_char)
        calc_timeout = max(8.0, min(45.0, est_audio_sec * 2.0 + 4.0))
        timeout = aiohttp.ClientTimeout(total=calc_timeout)
        payload = {
            "text": clean_text,
            "voice": self.reference_voice,
            "exaggeration": exaggeration,
            "cfg_weight": float(self.cfg.tts_cfg_weight if cfg_weight is None else cfg_weight),
            "format": "wav",
        }
        tag = "[TTS LIVE]" if is_live else "[TTS BG]"
        t0 = time.perf_counter()

        try:
            async with self._synth_semaphore:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=payload) as resp:
                        if resp.status == 200:
                            raw_wav = await resp.read()
                            if not raw_wav:
                                return None
                            # Zero-latency polyphase FIR decoding & resampling in worker thread
                            data = await asyncio.to_thread(self._decode_and_resample, raw_wav)
                            wall_sec = time.perf_counter() - t0
                            audio_dur = len(data) / self.sample_rate
                            if wall_sec > 0:
                                rtf = audio_dur / wall_sec
                                self.record_rtf(rtf)
                                rtf_str = f"{rtf:.2f}"
                            else:
                                rtf_str = "N/A"
                            logger.info(
                                f"{tag} [Chatterbox] Synthesized {audio_dur:.2f}s audio in {wall_sec:.2f}s "
                                f"(rtf={rtf_str}, exaggeration={exaggeration:.2f}) from {self.server_url}"
                            )
                            return data
                        else:
                            err_text = await resp.text()
                            logger.warning(f"{tag} Chatterbox server returned error HTTP {resp.status}: {err_text}")
                            return None
        except (asyncio.TimeoutError, aiohttp.ServerTimeoutError) as e:
            wall_sec = time.perf_counter() - t0
            logger.error(
                f"❌ {tag} [Chatterbox] Synthesis TIMEOUT after {wall_sec:.2f}s (calc_timeout={calc_timeout:.1f}s) "
                f"for sentence ({len(clean_text)} chars): '{clean_text}'"
            )
            return None
        except aiohttp.ClientError as e:
            wall_sec = time.perf_counter() - t0
            logger.warning(
                f"{tag} Chatterbox connection error to {self.server_url} after {wall_sec:.2f}s ({e}); "
                f"falling back to local edge-tts."
            )
            return None
        except Exception as e:
            logger.error(f"{tag} Unexpected error calling Chatterbox server: {e}", exc_info=True)
            return None

    async def _synthesize_edge_tts(self, clean_text: str, is_live: bool = True) -> np.ndarray:
        """Synthesizes speech locally via Microsoft edge-tts."""
        tag = "[TTS LIVE]" if is_live else "[TTS BG]"
        if not EDGE_TTS_AVAILABLE:
            logger.warning(f"{tag} edge-tts not available, generating synthesized tone placeholder")
            return self._generate_sine_placeholder(len(clean_text) * 0.06)

        try:
            t0 = time.perf_counter()
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
                logger.warning(f"{tag} No audio bytes received from edge-tts")
                return np.zeros((0, 2), dtype=np.float32)

            data = await asyncio.to_thread(self._decode_and_resample, bytes(audio_bytes))
            wall_sec = time.perf_counter() - t0
            audio_dur = len(data) / self.sample_rate
            if wall_sec > 0:
                rtf = audio_dur / wall_sec
                self.record_rtf(rtf)
            logger.info(f"{tag} [Edge-TTS] Synthesized {audio_dur:.2f}s of 48kHz stereo audio in {wall_sec:.2f}s")
            return data
        except Exception as e:
            logger.error(f"{tag} Error during edge-tts synthesis: {e}")
            return self._generate_sine_placeholder(len(clean_text) * 0.06)

    def _prepare_text(self, text: str, mood: str) -> Tuple[str, str, float, float]:
        """Resolves mood -> (clean_text, mood, exaggeration, cfg_weight) for the synthesizer."""
        active_mood = (mood or "neutral").lower().strip()
        if active_mood == "neutral":
            mood_match = re.search(r"\[MOOD:\s*([a-zA-Z_-]+)\]", text, flags=re.IGNORECASE)
            if mood_match:
                active_mood = mood_match.group(1).lower()
        exaggeration = self.mood_exaggeration_map.get(active_mood, self.exaggeration_default)
        exag_max = float(self.cfg.tts_exaggeration_max)
        if exaggeration > exag_max:
            exaggeration = exag_max

        clean_text = re.sub(r"\[MOOD:\s*[a-zA-Z_-]+\]", "", text, flags=re.IGNORECASE).strip()
        clean_text = re.sub(r"@+", "", clean_text)
        clean_text = clean_text.replace("*", "").replace("`", "").strip()

        cfg_weight = float(self.mood_cfg_weight_map.get(active_mood, self.cfg.tts_cfg_weight))
        return clean_text, active_mood, exaggeration, cfg_weight

    async def _synthesize_locked(self, clean_text: str, active_mood: str, exaggeration: float,
                                 cfg_weight: float, is_live: bool) -> np.ndarray:
        """
        Backend dispatch. MUST be called with self.gpu_lock already held by the caller.
        Never acquires the lock itself (asyncio.Lock is not re-entrant).
        """
        assert self.gpu_lock.locked(), "_synthesize_locked called without gpu_lock held"
        tag = "[TTS LIVE]" if is_live else "[TTS BG]"

        # 1. Primary: Remote Chatterbox Turbo GPU inference server
        if self.active_backend == "chatterbox":
            data = await self._synthesize_chatterbox(clean_text, exaggeration, cfg_weight, is_live=is_live)
            if data is not None and len(data) > 0:
                self.last_synthesized_duration = len(data) / self.sample_rate
                return data
            logger.info(f"{tag} Failing over to local Edge-TTS for utterance '{clean_text[:35]}...'")

        # 2. Fallback / Local Mode: Microsoft edge-tts
        data = await self._synthesize_edge_tts(clean_text, is_live=is_live)
        if len(data) > 0:
            self.last_synthesized_duration = len(data) / self.sample_rate
            return data

        # 3. Final safety: Sine placeholder (never silent)
        placeholder = self._generate_sine_placeholder(len(clean_text) * 0.06)
        self.last_synthesized_duration = len(placeholder) / self.sample_rate
        return placeholder

    async def synthesize(
        self,
        text: str,
        mood: str = "neutral",
        is_live: bool = True,
        *,
        _from_live_turn: bool = False,
    ) -> np.ndarray:
        """
        Live-turn synthesis: text -> 48kHz stereo float32 PCM.
        Acquires gpu_lock for the duration of the backend call so live sentences run serially.
        Background callers must use synthesize_background(); this method logs a stack trace if
        called without _from_live_turn=True, but still performs the synthesis.
        """
        if not _from_live_turn:
            logger.error(
                "[TTS MISUSE] TTSEngine.synthesize called without _from_live_turn=True. "
                "Background tasks must call synthesize_background().",
                stack_info=True,
            )

        clean_text, active_mood, exaggeration, cfg_weight = self._prepare_text(text, mood)
        if not clean_text:
            return np.zeros((0, 2), dtype=np.float32)

        tag = "[TTS LIVE]" if is_live else "[TTS BG]"
        logger.info(
            f"{tag} Synthesizing speech ({len(clean_text)} chars, mood={active_mood}, "
            f"exaggeration={exaggeration:.2f}, cfg_weight={cfg_weight:.2f}): '{clean_text[:60]}...'"
        )
        async with self.gpu_lock:
            return await self._synthesize_locked(clean_text, active_mood, exaggeration, cfg_weight, is_live)

    def _bg_may_proceed(self) -> bool:
        """True when no live turn is active and the post-turn cooldown has elapsed."""
        if self.live_turn_active.is_set():
            return False
        cooldown = float(self.cfg.cache_refill_cooldown_sec)
        if self.last_live_turn_end_time > 0 and (time.time() - self.last_live_turn_end_time) < cooldown:
            return False
        return True

    async def synthesize_background(self, text: str, mood: str = "neutral") -> np.ndarray:
        """
        Background pre-synthesis (greeting cache, warm-ups). Guarantees GPU exclusivity for live turns:
        (a) waits until no live turn is active and the cooldown has elapsed WITHOUT holding gpu_lock,
        (b) acquires gpu_lock,
        (c) re-checks; if a turn started meanwhile, releases and goes back to (a).
        """
        clean_text, active_mood, exaggeration, cfg_weight = self._prepare_text(text, mood)
        if not clean_text:
            return np.zeros((0, 2), dtype=np.float32)

        while True:
            # (a) Wait outside the lock. Never sleep while holding gpu_lock.
            while not self._bg_may_proceed():
                await asyncio.sleep(0.1)

            # (b)/(c) Acquire, re-validate, synthesize.
            async with self.gpu_lock:
                if not self._bg_may_proceed():
                    continue  # releases lock via context manager, back to (a)
                self._bg_inside_gpu_lock = True
                try:
                    logger.info(
                        f"[TTS BG] Synthesizing ({len(clean_text)} chars, mood={active_mood}, "
                        f"exaggeration={exaggeration:.2f}, cfg_weight={cfg_weight:.2f}): '{clean_text[:60]}...'"
                    )
                    return await self._synthesize_locked(clean_text, active_mood, exaggeration, cfg_weight, is_live=False)
                finally:
                    self._bg_inside_gpu_lock = False

    async def queue_speech(self, text: str, mood: str = "neutral"):
        """
        Synthesizes and plays a standalone utterance outside the turn scheduler
        (used by chat_reader_mode). Runs as a live utterance for GPU priority.
        """
        audio = await self.synthesize(text, mood=mood, is_live=True, _from_live_turn=True)
        if audio is None or len(audio) == 0:
            return
        self.begin_utterance()
        self.push_audio(audio)
        self.end_utterance()

    def _generate_sine_placeholder(self, duration_sec: float) -> np.ndarray:
        """Fallback beep / harmonic synthesizer."""
        t = np.linspace(0, duration_sec, int(self.sample_rate * duration_sec), endpoint=False)
        sine = 0.2 * np.sin(2 * np.pi * 440.0 * t) * np.exp(-t * 2)
        sine = sine.astype(np.float32)
        return np.column_stack((sine, sine))

    def _buffered_samples_ndi(self) -> int:
        return sum(len(item[0]) - item[1] for item in self._audio_buffer_ndi)

    def _buffered_samples_local(self) -> int:
        return sum(len(item[0]) - item[1] for item in self._audio_buffer_local)

    def _pop_from_deque(self, d: deque, num_samples: int) -> Tuple[np.ndarray, bool]:
        """
        Pops exactly `num_samples` (stereo, shape (num_samples, 2)) from the front of the deque.
        Returns (packet_audio, had_samples).
        Caller MUST hold `self._buffer_lock`.
        """
        out = np.zeros((num_samples, 2), dtype=np.float32)
        filled = 0
        while d and filled < num_samples:
            head = d[0]  # [chunk, offset]
            chunk = head[0]
            offset = head[1]
            available = len(chunk) - offset
            needed = num_samples - filled
            to_copy = min(available, needed)

            out[filled : filled + to_copy] = chunk[offset : offset + to_copy]
            filled += to_copy
            head[1] += to_copy

            if head[1] >= len(chunk):
                d.popleft()

        had_samples = (filled > 0)
        return out, had_samples

    @property
    def remaining_speech_duration(self) -> float:
        """Returns the duration in seconds of audio currently queued in the playback buffer."""
        with self._buffer_lock:
            samples = self._buffered_samples_ndi() if self.ndi_buffer_enabled else self._buffered_samples_local()
            return samples / self.sample_rate

    def get_buffered_duration(self) -> float:
        """Returns the duration in seconds of audio currently queued in the playback buffer."""
        return self.remaining_speech_duration

    def _dump_chunk(self, audio: np.ndarray):
        """Diagnostic tap: IAM_DUMP_TTS_AUDIO=1 appends every processed chunk (as pushed) to a WAV."""
        if os.environ.get("IAM_DUMP_TTS_AUDIO", "0") != "1":
            return
        try:
            if getattr(self, "_dump_file", None) is None:
                path = os.path.abspath(os.environ.get("IAM_DUMP_TTS_PATH", "debug_tts_push.wav"))
                self._dump_file = sf.SoundFile(path, mode="w", samplerate=self.sample_rate, channels=2, subtype="FLOAT")
                logger.warning(f"[AUDIO DUMP] Writing TTS push stream to {path}")
            self._dump_file.write(audio)
            self._dump_file.flush()
        except Exception as e:
            logger.error(f"[AUDIO DUMP] TTS dump failed: {e}")

    def begin_utterance(self):
        """Marks the start of a new conversational turn or multi-sentence sequence."""
        with self._buffer_lock:
            self._utterance_total_samples = 0
            self._utterance_chunk_count = 0
            self._first_push_time = 0.0
            self._utterance_open = True
            self.is_speaking = True

    def end_utterance(self):
        """Marks that all sentences for the active turn have been synthesized and pushed."""
        with self._buffer_lock:
            self._utterance_open = False
            if self._utterance_total_samples == 0:
                self.is_speaking = False
        if self.utterance_state_sink is not None:
            self.utterance_state_sink(False)

    def clear_audio_buffer(self):
        """Immediately purges all pending audio queues on turn interruption or barge-in."""
        with self._buffer_lock:
            self._audio_buffer_ndi.clear()
            self._audio_buffer_local.clear()
            self._utterance_open = False
            self._utterance_total_samples = 0
            self._utterance_chunk_count = 0
            self._first_push_time = 0.0
            self.is_speaking = False
        if self.ndi_clear_sink is not None:
            try:
                self.ndi_clear_sink()
            except Exception as e:
                logger.error(f"Error invoking ndi_clear_sink: {e}")
        if self.utterance_state_sink is not None:
            self.utterance_state_sink(False)

    async def wait_until_speech_completed(self, poll_interval: float = 0.05, timeout: Optional[float] = None):
        """
        Asynchronously waits until all buffered speech audio has finished broadcasting out
        through NDI/audio and the current utterance is closed.
        """
        t0 = time.time()
        # Brief initial sleep so the pop_audio_packet / pop_local_audio threads register playback start
        await asyncio.sleep(0.05)

        with self._buffer_lock:
            total_samples = self._utterance_total_samples
            first_push = self._first_push_time or t0

        expected_dur = total_samples / self.sample_rate if total_samples > 0 else getattr(self, "last_synthesized_duration", 0.0)
        hard_timeout = expected_dur + 3.0
        effective_timeout = timeout if timeout is not None else hard_timeout

        while True:
            now = time.time()
            with self._buffer_lock:
                utterance_open = self._utterance_open
                local_enabled = self.cfg.local_audio_enabled
                local_active = (now - getattr(self, "_last_local_pop_time", 0.0)) < 1.0 and local_enabled
                ndi_active = (now - getattr(self, "_last_ndi_pop_time", 0.0)) < 1.0 and self.ndi_buffer_enabled

                buf_len_ndi = self._buffered_samples_ndi() if ndi_active else 0
                buf_len_local = self._buffered_samples_local() if local_active else 0

                if local_active:
                    is_drained = (buf_len_local == 0)
                elif ndi_active:
                    is_drained = (buf_len_ndi == 0)
                else:
                    # Neither local nor NDI is actively popping in main process (e.g. proxy mode with local_audio disabled, or test harness)
                    elapsed = now - (self._first_push_time if self._first_push_time > 0 else t0)
                    is_drained = (elapsed >= expected_dur)

                is_done = (not utterance_open) and is_drained

            if is_done:
                with self._buffer_lock:
                    self.is_speaking = False
                    self._audio_buffer_ndi.clear()
                    self._audio_buffer_local.clear()
                # Safety padding for soundcard hardware driver ringbuffer drain before resolving
                await asyncio.sleep(0.10)
                break

            if (time.time() - t0) >= effective_timeout:
                logger.warning(
                    f"⚠️ [TTS-ENGINE] wait_until_speech_completed timed out after {effective_timeout:.2f}s "
                    f"(expected {expected_dur:.2f}s, open={utterance_open})"
                )
                with self._buffer_lock:
                    self.is_speaking = False
                    self._audio_buffer_ndi.clear()
                    self._audio_buffer_local.clear()
                break

            await asyncio.sleep(poll_interval)

    def push_audio(self, audio: np.ndarray, beat_before: bool = False) -> np.ndarray:
        """
        Pushes pre-synthesized audio into playback buffers with zero latency,
        applying 5ms crossfades and inter-sentence gap silence between chunks.
        Returns the fully processed array (after fades and gap prepend).
        """
        if audio is None or len(audio) == 0:
            return np.zeros((0, 2), dtype=np.float32)

        if audio.ndim == 1:
            audio = np.column_stack((audio, audio))
        elif audio.shape[1] == 1:
            audio = np.column_stack((audio[:, 0], audio[:, 0]))

        audio = audio.astype(np.float32).copy()
        dur = len(audio) / self.sample_rate
        self.last_synthesized_duration = dur

        # 5ms fade = 240 samples at 48kHz
        fade_samples = min(240, len(audio) // 4)
        if fade_samples > 0:
            # Always apply 5ms linear fade-out to tail to prevent zero-crossing clicks
            fade_out = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)[:, None]
            audio[-fade_samples:] *= fade_out

        is_first_chunk = (self._utterance_chunk_count == 0)
        if not is_first_chunk:
            # Subsequent chunks: apply 5ms head fade-in and prepend gap silence
            if fade_samples > 0:
                fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)[:, None]
                audio[:fade_samples] *= fade_in

            inter_gap_sec = float(self.cfg.tts_beat_gap_sec) if beat_before else float(self.cfg.inter_sentence_gap_sec)
            if beat_before:
                logger.info(f"[TTS BEAT] inserting {inter_gap_sec*1000:.0f} ms comedic pause before chunk #{self._utterance_chunk_count + 1}")
            if inter_gap_sec > 0:
                gap_samples = int(self.sample_rate * inter_gap_sec)
                gap_silence = np.zeros((gap_samples, 2), dtype=np.float32)
                audio = np.vstack((gap_silence, audio))
        else:
            # First chunk: if buffer currently has residual samples, fade in to prevent discontinuity
            with self._buffer_lock:
                buffer_has_samples = (self._buffered_samples_ndi() > 0) if self.ndi_buffer_enabled else (self._buffered_samples_local() > 0)
            if fade_samples > 0 and buffer_has_samples:
                fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)[:, None]
                audio[:fade_samples] *= fade_in

        # Microsecond lock hold time: only append reference and update counters
        with self._buffer_lock:
            if self._first_push_time == 0.0:
                self._first_push_time = time.time()
                self._utterance_open = True

            self._utterance_chunk_count += 1
            self._utterance_total_samples += len(audio)

            if self.ndi_buffer_enabled:
                self._audio_buffer_ndi.append([audio, 0])
            self._audio_buffer_local.append([audio, 0])
            self.is_speaking = True

            total_buf_sec = (self._buffered_samples_ndi() if self.ndi_buffer_enabled else self._buffered_samples_local()) / self.sample_rate
            logger.info(
                f"Queued {dur:.2f}s pre-synthesized audio "
                f"(chunk #{self._utterance_chunk_count}, total buffered: {total_buf_sec:.2f}s)"
            )

        if self.ndi_sink is not None:
            self.ndi_sink(audio)
        self._dump_chunk(audio)
        # Announce the open utterance only once data is actually available downstream.
        if is_first_chunk and self.utterance_state_sink is not None:
            self.utterance_state_sink(True)

        return audio

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
            packet_audio, had_samples = self._pop_from_deque(self._audio_buffer_ndi, n)
            self.is_speaking = had_samples or (self._buffered_samples_local() > 0)

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
        Guarantees zero buffer underruns, zero drift, smooth audio scaling, and click-free crossfades.
        """
        n = num_samples
        now = time.time()
        self._last_local_pop_time = now
        with self._buffer_lock:
            packet_audio, has_audio = self._pop_from_deque(self._audio_buffer_local, n)
            utterance_open = self._utterance_open

            # Detect and count underrun if utterance is open but buffer ran dry
            if utterance_open and not has_audio and self._utterance_chunk_count > 0:
                self.underrun_count += 1
                self.underrun_samples += n
                if now - self._last_underrun_log_time >= 0.5:
                    total_ms = (self.underrun_samples / self.sample_rate) * 1000.0
                    logger.warning(
                        f"[TTS UNDERRUN] utterance open, local buffer empty ({self.underrun_count} underruns, {total_ms:.1f} ms total)"
                    )
                    self._last_underrun_log_time = now

            ndi_active = (now - getattr(self, "_last_ndi_pop_time", 0.0)) < 0.5
            if not ndi_active:
                self.is_speaking = has_audio

        # 5ms crossfade on buffer starvation and resume (240 samples @ 48kHz)
        fade_samples = min(240, n)
        if utterance_open and not has_audio:
            self._local_resume_pending = True
        elif has_audio and self._local_resume_pending:
            if fade_samples > 0:
                fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)[:, None]
                packet_audio[:fade_samples] *= fade_in
            self._local_resume_pending = False

        if not ndi_active:
            roll_len = min(n, 1024)
            self._analysis_window = np.roll(self._analysis_window, -roll_len, axis=0)
            self._analysis_window[-roll_len:] = packet_audio[:roll_len]
            self._update_metrics()

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
            "buffer_duration_sec": self.remaining_speech_duration,
            "active_backend": self.active_backend,
        }
