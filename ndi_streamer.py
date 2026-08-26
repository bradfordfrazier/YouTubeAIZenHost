"""
NDI Broadcast Engine for AI Live Stream Co-Host.
Packages 1080p60 RGBA video frames and synchronized 48kHz stereo audio into
the outbound local NDI stream 'AI_COHOST_FEED'.
"""

import logging
import threading
import time
from fractions import Fraction
from typing import Optional

import numpy as np
from config import config

# Optional cyndilib import with mock fallback
try:
    import cyndilib
    CYNDILIB_AVAILABLE = True
except ImportError:
    cyndilib = None
    CYNDILIB_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [NDI-STREAMER] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ndi_streamer")


class NDIStreamer:
    """Broadcaster wrapping cyndilib to stream 1080p60 RGBA video + 48kHz stereo audio over NDI."""

    def __init__(self, stream_name: Optional[str] = None):
        self.cfg = config
        self.stream_name = stream_name or self.cfg.ndi_stream_name  # "AI_COHOST_FEED"
        self.width = self.cfg.visualizer_width  # 1920 or 1080
        self.height = self.cfg.visualizer_height  # 1080 or 1920
        self.fps = self.cfg.visualizer_fps  # 60
        self.sample_rate = self.cfg.tts_sample_rate  # 48000
        self.channels = 2  # Stereo
        self.samples_per_frame = self.sample_rate // self.fps  # 800 samples per 60fps frame
        self.audio_packet_samples = 480  # Exactly 480 samples (10ms @ 48kHz) for zero-jitter isochronous audio pump

        self.sender = None
        self.video_frame = None
        self.audio_frame = None
        self.is_open = False
        self.is_mock = not CYNDILIB_AVAILABLE
        self.frames_sent = 0
        self.start_time = 0.0
        self._lock = threading.RLock()

    def open(self) -> bool:
        """Initialize and open the NDI Sender."""
        if not CYNDILIB_AVAILABLE:
            logger.warning(
                "cyndilib is not installed or unavailable. NDIStreamer running in Mock Broadcasting Mode."
            )
            self.is_mock = True
            self.is_open = True
            self.start_time = time.time()
            return True

        with self._lock:
            try:
                logger.info(f"Initializing NDI Sender '{self.stream_name}'...")
                logger.info(f"NDI Version: {cyndilib.get_ndi_version()}")

                # 1. Configure Video Frame (1920x1080 @ 60fps RGBA or 1080x1920 @ 60fps RGBA)
                self.video_frame = cyndilib.VideoSendFrame()
                self.video_frame.set_resolution(self.width, self.height)
                self.video_frame.set_frame_rate(Fraction(self.fps, 1))
                self.video_frame.set_fourcc(cyndilib.FourCC.RGBA)

                # 2. Configure Audio Frame (48000Hz Stereo Float32 with exact 480-sample buffer)
                # Matches the 10ms isochronous pump (480 samples @ 48kHz = exactly 1920 bytes/channel)
                # Eliminates channel stride drift, garbage memory injection, and NDI audio distortion in OBS
                self.audio_frame = cyndilib.AudioSendFrame(self.audio_packet_samples, self.channels, self.sample_rate)

                # 3. Create and configure Sender (unclocked so Python loop drives precise 60 FPS clock)
                self.sender = cyndilib.Sender(
                    ndi_name=self.stream_name,
                    clock_video=False,
                    clock_audio=False,
                )
                self.sender.set_video_frame(self.video_frame)
                self.sender.set_audio_frame(self.audio_frame)

                self.sender.open()
                self.is_open = True
                self.is_mock = False
                self.start_time = time.time()
                logger.info(f"NDI Stream '{self.stream_name}' is LIVE ({self.width}x{self.height} @ 60fps + 48kHz Stereo Frame-Locked)!")
                return True

            except Exception as e:
                import traceback
                logger.error(f"Failed to open real NDI Sender: {e}\n{traceback.format_exc()}. Falling back to mock streamer.")
                self.is_mock = True
                self.is_open = True
                self.start_time = time.time()
                return False

    def send_frame_sync(self, video_rgba_bytes: bytes, audio_data: np.ndarray):
        """
        Atomically broadcasts synchronized video and audio frames to NDI.
        Video: RGBA buffer of size (width * height * 4).
        Audio: Planar float32 audio of shape (2, num_samples) or interleaved (num_samples, 2).
        """
        if not self.is_open:
            return
        self.frames_sent += 1
        if self.is_mock or not self.sender:
            return

        if isinstance(video_rgba_bytes, (bytes, bytearray)):
            video_data = np.frombuffer(video_rgba_bytes, dtype=np.uint8).copy()
        else:
            video_data = np.ascontiguousarray(video_rgba_bytes.reshape(-1), dtype=np.uint8)

        if audio_data.ndim == 2:
            if audio_data.shape[1] == 2 and audio_data.shape[0] != 2:
                audio_out = np.ascontiguousarray(audio_data.T, dtype=np.float32)
            else:
                audio_out = np.ascontiguousarray(audio_data, dtype=np.float32)
        elif audio_data.ndim == 1:
            audio_out = np.ascontiguousarray(np.vstack((audio_data, audio_data)), dtype=np.float32)
        else:
            audio_out = np.ascontiguousarray(audio_data, dtype=np.float32)

        with self._lock:
            try:
                # Use atomic write_video_and_audio for asynchronous video transmission and synchronized audio
                if hasattr(self.sender, "write_video_and_audio"):
                    self.sender.write_video_and_audio(video_data, audio_out)
                else:
                    self.sender.write_video_async(video_data)
                    self.sender.write_audio(audio_out)
            except Exception as e:
                logger.error(f"Error in synchronized NDI broadcast: {e}")

    def send_video(self, video_rgba_bytes: bytes):
        """Sends a single video frame asynchronously to NDI."""
        if not self.is_open:
            return
        self.frames_sent += 1
        if self.is_mock or not self.sender:
            return
        try:
            if isinstance(video_rgba_bytes, (bytes, bytearray)):
                video_data = np.frombuffer(video_rgba_bytes, dtype=np.uint8).copy()
            else:
                video_data = np.ascontiguousarray(video_rgba_bytes.reshape(-1), dtype=np.uint8)

            with self._lock:
                self.sender.write_video_async(video_data)
        except Exception as e:
            logger.error(f"Error streaming video frame over NDI: {e}")

    def send_audio(self, audio_data: np.ndarray):
        """Sends audio samples to NDI (shape: [2, num_samples] planar float32)."""
        if not self.is_open or self.is_mock or not self.sender:
            return
        try:
            if audio_data.ndim == 2:
                if audio_data.shape[1] == 2 and audio_data.shape[0] != 2:
                    audio_out = np.ascontiguousarray(audio_data.T, dtype=np.float32)
                else:
                    audio_out = np.ascontiguousarray(audio_data, dtype=np.float32)
            elif audio_data.ndim == 1:
                audio_out = np.ascontiguousarray(np.vstack((audio_data, audio_data)), dtype=np.float32)
            else:
                audio_out = np.ascontiguousarray(audio_data, dtype=np.float32)

            with self._lock:
                self.sender.write_audio(audio_out)
        except Exception as e:
            logger.error(f"Error streaming audio packet over NDI: {e}")

    def send_frame(self, video_rgba_bytes: bytes, audio_data: np.ndarray):
        """Legacy combined method forwarding directly to send_frame_sync."""
        self.send_frame_sync(video_rgba_bytes, audio_data)

    def get_num_connections(self) -> int:
        """Returns the number of active NDI receivers (e.g. OBS Studio or NDI Monitor)."""
        if not self.is_open or self.is_mock or not self.sender:
            return 0
        with self._lock:
            try:
                return self.sender.get_num_connections(0.0)
            except Exception:
                return 0

    def close(self):
        """Closes the NDI Sender and releases resources."""
        with self._lock:
            if self.sender and self.is_open:
                try:
                    self.sender.close()
                    logger.info(f"NDI Stream '{self.stream_name}' closed cleanly.")
                except Exception as e:
                    logger.debug(f"Error during NDI close: {e}")
            self.is_open = False
