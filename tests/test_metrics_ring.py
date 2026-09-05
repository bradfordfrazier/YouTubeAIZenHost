"""
Unit test for 60 Hz Audio Metrics Ring buffer in shared memory (Item 1).
"""

from pathlib import Path
import sys
import threading
import time
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from render_worker import AudioMetricsSharedMemory, ndi_audio_pump


class MockNDISender:
    def __init__(self):
        self.is_open = True
        self.audio_packet_samples = 2400
        self.sent_packets = []

    def send_audio_packet(self, packet: np.ndarray):
        self.sent_packets.append(packet)


def test_metrics_ring_60hz_updates_and_speaking_rise():
    """
    Pushes 1.0s of 1kHz tone through the audio pump with a mocked NDI sender.
    Samples read_metrics_for(time.time()) at 60 Hz and verifies:
    1. is_speaking rises within 60 ms of playback start.
    2. At least 55 distinct RMS values are sampled per second during audio delivery.
    """
    shm_name = "test_metrics_ring_shm"
    shm = AudioMetricsSharedMemory(name=shm_name, create=True)
    stop_event = threading.Event()
    ndi = MockNDISender()

    sr = 48000
    duration_s = 1.0
    t_tone = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False, dtype=np.float32)
    # 1kHz carrier with gentle 3Hz amplitude envelope so each 16.67ms hop has a unique RMS
    envelope = 0.45 + 0.25 * np.sin(2 * np.pi * 3.0 * t_tone)
    tone = (envelope * np.sin(2 * np.pi * 1000.0 * t_tone)).astype(np.float32)
    stereo_tone = np.column_stack((tone, tone))

    # Pre-fill audio into shared memory ring buffer and open utterance
    shm.set_utterance_state(True)
    shm.write_audio_samples(stereo_tone)

    pump_thread = threading.Thread(
        target=ndi_audio_pump,
        args=(ndi, shm, stop_event, 2400, sr),
        name="test_audio_pump",
        daemon=True,
    )

    t0 = time.time()
    pump_thread.start()

    # Sample at 60 Hz for 1.05s
    samples = []
    speaking_first_true_time = None
    target_dt = 1.0 / 60.0  # 16.67 ms

    t_end = time.time() + 1.05
    while time.time() < t_end:
        t_sample = time.time()
        m = shm.read_metrics_for(t_sample)
        samples.append((t_sample - t0, m["rms"], m["is_speaking"], m["timestamp"]))
        if m["is_speaking"] and speaking_first_true_time is None:
            speaking_first_true_time = t_sample - t0
        time.sleep(target_dt)

    stop_event.set()
    pump_thread.join(timeout=2.0)

    shm.close()
    shm.unlink()

    # 1. is_speaking rise check (< 60 ms)
    assert speaking_first_true_time is not None, "is_speaking never became True during 1kHz tone"
    assert speaking_first_true_time < 0.060, f"is_speaking took {speaking_first_true_time*1000:.1f}ms to rise (>= 60ms)"

    # 2. Count distinct non-zero RMS updates during the active audio delivery
    active_rms_vals = [s[1] for s in samples if s[1] > 0.05]
    distinct_rms_count = len(set(round(val, 5) for val in active_rms_vals))
    print(f"Total 60Hz samples: {len(samples)}, Active RMS samples: {len(active_rms_vals)}, Distinct RMS values: {distinct_rms_count}")

    assert distinct_rms_count >= 55, f"Expected >= 55 distinct RMS updates/sec, got {distinct_rms_count}"
