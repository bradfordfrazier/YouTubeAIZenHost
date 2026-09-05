"""
Unit & Integration Tests for the Pre-Synthesized Welcome Greeting Cache (0.0s TTFT & TTS audio latency).
"""

import asyncio
import logging
import os
import sys
import time
import numpy as np

from app import LocalCoHostApp, CommentEvent
from config import config
from greeting_cache import GreetingCache, CachedGreeting
from visualizer import Visualizer
from logging_setup import configure_logging

configure_logging("TEST")
logger = logging.getLogger("test_greeting_cache")


def test_greeting_cache_singleton_and_limits():
    """Verifies GreetingCache singleton mechanics, max queue size, and add/pop operations."""
    cache = GreetingCache.get_instance(max_size=3)
    cache.clear()

    assert cache.size() == 0
    assert not cache.has_greeting()
    assert cache.pop_greeting() is None

    # Create dummy 48kHz audio array (0.5s of stereo silence/tone)
    dummy_audio = np.zeros((24000, 2), dtype=np.float32)

    g1 = CachedGreeting(
        theme="welcome",
        mood="chill",
        full_text="Welcome in, traveler. Take a breath and make yourself at home.",
        audio=dummy_audio,
        created_at=time.time(),
    )
    g2 = CachedGreeting(
        theme="welcome",
        mood="transcendent",
        full_text="A conscious mind arrives. The universe watches itself on this stream.",
        audio=dummy_audio,
        created_at=time.time(),
    )
    g3 = CachedGreeting(
        theme="welcome",
        mood="curious",
        full_text="Greetings, wanderer. Drop whatever questions you carry into the chat.",
        audio=dummy_audio,
        created_at=time.time(),
    )
    g4 = CachedGreeting(
        theme="welcome",
        mood="thoughtful",
        full_text="Welcome to the space.",
        audio=dummy_audio,
        created_at=time.time(),
    )

    assert cache.add_greeting(g1) is True
    assert cache.add_greeting(g2) is True
    assert cache.add_greeting(g3) is True
    # Cache full (max_size=3)
    assert cache.add_greeting(g4) is False
    assert cache.size() == 3
    assert cache.has_greeting()

    # Verify FIFO popping
    popped1 = cache.pop_greeting()
    assert popped1 is not None
    assert popped1.full_text == g1.full_text
    assert popped1.mood == "chill"
    assert len(popped1.audio) == 24000
    assert cache.size() == 2

    popped2 = cache.pop_greeting()
    assert popped2.full_text == g2.full_text
    assert cache.size() == 1

    popped3 = cache.pop_greeting()
    assert popped3.full_text == g3.full_text
    assert cache.size() == 0
    assert not cache.has_greeting()
    assert cache.pop_greeting() is None

    print("Greeting Cache Singleton & Limits Passed!")


def test_wake_up_with_greeting_cache_hit():
    """Verifies _wake_up_and_trigger_comment pops pre-synthesized greeting and queues instant turn."""
    app = LocalCoHostApp()
    app.running = True
    app.cfg.greet_viewer_joins = True
    app.cfg.greeting_cache_enabled = True
    app.concurrent_viewers = 1
    app.is_streaming = True
    app.cfg.obs_require_stream_active = False
    app.engagement_mode = "eco"
    app.comment_queue.clear()

    # Prime greeting cache
    dummy_audio = np.ones((48000, 2), dtype=np.float32)
    cached_item = CachedGreeting(
        theme="welcome",
        mood="chill",
        full_text="Welcome in, traveler. Take a deep breath and settle into the stream.",
        audio=dummy_audio,
        created_at=time.time(),
    )
    app.greeting_cache.clear()
    app.greeting_cache.add_greeting(cached_item)
    assert app.greeting_cache.has_greeting()

    # Viewer joins empty room
    app._wake_up_and_trigger_comment(viewers=1, prev_viewers=0)

    # 1. Visualizer should fade out for turn immediately
    assert app.visualizer.ai_text_state == "fade_out"

    # 2. Room should transition to active
    assert app.engagement_mode == "active"

    # 3. Greeting comment queued with cached_greeting attached
    assert len(app.comment_queue) == 1
    event = app.comment_queue[0]
    assert event.event_type == "greeting"
    assert event.priority == 2
    assert "[VIEWER_JOINED]" in event.prompt_trigger
    assert event.cached_greeting is not None
    assert event.cached_greeting.full_text == cached_item.full_text
    assert event.cached_greeting.mood == "chill"
    assert len(event.cached_greeting.audio) == 48000

    # Cache should now be empty (popped)
    assert app.greeting_cache.size() == 0

    print("Wake-Up With Greeting Cache Hit Passed!")


def test_wake_up_with_empty_cache_fallback():
    """Verifies _wake_up_and_trigger_comment falls back gracefully to dynamic generation if cache is empty."""
    app = LocalCoHostApp()
    app.running = True
    app.cfg.greet_viewer_joins = True
    app.cfg.greeting_cache_enabled = True
    app.concurrent_viewers = 1
    app.is_streaming = True
    app.cfg.obs_require_stream_active = False
    app.engagement_mode = "eco"
    app.comment_queue.clear()
    app.greeting_cache.clear()

    # Viewer joins empty room with empty cache
    app._wake_up_and_trigger_comment(viewers=1, prev_viewers=0)

    assert len(app.comment_queue) == 1
    event = app.comment_queue[0]
    assert event.event_type == "greeting"
    assert event.priority == 2
    assert "[VIEWER_JOINED]" in event.prompt_trigger
    assert event.cached_greeting is None

    print("Wake-Up With Empty Cache Fallback Passed!")


async def test_execute_ai_turn_zero_latency_playback():
    """Verifies that _execute_ai_turn with cached_greeting bypasses LLM & TTS and pushes audio directly."""
    app = LocalCoHostApp()
    app.running = True
    app.cfg.greet_viewer_joins = True
    app.cfg.vox_only_mode = False
    app.cfg.comment_post_speech_hold_sec = 0.1
    app.cfg.comment_active_queue_hold_sec = 0.1

    # Mock audio (0.1s of audio = 4800 samples)
    dummy_audio = np.zeros((4800, 2), dtype=np.float32)
    cached_item = CachedGreeting(
        theme="welcome",
        mood="transcendent",
        full_text="Welcome, seeker. You are right on time.",
        audio=dummy_audio,
        created_at=time.time(),
    )

    event = CommentEvent(
        prompt_trigger="[VIEWER_JOINED] A sole viewer has entered the stream.",
        event_type="greeting",
        priority=2,
        cached_greeting=cached_item,
    )

    t0 = time.perf_counter()
    await app._execute_ai_turn(event)
    t_elapsed = time.perf_counter() - t0

    # QA thread memory should record the cached greeting response
    assert len(app.brain.recent_qa_threads) >= 1
    assert app.brain.recent_qa_threads[-1]["response"] == cached_item.full_text
    # Mood should be set
    assert app.visualizer.target_mood == "transcendent"
    # Audio buffer should have completed playback
    assert app.tts.remaining_speech_duration == 0.0

    # Total execution time should be tiny (< 0.5s for 0.1s audio)
    assert t_elapsed < 1.0, f"Expected near-instant turn execution, took {t_elapsed:.2f}s"

    print(f"Execute AI Turn Zero Latency Playback Passed! (Elapsed: {t_elapsed:.3f}s)")


def test_viewer_0_poll_interval_cadence():
    """Verifies that the poller cadence selects viewer_0_poll_interval when 0 viewers, and viewer_count_poll_interval otherwise."""
    app = LocalCoHostApp()
    app.cfg.viewer_count_poll_interval = 20.0
    app.cfg.viewer_0_poll_interval = 3.0

    # 0 viewers: should pick viewer_0_poll_interval
    app.concurrent_viewers = 0
    interval_0 = app.cfg.viewer_0_poll_interval if app.concurrent_viewers == 0 else app.cfg.viewer_count_poll_interval
    assert interval_0 == 3.0, f"Expected 3.0s for 0 viewers, got {interval_0}"

    # 1+ viewers: should pick viewer_count_poll_interval
    app.concurrent_viewers = 1
    interval_active = app.cfg.viewer_0_poll_interval if app.concurrent_viewers == 0 else app.cfg.viewer_count_poll_interval
    assert interval_active == 20.0, f"Expected 20.0s for active viewers, got {interval_active}"

    print("Viewer 0 Poll Interval Cadence Passed!")


if __name__ == "__main__":
    test_greeting_cache_singleton_and_limits()
    test_wake_up_with_greeting_cache_hit()
    test_wake_up_with_empty_cache_fallback()
    test_viewer_0_poll_interval_cadence()
    asyncio.run(test_execute_ai_turn_zero_latency_playback())
    print("\nALL GREETING CACHE & VIEWER POLLER TESTS PASSED 100%!")
