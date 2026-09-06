"""
Unit tests for Trigger, Classifier, and Queue Hygiene (Phase 3).
Runnable via pytest.
"""

import heapq
from pathlib import Path
import sys
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_brain import AIBrain
from app import CommentEvent, LocalCoHostApp


def test_trigger_hygiene_no_trigger_on_common_words():
    """'w', 'l', 'gg', 'lol', 'real', 'game', 'play', 'win', 'lose', 'god that game was trash' -> no trigger."""
    brain = AIBrain()
    brain.set_engagement_mode("active", is_stream_live=True, concurrent_viewers=15, is_chat_active=True)

    for word in ["w", "l", "gg", "lol", "real", "game", "play", "win", "lose", "again lol", "god that game was trash", "the bot died"]:
        trig, reason = brain.should_trigger_response(word)
        assert not trig, f"Expected '{word}' not to trigger, but triggered with reason: {reason}"
        assert reason == "no_trigger_keywords"


def test_trigger_hygiene_direct_mention():
    """'@IAM why do we dream?', 'ai, what is life?', 'hey god' -> direct_mention."""
    brain = AIBrain()
    brain.set_engagement_mode("active", is_stream_live=True, concurrent_viewers=5, is_chat_active=True)

    for phrase in ["@IAM why do we dream?", "@MassiveGodComplex thoughts?", "ai, explain this", "hey god give us wisdom", "bot: roast me"]:
        trig, reason = brain.should_trigger_response(phrase)
        assert trig, f"Expected '{phrase}' to trigger, but got False ({reason})"
        assert "direct_mention" in reason or "chat_question" in reason


def test_trigger_viewer_count_sampling():
    """High viewer counts (> 25) engage probabilistic sampling on generic chat keywords."""
    brain = AIBrain()
    # Active with 50 viewers
    brain.set_engagement_mode("active", is_stream_live=True, concurrent_viewers=50, is_chat_active=True)

    # When random exceeds sampling probability, should be sampled out
    with patch("random.random", return_value=0.90):
        trig, reason = brain.should_trigger_response("roast the team")
        assert not trig
        assert "sampled_out" in reason

    # When random is within probability, should trigger
    with patch("random.random", return_value=0.10):
        trig, reason = brain.should_trigger_response("roast the team")
        assert trig
        assert "chat_interaction" in reason


def test_prompt_depth_classifier_deep():
    """'I am scared of dying and losing everyone I love, what's the point' -> DEEP."""
    brain = AIBrain()
    prompt = "I am scared of dying and losing everyone I love, what's the point"
    is_deep, match = brain._classify_prompt_depth(prompt)
    assert is_deep is True
    assert match in ("dying", "death")


def test_prompt_depth_classifier_fast():
    """'god that game was trash' -> FAST."""
    brain = AIBrain()
    prompt = "god that game was trash"
    is_deep, reason = brain._classify_prompt_depth(prompt)
    assert is_deep is False


def test_superchat_always_triggers_regardless_of_sampling():
    """superchat -> always triggers regardless of sampling."""
    brain = AIBrain()
    brain.set_engagement_mode("active", is_stream_live=True, concurrent_viewers=100, is_chat_active=True)

    with patch("random.random", return_value=0.99):
        trig, reason = brain.should_trigger_response("generic comment", is_superchat=True)
        assert trig is True
        assert reason == "superchat"


def test_queue_superchat_prioritized_over_cast():
    """Queue test: superchat enqueued after 3 cast events is dequeued first."""
    queue = []
    t_now = time.time()

    e1 = CommentEvent(prompt_trigger="Cast 1", event_type="cast", priority=5, created_at=t_now, seq_id=1)
    e2 = CommentEvent(prompt_trigger="Cast 2", event_type="cast", priority=5, created_at=t_now + 0.01, seq_id=2)
    e3 = CommentEvent(prompt_trigger="Cast 3", event_type="cast", priority=5, created_at=t_now + 0.02, seq_id=3)

    heapq.heappush(queue, e1)
    heapq.heappush(queue, e2)
    heapq.heappush(queue, e3)

    e_sc = CommentEvent(prompt_trigger="Superchat $20", event_type="superchat", priority=1, created_at=t_now + 0.05, seq_id=4)
    heapq.heappush(queue, e_sc)

    popped = heapq.heappop(queue)
    assert popped.event_type == "superchat"
    assert popped.priority == 1
    assert popped.seq_id == 4

    next_pop = heapq.heappop(queue)
    assert next_pop.event_type == "cast"
    assert next_pop.seq_id == 1
    print("All trigger and queue unit tests passed!")


if __name__ == "__main__":
    test_trigger_hygiene_no_trigger_on_common_words()
    test_trigger_hygiene_direct_mention()
    test_prompt_depth_classifier_deep()
    test_prompt_depth_classifier_fast()
    test_superchat_always_triggers_regardless_of_sampling()
    test_queue_superchat_prioritized_over_cast()
    print("100% Phase 3 acceptance assertions passed.")
