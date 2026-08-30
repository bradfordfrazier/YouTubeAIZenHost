"""
Phase 5 Test Suite: Broadcast Hardening & Observability (E3, E4).
Validates rate-limit/quota circuit breaker defense and stream health observability metrics.
"""

import asyncio
from pathlib import Path
import shutil
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock

from ai_brain import AIBrain
from session_log import SessionLogger


async def test_circuit_breaker_defense():
    print("\n" + "=" * 50)
    print("TEST 1: Rate-Limit & Quota Defense Circuit Breaker (E3)")
    print("=" * 50)

    brain = AIBrain()
    # Configure mock client that throws network/quota errors
    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(side_effect=RuntimeError("429 Too Many Requests: Resource exhausted"))
    brain.client = mock_client
    brain.max_consecutive_errors = 3
    brain.circuit_breaker_cooldown_sec = 2.0  # 2.0s cooldown for test

    assert brain.circuit_breaker_tripped is False
    assert brain.consecutive_gemini_errors == 0

    # 1. First failure
    events1 = []
    async for ev in brain.generate_response_stream("Hello 1"):
        events1.append(ev)
    assert brain.consecutive_gemini_errors == 1
    assert brain.circuit_breaker_tripped is False
    assert any(e["type"] == "complete" for e in events1)

    # 2. Second failure
    async for _ in brain.generate_response_stream("Hello 2"):
        pass
    assert brain.consecutive_gemini_errors == 2
    assert brain.circuit_breaker_tripped is False

    # 3. Third failure -> trips circuit breaker
    async for _ in brain.generate_response_stream("Hello 3"):
        pass
    assert brain.consecutive_gemini_errors == 3
    assert brain.circuit_breaker_tripped is True
    print(f"-> Verified circuit breaker tripped after 3 consecutive failures: reset_time={brain.circuit_breaker_reset_time}")

    # 4. Immediate fourth call during cooldown -> routes to simulation without calling client
    mock_client.aio.models.generate_content_stream.reset_mock()
    events4 = []
    async for ev in brain.generate_response_stream("Hello 4"):
        events4.append(ev)
    assert mock_client.aio.models.generate_content_stream.call_count == 0, "Expected bypass of Gemini API during circuit breaker trip"
    assert any(e["type"] == "complete" for e in events4)
    print("-> Verified active trip bypassed Gemini client completely and routed to fallback stream")

    # 5. Wait for cooldown to elapse
    await asyncio.sleep(2.1)

    # 6. Mock client recovers
    async def mock_stream_gen():
        chunk = MagicMock()
        chunk.text = "[MOOD: thoughtful] Peace returns to the network."
        yield chunk

    mock_client.aio.models.generate_content_stream = AsyncMock(return_value=mock_stream_gen())

    events5 = []
    async for ev in brain.generate_response_stream("Hello 5"):
        events5.append(ev)
    assert brain.circuit_breaker_tripped is False
    assert brain.consecutive_gemini_errors == 0
    print("-> Verified circuit breaker half-open probe recovery and reset to HEALTHY")
    print("[PASS] Circuit Breaker Defense verified successfully!")


def test_observability_telemetry():
    print("\n" + "=" * 50)
    print("TEST 2: Stream Health Observability Metrics (E4)")
    print("=" * 50)

    test_dir = Path(tempfile.mkdtemp(prefix="test_hud_"))
    try:
        logger = SessionLogger(log_dir=str(test_dir), session_id="test_hud_session_001")

        logger.log_chat_message("CosmicGamer", "user", "Hello Oracle!", False, "")
        logger.log_chat_message("ZenSeeker", "member", "What is peace?", False, "")
        logger.log_cast_question("Existential Dave", "ExistentialDave", "cast", "What is the observer?")

        logger.log_ai_turn(
            trigger="What is peace?",
            event_type="chat",
            full_text="Peace is the absence of resistance to what is.",
            mood="transcendent",
            exaggeration=0.6,
            tts_backend="edge_tts",
            turn_latency_sec=1.45,
            audio_duration_sec=3.2,
            author="ZenSeeker",
        )

        logger.log_ai_turn(
            trigger="What is the observer?",
            event_type="cast",
            full_text="The observer is the looking itself.",
            mood="thoughtful",
            exaggeration=0.45,
            tts_backend="edge_tts",
            turn_latency_sec=1.15,
            audio_duration_sec=2.8,
            author="ExistentialDave",
            is_cast=True,
        )

        metrics = logger.get_stream_health_metrics()
        assert metrics["session_id"] == "test_hud_session_001"
        assert metrics["total_turns"] == 2
        assert metrics["total_chats"] == 2
        assert metrics["total_cast_questions"] == 1
        assert metrics["recent_turns_analyzed"] == 2
        assert metrics["avg_latency_sec"] == 1.3  # (1.45 + 1.15) / 2 = 1.3

        print(f"-> Verified Telemetry Metrics: {metrics}")
        print("[PASS] Observability Telemetry verified successfully!")

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


async def run_all_phase5_tests():
    print("\n" + "#" * 60)
    print("RUNNING PHASE 5 VERIFICATION TEST SUITE")
    print("#" * 60)

    await test_circuit_breaker_defense()
    test_observability_telemetry()

    print("\n" + "#" * 60)
    print("ALL PHASE 5 TESTS PASSED PERFECTLY!")
    print("#" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_phase5_tests())
