"""
Unit tests for shared memory IPC and VisualizerProxy (Phase 5).
Runnable via pytest.
"""

from pathlib import Path
import sys
import time
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from render_worker import AudioMetricsSharedMemory


def test_shared_memory_metrics_roundtrip():
    shm_w = AudioMetricsSharedMemory(name="pytest_audio_shm", create=True)
    shm_r = AudioMetricsSharedMemory(name="pytest_audio_shm", create=False)

    rms_in = 0.725
    speaking_in = True
    spec_in = np.random.uniform(0.0, 1.0, 32).astype(np.float32)
    ts_in = time.time()

    shm_w.write(rms_in, speaking_in, spec_in, ts_in)
    out = shm_r.read()

    assert abs(out["rms"] - rms_in) < 1e-5
    assert out["is_speaking"] is True
    assert np.allclose(out["spectrum"], spec_in, atol=1e-5)
    assert abs(out["timestamp"] - ts_in) < 1e-4

    shm_r.close()
    shm_w.close()
    shm_w.unlink()


def test_shared_memory_audio_ring_buffer_roundtrip():
    shm_w = AudioMetricsSharedMemory(name="pytest_audio_ring_shm", create=True)
    shm_r = AudioMetricsSharedMemory(name="pytest_audio_ring_shm", create=False)

    # 1. Write 800 stereo samples
    sample_audio = np.random.uniform(-0.5, 0.5, (800, 2)).astype(np.float32)
    shm_w.write_audio_samples(sample_audio)

    # Read back exactly 800 samples
    read_audio = shm_r.read_audio_samples(800)
    assert np.allclose(sample_audio, read_audio, atol=1e-6)

    # Subsequent read on empty buffer returns zeros
    empty_audio = shm_r.read_audio_samples(800)
    assert np.all(empty_audio == 0.0)

    # 2. Test multi-chunk write and read
    chunk1 = np.ones((400, 2), dtype=np.float32) * 0.3
    chunk2 = np.ones((400, 2), dtype=np.float32) * 0.7
    shm_w.write_audio_samples(chunk1)
    shm_w.write_audio_samples(chunk2)

    combined_read = shm_r.read_audio_samples(800)
    assert np.allclose(combined_read[:400], chunk1, atol=1e-6)
    assert np.allclose(combined_read[400:], chunk2, atol=1e-6)

    # 3. Test clear
    shm_w.write_audio_samples(sample_audio)
    shm_w.clear_audio()
    cleared_read = shm_r.read_audio_samples(800)
    assert np.all(cleared_read == 0.0)

    shm_r.close()
    shm_w.close()
    shm_w.unlink()
