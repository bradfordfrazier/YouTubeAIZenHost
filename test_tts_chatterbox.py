"""
Unit and Integration Tests for Dual-Backend TTS Engine (ChatterBox Turbo & Edge-TTS Fallback).
"""

import asyncio
import numpy as np

from config import config
from tts_engine import TTSEngine


async def test_offline_server_health_check_and_failover():
    print("\n" + "=" * 60)
    print("TEST 1: Offline Server Health Check & Automatic Fallback")
    print("=" * 60)

    # Configure engine pointing to an unreachable port to simulate server offline
    engine = TTSEngine()
    engine.server_url = "http://127.0.0.1:59999"  # Deliberately unreachable port
    engine.tts_backend = "chatterbox"
    engine.active_backend = "chatterbox"

    is_healthy = await engine.check_health()
    print(f"-> Health check result on unreachable server: {is_healthy}")
    print(f"-> Active backend automatically transitioned to: '{engine.active_backend}'")
    assert not is_healthy, "Expected health check to fail on unreachable server"
    assert engine.active_backend == "edge", "Expected active backend to failover to 'edge'"
    print("[PASS] Offline health check failover verified!")


async def test_synthesis_under_fallback_mode():
    print("\n" + "=" * 60)
    print("TEST 2: Synthesis Under Fallback Mode with Mood Tags")
    print("=" * 60)

    engine = TTSEngine()
    engine.active_backend = "edge"

    test_prompt = "[MOOD: hyped] Welcome to the stream! We are fully operational."
    audio = await engine.synthesize(test_prompt)

    print(f"-> Output audio shape: {audio.shape} (dtype: {audio.dtype})")
    assert audio.ndim == 2, "Expected 2D stereo array"
    assert audio.shape[1] == 2, "Expected 2 channels (stereo)"
    assert audio.dtype == np.float32, "Expected float32 PCM"
    assert len(audio) > 0, "Expected non-empty audio array"

    metrics = engine.get_audio_metrics()
    print(f"-> Metrics active_backend: '{metrics.get('active_backend')}'")
    assert metrics.get("active_backend") == "edge", "Expected 'edge' in audio metrics"
    print("[PASS] Synthesis under fallback verified successfully!")


async def test_mood_to_exaggeration_mapping():
    print("\n" + "=" * 60)
    print("TEST 3: Mood to Exaggeration Mapping")
    print("=" * 60)

    engine = TTSEngine()
    assert engine.mood_exaggeration_map.get("hyped") == 0.8
    assert engine.mood_exaggeration_map.get("savage") == 0.85
    assert engine.mood_exaggeration_map.get("chill") == 0.4
    assert engine.mood_exaggeration_map.get("deadpan") == 0.3
    print("-> Verified mood map: hyped=0.8, savage=0.85, chill=0.4, deadpan=0.3")
    print("[PASS] Mood mapping verified successfully!")


async def test_audio_buffer_and_frame_slicing():
    print("\n" + "=" * 60)
    print("TEST 4: Audio Buffer Lock & 60 FPS NDI Frame Slicing")
    print("=" * 60)

    engine = TTSEngine()
    await engine.queue_speech("[MOOD: thoughtful] Life is unfolding perfectly.")

    initial_dur = engine.remaining_speech_duration
    print(f"-> Queued audio duration: {initial_dur:.2f}s")
    assert initial_dur > 0.5, "Expected at least 0.5s audio queued"

    # Pop 5 frames (800 samples each = 4000 samples)
    for _ in range(5):
        planar, interleaved = engine.pop_audio_packet(800)
        assert planar.shape == (2, 800)
        assert interleaved.shape == (800, 2)

    after_dur = engine.remaining_speech_duration
    print(f"-> Remaining audio duration after 5 frames: {after_dur:.2f}s")
    assert after_dur < initial_dur, "Expected buffer duration to decrease as frames are popped"

    engine.clear_audio_buffer()
    assert engine.remaining_speech_duration == 0.0, "Expected buffer to be empty after clear"
    print("[PASS] Frame slicing and buffer management verified successfully!")


async def main():
    await test_offline_server_health_check_and_failover()
    await test_synthesis_under_fallback_mode()
    await test_mood_to_exaggeration_mapping()
    await test_audio_buffer_and_frame_slicing()
    print("\n" + "#" * 60)
    print("ALL CHATTERBOX & DUAL-BACKEND TTS TESTS PASSED PERFECTLY!")
    print("#" * 60)


if __name__ == "__main__":
    asyncio.run(main())
