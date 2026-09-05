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

        # Double-buffered video memory to guarantee buffer lifetime during asynchronous NDI read
        self._buffer_index = 0
        self._video_buffers = [
            np.zeros(self.width * self.height * 4, dtype=np.uint8),
            np.zeros(self.width * self.height * 4, dtype=np.uint8),
        ]
        self._curr_frame_buffer: Optional[np.ndarray] = None
        self._prev_frame_buffer: Optional[np.ndarray] = None
        self._frame_buffer_bytes: Optional[bytes] = None
        self._prev_frame_buffer_bytes: Optional[bytes] = None

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

                # Explicit line stride verification (width * 4 bytes per row)
                expected_line_stride = self.width * 4
                actual_line_stride = self.video_frame.get_line_stride()
                if actual_line_stride != expected_line_stride:
                    logger.error(
                        f"NDI VideoSendFrame line stride mismatch: got {actual_line_stride}, expected {expected_line_stride} (width={self.width}x4)."
                    )
                else:
                    logger.info(f"NDI VideoSendFrame line stride verified: {actual_line_stride} bytes/line ({self.width}x4)")

                # Explicit FourCC verification (FOURCC_VIDEO_TYPE_RGBA)
                actual_fourcc = self.video_frame.get_fourcc()
                if actual_fourcc != cyndilib.FourCC.RGBA:
                    logger.error(f"NDI VideoSendFrame FourCC mismatch: got {actual_fourcc}, expected {cyndilib.FourCC.RGBA} (RGBA)")
                else:
                    logger.info(f"NDI VideoSendFrame FourCC verified: FOURCC_VIDEO_TYPE_RGBA ({actual_fourcc})")

                # 2. Configure Audio Frame (48000Hz Stereo Float32 with exact frame buffer capacity)
                # Exactly self.samples_per_frame (800 samples @ 60fps / 48kHz = exactly 3200 bytes/channel)
                # Eliminates channel stride drift, uninitialized buffer memory injection, and pegging OBS audio meter
                self.audio_frame = cyndilib.AudioSendFrame(self.samples_per_frame, self.channels, self.sample_rate)

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

        if audio_data.ndim == 2:
            if audio_data.shape[1] == 2 and audio_data.shape[0] != 2:
                audio_out = np.ascontiguousarray(audio_data.T, dtype=np.float32)
            else:
                audio_out = np.ascontiguousarray(audio_data, dtype=np.float32)
        elif audio_data.ndim == 1:
            audio_out = np.ascontiguousarray(np.vstack((audio_data, audio_data)), dtype=np.float32)
        else:
            audio_out = np.ascontiguousarray(audio_data, dtype=np.float32)

        # Ensure exact match with self.samples_per_frame (800 samples) to prevent uninitialized memory gaps
        target_samples = self.samples_per_frame
        curr_samples = audio_out.shape[1] if audio_out.ndim == 2 else 0

        if curr_samples < target_samples:
            padded = np.zeros((2, target_samples), dtype=np.float32)
            if curr_samples > 0:
                padded[:, :curr_samples] = audio_out[:, :curr_samples]
            audio_out = padded
        elif curr_samples > target_samples:
            audio_out = np.ascontiguousarray(audio_out[:, :target_samples], dtype=np.float32)

        with self._lock:
            try:
                # Rotate double buffer so previous frame remains alive during NDI asynchronous read
                target_buf = self._video_buffers[self._buffer_index]
                self._buffer_index = 1 - self._buffer_index

                if isinstance(video_rgba_bytes, (bytes, bytearray)):
                    target_buf[:] = np.frombuffer(video_rgba_bytes, dtype=np.uint8)
                else:
                    target_buf[:] = np.ascontiguousarray(video_rgba_bytes.reshape(-1), dtype=np.uint8)

                self._prev_frame_buffer = self._curr_frame_buffer
                self._curr_frame_buffer = target_buf
                self._prev_frame_buffer_bytes = self._frame_buffer_bytes
                self._frame_buffer_bytes = video_rgba_bytes if isinstance(video_rgba_bytes, (bytes, bytearray)) else None

                # Asynchronous video transmission + frame-locked synchronized audio
                self.sender.write_video_async(target_buf)
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
            with self._lock:
                # Rotate double buffer so previous frame remains alive during NDI asynchronous read
                target_buf = self._video_buffers[self._buffer_index]
                self._buffer_index = 1 - self._buffer_index

                if isinstance(video_rgba_bytes, (bytes, bytearray)):
                    target_buf[:] = np.frombuffer(video_rgba_bytes, dtype=np.uint8)
                else:
                    target_buf[:] = np.ascontiguousarray(video_rgba_bytes.reshape(-1), dtype=np.uint8)

                # Maintain persistent references on self across async NDI read lifetime
                self._prev_frame_buffer = self._curr_frame_buffer
                self._curr_frame_buffer = target_buf
                self._prev_frame_buffer_bytes = self._frame_buffer_bytes
                self._frame_buffer_bytes = video_rgba_bytes if isinstance(video_rgba_bytes, (bytes, bytearray)) else None

                self.sender.write_video_async(target_buf)
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

            target_samples = self.samples_per_frame
            curr_samples = audio_out.shape[1] if audio_out.ndim == 2 else 0
            if curr_samples == 0:
                return

            with self._lock:
                for chunk_start in range(0, curr_samples, target_samples):
                    chunk = audio_out[:, chunk_start : chunk_start + target_samples]
                    if chunk.shape[1] < target_samples:
                        padded = np.zeros((2, target_samples), dtype=np.float32)
                        padded[:, : chunk.shape[1]] = chunk
                        chunk = padded
                    self.sender.write_audio(np.ascontiguousarray(chunk, dtype=np.float32))
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
