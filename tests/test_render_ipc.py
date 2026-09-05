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


def test_shared_memory_long_reflection_audio_no_cutoff():
    """Verifies that full-length reflections (e.g. 10s = 480,000 samples) play completely without truncation."""
    shm_w = AudioMetricsSharedMemory(name="pytest_long_refl_shm", create=True)
    shm_r = AudioMetricsSharedMemory(name="pytest_long_refl_shm", create=False)

    # 10.0 seconds of speech at 48kHz (480,000 samples)
    total_samples = 480000
    long_speech_audio = np.random.uniform(-0.8, 0.8, (total_samples, 2)).astype(np.float32)

    # Push full 10-second reflection at once (just like app.py does)
    shm_w.write_audio_samples(long_speech_audio)

    # Drain frame by frame (800 samples @ 60fps = 600 frames)
    frames = total_samples // 800
    drained_chunks = []
    for _ in range(frames):
        chunk = shm_r.read_audio_samples(800)
        drained_chunks.append(chunk)

    reconstructed_audio = np.vstack(drained_chunks)
    assert np.allclose(long_speech_audio, reconstructed_audio, atol=1e-6)

    # Verify that once 10 seconds are drained, buffer outputs silence
    silence_check = shm_r.read_audio_samples(800)
    assert np.all(silence_check == 0.0)

    shm_r.close()
    shm_w.close()
    shm_w.unlink()


def test_spsc_ring_buffer_concurrency():
    """Verifies that concurrent single-producer single-consumer read/write streams without sample loss."""
    import threading
    from render_worker import RING_BUFFER_FRAMES
    import struct

    shm_w = AudioMetricsSharedMemory(name="pytest_spsc_concur_shm", create=True)
    shm_r = AudioMetricsSharedMemory(name="pytest_spsc_concur_shm", create=False)

    # 3.0 seconds of audio streamed in 800-sample chunks (180 chunks)
    total_chunks = 180
    chunk_samples = 800
    test_data = np.random.uniform(-0.5, 0.5, (total_chunks * chunk_samples, 2)).astype(np.float32)

    collected = []
    stop_event = threading.Event()

    def _reader_thread():
        while len(collected) < total_chunks and not stop_event.is_set():
            buf = shm_r.shm.buf
            r_pos = struct.unpack_from("=I", buf, 148)[0]
            w_pos = struct.unpack_from("=I", buf, 144)[0]
            avail = (w_pos - r_pos) % RING_BUFFER_FRAMES
            if avail >= chunk_samples:
                chunk = shm_r.read_audio_samples(chunk_samples)
                collected.append(chunk)
            else:
                time.sleep(0.0005)

    thread = threading.Thread(target=_reader_thread)
    thread.start()

    # Writer streams chunks
    for i in range(total_chunks):
        chunk = test_data[i * chunk_samples : (i + 1) * chunk_samples]
        shm_w.write_audio_samples(chunk)
        time.sleep(0.001)

    thread.join(timeout=5.0)
    stop_event.set()
    assert len(collected) == total_chunks

    reconstructed = np.vstack(collected)
    assert np.allclose(test_data, reconstructed, atol=1e-6)

    shm_r.close()
    shm_w.close()
    shm_w.unlink()


def test_shm_page_alignment_and_loud_failure():
    """Verifies that AUDIO_SHM_SIZE is 4096-aligned and attach fails loudly with RuntimeError."""
    from render_worker import AUDIO_SHM_SIZE

    # 1. Verify page alignment
    assert AUDIO_SHM_SIZE % 4096 == 0

    # 2. Verify loud failure when trying to attach to non-existent segment
    with pytest.raises(RuntimeError):
        AudioMetricsSharedMemory(name="non_existent_shm_test_segment_xyz", create=False)


def test_audio_analysis_processor_metrics_and_speaking_state():
    """Verifies that AudioAnalysisProcessor extracts RMS, speaking state, and multi-band spectrum from audio."""
    from render_worker import AudioAnalysisProcessor

    analyzer = AudioAnalysisProcessor(sample_rate=48000, num_spectrum_bands=32)

    # 1. Silence packet -> is_speaking is False, rms < 1e-4
    silence = np.zeros((800, 2), dtype=np.float32)
    m_silence = analyzer.process(silence)
    assert m_silence["is_speaking"] is False
    assert m_silence["rms"] < 1e-4

    # 2. 440 Hz Sine Tone -> is_speaking is True, rms > 0.1, non-zero spectrum
    t = np.linspace(0, 800 / 48000.0, 800, endpoint=False)
    tone = np.column_stack((0.5 * np.sin(2 * np.pi * 440 * t), 0.5 * np.sin(2 * np.pi * 440 * t))).astype(np.float32)
    m_tone = analyzer.process(tone)
    assert m_tone["is_speaking"] is True
    assert m_tone["rms"] > 0.1
    assert np.any(m_tone["spectrum"] > 0.0)
    assert len(m_tone["spectrum"]) == 32



