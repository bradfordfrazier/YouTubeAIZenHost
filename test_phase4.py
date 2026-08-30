"""
Phase 4 Test Suite: Intelligence Leverage & Dynamic Thinking Architecture (D1, D2, D3).
Validates dynamic two-tier thinking budget, intent classification,
pre-computed reflection cache, and zero-latency spontaneous commentary.
"""

import asyncio
import time

from ai_brain import AIBrain
from config import config
from reflection_cache import ReflectionCache, CachedReflection


def test_intent_classification_and_depth():
    print("\n" + "=" * 50)
    print("TEST 1: Intent Classification for Two-Tier Thinking (D1, D3)")
    print("=" * 50)

    brain = AIBrain()

    # Fast triggers (should return False)
    fast_triggers = [
        "[NEW_CHATTER_GREETING] @Neo just arrived!",
        "[CELEBRATION] @Alice joined as member!",
        "[VIEWER_JOINED] Traveler joined",
        "[CHAT_ENCOURAGEMENT] Chat is quiet",
        "Chat message from @Gamer: 'Hey I Am what's up!'",
        "Chat message from @Bob: 'LOL that was hilarious'",
    ]
    for trig in fast_triggers:
        assert brain._classify_prompt_depth(trig) is False, f"Expected FAST for '{trig}'"
    print(f"-> Verified {len(fast_triggers)} fast banter/greeting triggers")

    # Deep triggers (should return True)
    deep_triggers = [
        "Chat message from @Sarah: 'I lost someone I love and grief feels unbearable. Where did they go?'",
        "Cast member @ExistentialDave asks: 'Where is the observer in consciousness?'",
        "Chat message from @Neo: 'What is the true nature of free will and the void?'",
        "Chat message from @Philosopher: 'Why does anything exist rather than nothing?'",
        "Chat message from @Seeker: 'What happens to the soul after death?'",
    ]
    for trig in deep_triggers:
        assert brain._classify_prompt_depth(trig) is True, f"Expected DEEP for '{trig}'"
    print(f"-> Verified {len(deep_triggers)} deep philosophical/existential triggers")

    # Verify config generation
    cfg_fast = brain._build_generate_content_config(is_deep=False)
    cfg_deep = brain._build_generate_content_config(is_deep=True)

    if cfg_fast and cfg_deep:
        # If new Google GenAI SDK is active
        if hasattr(cfg_fast, "thinking_config") and cfg_fast.thinking_config:
            assert cfg_fast.thinking_config.thinking_budget in (64, 128) or hasattr(cfg_fast.thinking_config, "thinking_level")
        if hasattr(cfg_deep, "thinking_config") and cfg_deep.thinking_config:
            assert cfg_deep.thinking_config.thinking_budget in (512, 1024) or hasattr(cfg_deep.thinking_config, "thinking_level")
        assert cfg_deep.max_output_tokens >= cfg_fast.max_output_tokens

    print("[PASS] Intent classification & two-tier config verified!")


async def test_reflection_cache_operations():
    print("\n" + "=" * 50)
    print("TEST 2: Pre-Computed Spontaneous Reflection Cache (D2)")
    print("=" * 50)

    cache = ReflectionCache(max_size=3)
    assert cache.size() == 0
    assert cache.has_reflection() is False

    # 1. Add reflections
    item1 = CachedReflection(
        theme="The illusion of separation",
        mood="thoughtful",
        full_text="You are not a drop in the ocean. You are the entire ocean in a drop.",
        created_at=time.time(),
    )
    item2 = CachedReflection(
        theme="The nature of time",
        mood="transcendent",
        full_text="The clock is a collective agreement to pretend eternity has a schedule.",
        created_at=time.time(),
    )

    await cache.add_reflection(item1)
    await cache.add_reflection(item2)
    assert cache.size() == 2
    assert cache.has_reflection() is True

    # 2. Pop reflection in 0.0s
    t0 = time.perf_counter()
    popped = await cache.pop_reflection()
    dt = time.perf_counter() - t0
    assert popped is not None
    assert popped.theme == "The illusion of separation"
    assert popped.mood == "thoughtful"
    assert dt < 0.005, f"Cache pop took too long ({dt*1000:.2f}ms)"
    print(f"-> Popped cached reflection in {dt*1000:.3f}ms: '{popped.full_text}'")

    # 3. Pop second
    popped2 = await cache.pop_reflection()
    assert popped2.theme == "The nature of time"
    assert cache.size() == 0

    # 4. Pop empty
    popped3 = await cache.pop_reflection()
    assert popped3 is None
    print("[PASS] ReflectionCache operations verified!")


async def test_zero_latency_stream_delivery():
    print("\n" + "=" * 50)
    print("TEST 3: Zero-Latency Spontaneous Reflection Delivery")
    print("=" * 50)

    brain = AIBrain()
    # Prime reflection cache
    test_reflection = CachedReflection(
        theme="Imperfection",
        mood="transcendent",
        full_text="The cracked bowl lets the light through.",
        created_at=time.time(),
    )
    await brain.reflection_cache.add_reflection(test_reflection)

    # Trigger spontaneous reflection stream
    events = []
    t0 = time.perf_counter()
    async for ev in brain.generate_response_stream("[SPONTANEOUS_REFLECTION]"):
        events.append(ev)
    elapsed = time.perf_counter() - t0

    assert any(e.get("is_precomputed") for e in events), "Expected precomputed flag in stream response"
    complete_ev = next(e for e in events if e["type"] == "complete")
    assert complete_ev["full_text"] == "The cracked bowl lets the light through."
    assert complete_ev["mood"] == "transcendent"
    assert elapsed < 0.05, f"Stream delivery took too long ({elapsed*1000:.2f}ms)"
    print(f"-> Instant Spontaneous Reflection delivered in {elapsed*1000:.2f}ms: '{complete_ev['full_text']}'")
    print("[PASS] Zero-latency spontaneous stream verified!")


async def run_all_phase4_tests():
    print("\n" + "#" * 60)
    print("RUNNING PHASE 4 VERIFICATION TEST SUITE")
    print("#" * 60)

    test_intent_classification_and_depth()
    await test_reflection_cache_operations()
    await test_zero_latency_stream_delivery()

    print("\n" + "#" * 60)
    print("ALL PHASE 4 TESTS PASSED PERFECTLY!")
    print("#" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_phase4_tests())
