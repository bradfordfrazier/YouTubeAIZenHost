"""
Phase 3 Test Suite: Trigger, Classifier, and Priority Queue Hygiene.
Validates:
1. Tightened trigger rules (no false substring matches for ai/bot/god/iam, cleaned chat_keywords).
2. Config-driven chat sampling above viewer threshold (questions/mentions/superchats exempt).
3. Stricter Deep-vs-Fast prompt depth classifier (>= 8 words AND reduced philosophical terms).
4. Heapq-backed min-priority comment queue (superchats prioritized over cast/chat, FIFO preserved).
"""

import asyncio
import heapq
import time
from unittest.mock import patch

from ai_brain import AIBrain, DEEP_PHILOSOPHICAL_TERMS
from app import CommentEvent, LocalCoHostApp
from config import config


def test_trigger_hygiene():
    print("\n" + "=" * 60)
    print("TEST 1: Tightened Trigger & Addressing Hygiene (Phase 3.1)")
    print("=" * 60)

    brain = AIBrain()
    brain.set_engagement_mode("active", is_stream_live=True, concurrent_viewers=5, is_chat_active=True)

    # 1. False substring matches must NOT trigger direct_mention
    false_positives = [
        "again lol",
        "robot is smart",
        "godzilla is huge",
        "diamond hands to the moon",
        "parliament debated today",
        "god that game was trash",
        "just playing a casual game",
    ]
    for text in false_positives:
        trig, reason = brain.should_trigger_response(text)
        assert not trig, f"Expected no trigger for '{text}', but got ({trig}, '{reason}')"
        print(f"  [PASS] Correctly rejected non-trigger: '{text}' -> {reason}")

    # 2. Legitimate direct mentions must trigger
    true_positives = [
        ("@IAM why do we dream?", "direct_mention"),
        ("ai, what is reality?", "direct_mention"),
        ("@ai help me understand", "direct_mention"),
        ("bot: explain consciousness", "direct_mention"),
        ("god? are you listening?", "direct_mention"),
        ("hey god why is there suffering", "direct_mention"),
        ("what do you think about existence", "direct_mention"),
        ("@MassiveGodComplex greetings", "direct_mention"),
    ]
    for text, expected_type in true_positives:
        trig, reason = brain.should_trigger_response(text)
        assert trig, f"Expected trigger for '{text}', but got ({trig}, '{reason}')"
        assert expected_type in reason, f"Expected '{expected_type}' in reason '{reason}'"
        print(f"  [PASS] Correctly triggered mention: '{text}' -> {reason}")

    # 3. Superchats and new chatters always trigger
    trig_sc, sc_reason = brain.should_trigger_response("generic comment", is_superchat=True)
    assert trig_sc and sc_reason == "superchat"
    print(f"  [PASS] Superchat triggered: {sc_reason}")

    trig_nc, nc_reason = brain.should_trigger_response("hello stream", is_new_chatter=True)
    assert trig_nc and nc_reason == "new_chatter_greeting"
    print(f"  [PASS] New chatter greeting triggered: {nc_reason}")


def test_sampling_layer():
    print("\n" + "=" * 60)
    print("TEST 2: High-Viewer Chat Sampling Layer (Phase 3.1)")
    print("=" * 60)

    brain = AIBrain()
    # High viewer count: 100 viewers > threshold 25
    brain.set_engagement_mode("active", is_stream_live=True, concurrent_viewers=100, is_chat_active=True)

    # 1. Questions are NEVER sampled out
    trig_q, q_reason = brain.should_trigger_response("why does the universe exist?")
    assert trig_q, "Questions must never be sampled out"
    assert q_reason == "chat_question"
    print(f"  [PASS] Question exempt from sampling: {q_reason}")

    # 2. Mentions are NEVER sampled out
    trig_m, m_reason = brain.should_trigger_response("@IAM hello there")
    assert trig_m, "Direct mentions must never be sampled out"
    print(f"  [PASS] Mention exempt from sampling: {m_reason}")

    # 3. Superchats are NEVER sampled out
    trig_s, s_reason = brain.should_trigger_response("here is support", is_superchat=True)
    assert trig_s and s_reason == "superchat"
    print(f"  [PASS] Superchat exempt from sampling: {s_reason}")

    # 4. Non-question keyword chat: sampled based on probability when viewers > 25
    with patch("random.random", return_value=0.80):  # 0.80 > 0.35 -> sampled out
        trig_out, reason_out = brain.should_trigger_response("thoughts on consciousness")
        assert not trig_out, "Keyword chat should be sampled out when random > prob"
        assert "chat_sampled_out" in reason_out
        print(f"  [PASS] Non-question chat sampled out: {reason_out}")

    with patch("random.random", return_value=0.10):  # 0.10 <= 0.35 -> passes sampling
        trig_in, reason_in = brain.should_trigger_response("thoughts on consciousness")
        assert trig_in, "Keyword chat should pass when random <= prob"
        assert "chat_interaction" in reason_in
        print(f"  [PASS] Non-question chat passed sampling: {reason_in}")


def test_prompt_depth_classifier():
    print("\n" + "=" * 60)
    print("TEST 3: Stricter Deep-vs-Fast Classifier (Phase 3.2)")
    print("=" * 60)

    brain = AIBrain()

    # Case 1: Acceptance requirement -> DEEP (>= 8 words AND contains 'dying')
    deep_prompt = "I am scared of dying and losing everyone I love, what's the point"
    is_deep, match = brain._classify_prompt_depth(deep_prompt)
    assert is_deep, f"Expected DEEP for '{deep_prompt}', got {is_deep} ({match})"
    assert match in ("dying", "death"), f"Expected match 'dying', got '{match}'"
    print(f"  [PASS] Classified DEEP: '{deep_prompt}' -> match: '{match}'")

    # Case 2: Acceptance requirement -> FAST (no trigger words, < 8 words)
    fast_prompt_1 = "god that game was trash"
    is_deep_1, reason_1 = brain._classify_prompt_depth(fast_prompt_1)
    assert not is_deep_1, f"Expected FAST for '{fast_prompt_1}', got {is_deep_1}"
    print(f"  [PASS] Classified FAST: '{fast_prompt_1}' -> reason: '{reason_1}'")

    # Case 3: Short message with deep term -> FAST (must be >= 8 words)
    short_deep = "what is meaning?"
    is_deep_short, reason_short = brain._classify_prompt_depth(short_deep)
    assert not is_deep_short, f"Expected FAST for short question '{short_deep}', got {is_deep_short}"
    print(f"  [PASS] Short deep question classified FAST: '{short_deep}' -> reason: '{reason_short}'")

    # Case 4: Long existential inquiry -> DEEP
    long_deep = "why do human beings struggle with suffering and seek enlightenment through meditation?"
    is_deep_long, match_long = brain._classify_prompt_depth(long_deep)
    assert is_deep_long, f"Expected DEEP for '{long_deep}'"
    print(f"  [PASS] Long existential inquiry classified DEEP: '{long_deep}' -> match: '{match_long}'")

    # Case 5: Multi-word terms ('who am i', 'free will')
    who_am_i_prompt = "can you tell me who am i when all my thoughts stop completely?"
    is_deep_who, match_who = brain._classify_prompt_depth(who_am_i_prompt)
    assert is_deep_who and match_who == "who am i"
    print(f"  [PASS] Multi-word term matched DEEP: '{who_am_i_prompt}' -> match: '{match_who}'")

    # Case 6: Special-mode bracketed events are always FAST
    special_events = [
        "[new_chatter_greeting] Greet @NewUser warmly",
        "[celebration] Massive milestone reached",
        "[spontaneous_reflection] Death and consciousness reflection",
    ]
    for sp in special_events:
        is_d, r = brain._classify_prompt_depth(sp)
        assert not is_d, f"Expected FAST for special mode '{sp}', got {is_d}"
        print(f"  [PASS] Special mode classified FAST: '{sp}' -> reason: '{r}'")


def test_priority_queue_heapq():
    print("\n" + "=" * 60)
    print("TEST 4: Priority Queue & FIFO Ordering with Heapq (Phase 3.3)")
    print("=" * 60)

    queue = []
    t_now = time.time()

    # 1. Enqueue 3 synthetic cast events (prio 5)
    e1 = CommentEvent(prompt_trigger="Cast 1", event_type="cast", priority=5, created_at=t_now, seq_id=1)
    e2 = CommentEvent(prompt_trigger="Cast 2", event_type="cast", priority=5, created_at=t_now + 0.01, seq_id=2)
    e3 = CommentEvent(prompt_trigger="Cast 3", event_type="cast", priority=5, created_at=t_now + 0.02, seq_id=3)

    heapq.heappush(queue, e1)
    heapq.heappush(queue, e2)
    heapq.heappush(queue, e3)

    # 2. Enqueue superchat (prio 1) after the 3 cast events
    e_sc = CommentEvent(prompt_trigger="Superchat $50", event_type="superchat", priority=1, created_at=t_now + 0.05, seq_id=4)
    heapq.heappush(queue, e_sc)

    # 3. Enqueue regular chat (prio 4)
    e_chat = CommentEvent(prompt_trigger="Regular Chat Question?", event_type="chat", priority=4, created_at=t_now + 0.06, seq_id=5)
    heapq.heappush(queue, e_chat)

    # 4. Enqueue direct mention (prio 2)
    e_mention = CommentEvent(prompt_trigger="@IAM hello", event_type="direct_mention", priority=2, created_at=t_now + 0.07, seq_id=6)
    heapq.heappush(queue, e_mention)

    # Assert dequeued order:
    # 1st: Superchat (Pri: 1, seq: 4)
    # 2nd: Direct Mention (Pri: 2, seq: 6)
    # 3rd: Chat (Pri: 4, seq: 5)
    # 4th: Cast 1 (Pri: 5, seq: 1) -> Strict FIFO
    # 5th: Cast 2 (Pri: 5, seq: 2) -> Strict FIFO
    # 6th: Cast 3 (Pri: 5, seq: 3) -> Strict FIFO

    pop1 = heapq.heappop(queue)
    assert pop1.event_type == "superchat" and pop1.priority == 1
    print(f"  [PASS] 1st Popped: {pop1.event_type} (Pri: {pop1.priority}, Seq: {pop1.seq_id})")

    pop2 = heapq.heappop(queue)
    assert pop2.event_type == "direct_mention" and pop2.priority == 2
    print(f"  [PASS] 2nd Popped: {pop2.event_type} (Pri: {pop2.priority}, Seq: {pop2.seq_id})")

    pop3 = heapq.heappop(queue)
    assert pop3.event_type == "chat" and pop3.priority == 4
    print(f"  [PASS] 3rd Popped: {pop3.event_type} (Pri: {pop3.priority}, Seq: {pop3.seq_id})")

    pop4 = heapq.heappop(queue)
    assert pop4.event_type == "cast" and pop4.seq_id == 1
    print(f"  [PASS] 4th Popped: {pop4.event_type} (Pri: {pop4.priority}, Seq: {pop4.seq_id})")

    pop5 = heapq.heappop(queue)
    assert pop5.event_type == "cast" and pop5.seq_id == 2
    print(f"  [PASS] 5th Popped: {pop5.event_type} (Pri: {pop5.priority}, Seq: {pop5.seq_id})")

    pop6 = heapq.heappop(queue)
    assert pop6.event_type == "cast" and pop6.seq_id == 3
    print(f"  [PASS] 6th Popped: {pop6.event_type} (Pri: {pop6.priority}, Seq: {pop6.seq_id})")

    assert len(queue) == 0


def run_all_tests():
    print("\n" + "#" * 65)
    print("PHASE 3 VERIFICATION: TRIGGERS, CLASSIFIER & HEAP QUEUE HYGIENE")
    print("#" * 65)

    test_trigger_hygiene()
    test_sampling_layer()
    test_prompt_depth_classifier()
    test_priority_queue_heapq()

    print("\n" + "#" * 65)
    print("ALL PHASE 3 ACCEPTANCE TESTS PASSED (100% SUCCESS)")
    print("#" * 65)


if __name__ == "__main__":
    run_all_tests()
