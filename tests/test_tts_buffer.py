"""
Unit test for TTSEngine fast lockless deque audio buffer (Item 2).
"""

from pathlib import Path
import sys
import threading
import time
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tts_engine import TTSEngine


def test_concurrent_push_and_pop_latency():
    """
    Pushes a 5s chunk, then in a thread calls pop_local_audio(480) 500 times
    while the main thread pushes another 5s chunk.
    Asserts:
    1. No pop call took longer than 2ms.
    2. Total popped audio matches the pushed audio in order.
    """
    engine = TTSEngine()
    sr = engine.sample_rate  # 48000

    # Two 5-second chunks
    chunk1 = np.random.uniform(-0.5, 0.5, (sr * 5, 2)).astype(np.float32)
    chunk2 = np.random.uniform(-0.5, 0.5, (sr * 5, 2)).astype(np.float32)

    engine.begin_utterance()
    processed1 = engine.push_audio(chunk1)

    pop_samples = 480
    num_pops = 500
    popped_chunks = []
    pop_latencies_ms = []

    def _consumer():
        for _ in range(num_pops):
            t0 = time.perf_counter()
            packet = engine.pop_local_audio(pop_samples)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            pop_latencies_ms.append(dt_ms)
            popped_chunks.append(packet)
            # Simulate PortAudio real-time callback interval (10ms for 480 samples @ 48kHz)
            time.sleep(0.0005)

    th = threading.Thread(target=_consumer)
    th.start()

    # While consumer is popping, main thread pushes second 5s chunk
    time.sleep(0.005)
    processed2 = engine.push_audio(chunk2)
    engine.end_utterance()

    th.join(timeout=5.0)
    assert not th.is_alive()

    # 1. Pop latency assertion: no call > 2ms (allowing small margin if OS context switches, but all in microsecond range)
    max_latency = max(pop_latencies_ms)
    print(f"Max pop latency: {max_latency:.4f}ms, Mean: {np.mean(pop_latencies_ms):.4f}ms")
    assert max_latency < 2.0, f"Pop call exceeded 2ms latency: {max_latency:.4f}ms"

    # 2. Audio fidelity assertion
    total_popped = np.vstack(popped_chunks)
    total_pushed = np.vstack((processed1, processed2))

    popped_len = len(total_popped)
    assert np.array_equal(total_popped, total_pushed[:popped_len])


def test_pop_audio_packet_slice_and_wrap():
    """Verifies that pop_audio_packet pops exact 800-sample chunks across boundary-crossing deque items."""
    engine = TTSEngine()
    sr = engine.sample_rate

    # Push 3 small chunks (500 samples, 700 samples, 600 samples)
    c1 = np.ones((500, 2), dtype=np.float32) * 0.1
    c2 = np.ones((700, 2), dtype=np.float32) * 0.2
    c3 = np.ones((600, 2), dtype=np.float32) * 0.3

    engine.begin_utterance()
    p1 = engine.push_audio(c1)
    p2 = engine.push_audio(c2)
    p3 = engine.push_audio(c3)
    engine.end_utterance()

    all_processed = np.vstack((p1, p2, p3))
    total_samples = len(all_processed)

    drained = []
    while engine.remaining_speech_duration > 0:
        _, interleaved = engine.pop_audio_packet(800)
        drained.append(interleaved)

    reconstructed = np.vstack(drained)
    # The valid audio portion should match all_processed exactly
    assert np.allclose(all_processed, reconstructed[:total_samples], atol=1e-6)
