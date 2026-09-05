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
