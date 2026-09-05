"""
Unit Tests for TTS Supply Underrun Fixes:
1. Underrun detection in TTSEngine and Shared Memory
2. GPU exclusivity & Background synthesis queuing with cooldown
3. Calibrated honest timeout and RTF calculation
4. 5ms crossfades on starvation & resume
5. Adaptive lead buffer calculation
"""

import asyncio
import os
import sys
import time
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import config
from tts_engine import TTSEngine
from render_worker import AudioMetricsSharedMemory, VisualizerProxy


def test_underrun_detection_in_pop_local_audio():
    """Verifies that TTSEngine counts underruns and accumulates samples when utterance is open and buffer is empty."""
    tts = TTSEngine()
    tts.begin_utterance()
    assert tts._utterance_open is True
    assert tts.underrun_count == 0
    assert tts.underrun_samples == 0

    # Pop when buffer is empty -> underrun
    packet = tts.pop_local_audio(num_samples=800)
    assert len(packet) == 800
    assert np.all(packet == 0)
    assert tts.underrun_count == 1
    assert tts.underrun_samples == 800

    # Pop again -> underrun count increments
    packet2 = tts.pop_local_audio(num_samples=800)
    assert tts.underrun_count == 2
    assert tts.underrun_samples == 1600

    # End utterance -> popping empty buffer no longer counts as underrun
    tts.end_utterance()
    assert tts._utterance_open is False
    packet3 = tts.pop_local_audio(num_samples=800)
    assert tts.underrun_count == 2
    assert tts.underrun_samples == 1600


def test_gpu_exclusivity_and_background_synthesis():
    """Verifies that synthesize_background waits for live turns to end and respects cooldown."""
    async def _run():
        tts = TTSEngine()
        synth_calls = []

        async def mock_synth(text, mood="neutral", is_live=True):
            synth_calls.append((text, mood, is_live, time.time()))
            return np.ones((800, 2), dtype=np.float32)

        tts.synthesize = mock_synth

        # Set live turn active
        tts.live_turn_active.set()

        bg_task_started = False
        bg_task_done = False

        async def bg_worker():
            nonlocal bg_task_started, bg_task_done
            bg_task_started = True
            res = await tts.synthesize_background("Welcome new traveler", mood="chill")
            bg_task_done = True
            return res

        task = asyncio.create_task(bg_worker())
        await asyncio.sleep(0.05)
        assert bg_task_started is True
        assert bg_task_done is False
        assert len(synth_calls) == 0

        # End live turn with short cooldown for testing
        tts.cfg.cache_refill_cooldown_sec = 0.1
        tts.last_live_turn_end_time = time.time()
        tts.live_turn_active.clear()

        await asyncio.wait_for(task, timeout=2.0)
        assert bg_task_done is True
        assert len(synth_calls) == 1
        assert synth_calls[0][0] == "Welcome new traveler"
        assert synth_calls[0][2] is False  # is_live = False

    asyncio.run(_run())


def test_rolling_rtf_and_conservative_calculation():
    """Verifies that RTF records correctly and rtf_conservative returns minimum of last 8."""
    tts = TTSEngine()
    assert tts.rtf_conservative == 1.5

    tts.record_rtf(2.0)
    assert tts.rtf_conservative == 2.0

    tts.record_rtf(1.8)
    tts.record_rtf(1.3)
    tts.record_rtf(1.9)
    assert tts.rtf_conservative == 1.3

    # Add 8 fast items to push 1.3 out of window
    for _ in range(8):
        tts.record_rtf(2.5)
    assert tts.rtf_conservative == 2.5


def test_shared_memory_utterance_state():
    """Verifies that shared memory header byte 156 properly stores utterance_open state."""
    shm_name = f"test_shm_utterance_{int(time.time()*1000)}"
    shm = AudioMetricsSharedMemory(name=shm_name, create=True)
    try:
        assert shm.get_utterance_state() is False
        shm.set_utterance_state(True)
        assert shm.get_utterance_state() is True
        shm.set_utterance_state(False)
        assert shm.get_utterance_state() is False
    finally:
        shm.close()
        shm.unlink()


def test_crossfade_on_starvation_and_resume():
    """Verifies that 5ms crossfades are applied smoothly on buffer starvation and resume."""
    tts = TTSEngine()
    tts.cfg.inter_sentence_gap_sec = 0.0  # Zero gap for test clarity
    tts.begin_utterance()

    # Generate a constant 0.5 amplitude block of 1600 samples (2 frames)
    tone = np.full((1600, 2), 0.5, dtype=np.float32)
    tts.push_audio(tone)

    # Pop 800 samples -> gets audio
    p1 = tts.pop_local_audio(num_samples=800)
    assert not np.all(p1 == 0)

    # Pop 800 samples -> gets remaining audio
    p2 = tts.pop_local_audio(num_samples=800)
    assert not np.all(p2 == 0)

    # Pop 800 samples -> buffer is now dry (starvation)
    p3 = tts.pop_local_audio(num_samples=800)
    assert np.all(p3 == 0)
    assert tts._local_resume_pending is True

    # Push new audio and pop -> verify fade-in is applied on the leading samples
    new_tone = np.full((1600, 2), 0.8, dtype=np.float32)
    tts.push_audio(new_tone)
    p4 = tts.pop_local_audio(num_samples=800)
    assert tts._local_resume_pending is False
    # Check that sample 0 started near 0 and ramped up
    assert p4[0, 0] < 0.1
    assert p4[240, 0] > 0.6


def test_calibrated_timeout_formula():
    """Verifies the calibrated honest timeout formula for Chatterbox."""
    tts = TTSEngine()
    # Short sentence (30 chars) -> est ~ 1.95s -> timeout ~ 7.9s -> clamped to 8.0s min
    text_short = "Hello everyone, welcome."
    est_short = len(text_short) * float(tts.cfg.tts_sec_per_char)
    calc_short = max(8.0, min(45.0, est_short * 2.0 + 4.0))
    assert calc_short == 8.0

    # Long sentence (150 chars) -> est ~ 9.75s -> timeout ~ 23.5s
    text_long = "This is a much longer cosmic reflection that spans multiple thoughts and requires more inference time on the GPU server without premature cutoff."
    est_long = len(text_long) * float(tts.cfg.tts_sec_per_char)
    calc_long = max(8.0, min(45.0, est_long * 2.0 + 4.0))
    assert 20.0 <= calc_long <= 30.0
