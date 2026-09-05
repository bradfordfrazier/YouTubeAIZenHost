"""
Unit test for TTSEngine ndi_sink and ndi_clear_sink (Item 1).
"""

from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tts_engine import TTSEngine


def test_audio_sink_matches_local_buffer():
    """
    Creates a TTSEngine, attaches a sink that appends to a list, pushes two 1s chunks,
    and asserts the concatenated sink output equals the concatenated _audio_buffer_local sample-for-sample.
    """
    engine = TTSEngine()
    collected_sink = []

    def _custom_sink(chunk: np.ndarray):
        collected_sink.append(chunk.copy())

    engine.ndi_sink = _custom_sink

    sr = engine.sample_rate  # 48000
    # Two 1-second chunks of random stereo audio
    chunk1 = np.random.uniform(-0.5, 0.5, (sr, 2)).astype(np.float32)
    chunk2 = np.random.uniform(-0.5, 0.5, (sr, 2)).astype(np.float32)

    engine.begin_utterance()
    res1 = engine.push_audio(chunk1)
    res2 = engine.push_audio(chunk2)
    engine.end_utterance()

    assert len(collected_sink) == 2
    assert np.array_equal(res1, collected_sink[0])
    assert np.array_equal(res2, collected_sink[1])

    sink_total = np.vstack(collected_sink)
    # Compare with engine's internal _audio_buffer_local
    local_total = np.vstack([c[offset:] for c, offset in engine._audio_buffer_local])
    assert np.array_equal(sink_total, local_total)


def test_audio_clear_sink_called():
    """Verifies that clear_audio_buffer calls ndi_clear_sink."""
    engine = TTSEngine()
    cleared = False

    def _clear_sink():
        nonlocal cleared
        cleared = True

    engine.ndi_clear_sink = _clear_sink
    engine.clear_audio_buffer()
    assert cleared is True
