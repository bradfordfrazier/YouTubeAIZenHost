"""
Utterance-open ordering tests: the render worker must never observe
"utterance open but ring empty" at the start of a turn (false underrun + fade-in on
the first syllable).
"""

from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tts_engine import TTSEngine  # noqa: E402
from render_worker import AudioMetricsSharedMemory  # noqa: E402


def test_engine_announces_open_only_after_first_chunk_is_in_sink():
    e = TTSEngine()
    e.ndi_buffer_enabled = False
    events = []
    e.ndi_sink = lambda audio: events.append(("data", len(audio)))
    e.utterance_state_sink = lambda open_: events.append(("open", open_))

    e.begin_utterance()
    assert events == [], "begin_utterance must not announce open before any data exists"
    e.push_audio(np.zeros((4800, 2), dtype=np.float32))
    e.push_audio(np.zeros((4800, 2), dtype=np.float32))
    e.end_utterance()

    kinds = [k for k, _ in events]
    assert kinds[0] == "data", "first chunk must reach the ring before open=True"
    assert events[1] == ("open", True)
    assert kinds.count("open") == 2 and events[-1] == ("open", False)

    # clear also closes
    events.clear()
    e.begin_utterance(); e.push_audio(np.zeros((480, 2), dtype=np.float32)); e.clear_audio_buffer()
    assert events[-1] == ("open", False)


def test_ring_reader_ignores_empty_before_first_data():
    shm = AudioMetricsSharedMemory(name="iam_test_utt_ring", create=True)
    try:
        shm.set_utterance_state(True)
        # Open but nothing written yet: must not arm the resume fade or count as starvation
        pkt = shm.read_audio_samples(800)
        assert not shm._resume_pending
        assert shm._consumed_since_open == 0

        # Now data arrives; the first packet must be untouched (no fade-in)
        shm.write_audio_samples(np.ones((2400, 2), dtype=np.float32) * 0.5)
        pkt = shm.read_audio_samples(800)
        assert np.allclose(pkt, 0.5), "first real packet must not be faded in"

        # Drain to empty while still open -> now this IS starvation
        shm.read_audio_samples(800); shm.read_audio_samples(800)
        shm.read_audio_samples(800)  # empty read
        assert shm._resume_pending is True
        shm.set_utterance_state(False)
    finally:
        shm.close(); shm.unlink()
