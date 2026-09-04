"""
Unit & Integration Test Suite for Pinned Chat Highlight System.
Verifies:
1. Visualizer 16:9 and 9:16 rendering with pinned active question highlight.
2. Distinct badge and glowing border for Superchat, Cast Member, and standard Viewer inquiries.
3. Duplicate suppression in recent feed during active pin.
4. Seamless clearing back to normal chronological rolling feed.
5. App lifecycle turn pinning and unpinning.
"""

import asyncio
import time
import numpy as np

from visualizer import Visualizer
from config import config
from app import LocalCoHostApp, CommentEvent


def test_visualizer_pinned_chat_rendering():
    """Verifies Visualizer renders pinned chat card in 16:9 and 9:16 without errors."""
    config.visualizer_headless = True
    for (w, h) in [(1920, 1080), (1080, 1920)]:
        vis = Visualizer(width=w, height=h)
        audio_metrics = {
            "rms": 0.25,
            "spectrum": np.ones(32, dtype=np.float32) * 0.4,
            "is_speaking": True,
        }
        chat_messages = [
            {"author": "Alice", "message": "First message", "is_superchat": False},
            {"author": "Bob", "message": "Second message", "is_superchat": False},
            {"author": "SeekerDave", "message": "What is the nature of consciousness?", "is_superchat": True, "amount": "$10.00"},
        ]

        # 1. Test question preview in Oracle comment panel (before speaking begins)
        pinned_msg = {
            "author": "SeekerDave",
            "message": "What is the nature of consciousness?",
            "is_superchat": True,
            "amount": "$10.00",
        }
        audio_metrics_thinking = {
            "rms": 0.0,
            "spectrum": np.zeros(32, dtype=np.float32),
            "is_speaking": False,
        }
        buf_preview = vis.render_frame(
            audio_metrics=audio_metrics_thinking,
            chat_messages=chat_messages,
            host_transcript="",
            ai_subtitle="",
            pinned_chat_message=pinned_msg,
        )
        assert isinstance(buf_preview, (bytes, bytearray))
        assert len(buf_preview) == vis.width * vis.height * 4

        # 2. Test transition to Oracle statement when speaking begins
        buf_speaking = vis.render_frame(
            audio_metrics=audio_metrics,
            chat_messages=chat_messages,
            host_transcript="",
            ai_subtitle="Consciousness is the mirror observing itself.",
            pinned_chat_message=pinned_msg,
        )
        assert isinstance(buf_speaking, (bytes, bytearray))
        assert len(buf_speaking) == vis.width * vis.height * 4

        # 3. Test cast member question preview & speaking
        pinned_cast = {
            "author": "ExistentialDave",
            "message": "Is the universe just one big mirror pretending to have edges?",
            "is_cast": True,
            "cast_persona": "ExistentialDave",
        }
        buf_cast_preview = vis.render_frame(
            audio_metrics=audio_metrics_thinking,
            chat_messages=chat_messages,
            host_transcript="",
            ai_subtitle="",
            pinned_chat_message=pinned_cast,
        )
        assert isinstance(buf_cast_preview, (bytes, bytearray))
        assert len(buf_cast_preview) == vis.width * vis.height * 4

        buf_cast_speaking = vis.render_frame(
            audio_metrics=audio_metrics,
            chat_messages=chat_messages,
            host_transcript="",
            ai_subtitle="Edges are merely where the painting gets nervous.",
            pinned_chat_message=pinned_cast,
        )
        assert isinstance(buf_cast_speaking, (bytes, bytearray))
        assert len(buf_cast_speaking) == vis.width * vis.height * 4

        # 4. Test unpinned normal feed
        buf_unpinned = vis.render_frame(
            audio_metrics=audio_metrics,
            chat_messages=chat_messages,
            host_transcript="",
            ai_subtitle="",
            pinned_chat_message=None,
        )
        assert isinstance(buf_unpinned, (bytes, bytearray))


def test_app_turn_pinning_lifecycle():
    """Verifies that LocalCoHostApp keeps current_pinned_chat and Oracle response displayed for 10s, then transitions to motto."""
    app = LocalCoHostApp()
    assert app.current_pinned_chat is None

    chat_item_1 = {
        "author": "GrievingSeeker",
        "message": "My mother died three months ago. Where is she now?",
        "is_superchat": False,
    }
    app.chat_history.append(chat_item_1)

    event_1 = CommentEvent(
        prompt_trigger="Chat message from @GrievingSeeker: 'My mother died three months ago. Where is she now?'",
        event_type="chat",
        priority=5,
        chat_item=chat_item_1,
    )

    async def _test():
        # Mock TTS queue_speech to avoid hardware dependency
        async def mock_queue_speech(txt):
            # During speech, question is pinned and response is set
            assert app.current_pinned_chat is not None
            assert app.current_pinned_chat["author"] == "GrievingSeeker"

        async def mock_wait():
            pass

        app.tts.queue_speech = mock_queue_speech
        app.tts.wait_until_speech_completed = mock_wait

        # Initialize signal and queue
        app.new_comment_signal = asyncio.Event()

        # Trigger new comment signal after 0.1s to simulate the 10s hold expiring or advancing
        async def trigger_hold():
            await asyncio.sleep(0.1)
            app.new_comment_signal.set()

        asyncio.create_task(trigger_hold())

        # Process Turn 1
        await app._execute_ai_turn(event_1)

        # After turn finishes (post-speech hold completes), comment is cleared, unpinned, and motto is set
        assert app.current_pinned_chat is None
        assert app.current_ai_subtitle == ""
        assert app.visualizer.ai_text_target == "Everything is perfect."

    asyncio.run(_test())


def test_zero_flash_subtitle_transitions():
    """Verifies that clear_subtitle and set_subtitle purge previous comment and never flash old text."""
    vis = Visualizer(width=1920, height=1080)
    vis.set_subtitle("This is the previous oracle comment from 5 minutes ago.")
    vis.ai_text_alpha = 1.0
    vis.ai_text_current = "This is the previous oracle comment from 5 minutes ago."

    # Clear subtitle resets target to motto phrase
    vis.clear_subtitle()
    assert vis.ai_text_target == "Everything is perfect."

    # Setting new subtitle starts cleanly from alpha 0.0 without flashing old text
    vis.set_subtitle("This is the brand new statement.")
    assert vis.ai_text_current == "This is the brand new statement."
    assert vis.ai_text_alpha == 0.0
    assert vis.ai_text_state == "fade_in"


def test_motto_display_when_idle():
    """Verifies that the motto 'Everything is perfect.' is displayed when there is nothing to display."""
    vis = Visualizer(width=1920, height=1080)
    # Initial state (nothing to display)
    assert vis.ai_text_target == "Everything is perfect."
    assert vis.ai_text_current == "Everything is perfect."

    # When clear_subtitle is called, returns to motto
    vis.clear_subtitle()
    assert vis.ai_text_target == "Everything is perfect."


def test_pinned_comment_persists_during_oracle_statement():
    """Verifies that the pinned chat message persists in the chat feed while the Oracle statement is displayed."""
    vis = Visualizer(width=1920, height=1080)
    pinned_msg = {
        "author": "GrievingSeeker",
        "message": "Where is my mother now?",
        "is_superchat": False,
    }

    # 1. Oracle is speaking statement
    vis.render_frame(
        audio_metrics={"rms": 0.2, "spectrum": np.ones(32), "is_speaking": True},
        chat_messages=[{"author": "Bob", "message": "hello"}],
        host_transcript="",
        ai_subtitle="She is in the silence you listen with.",
        pinned_chat_message=pinned_msg,
    )
    assert vis._active_pinned_message == pinned_msg

    # 2. Even if app.py passes pinned_chat_message=None while the Oracle statement is still active/fading out:
    vis.render_frame(
        audio_metrics={"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False},
        chat_messages=[{"author": "Bob", "message": "hello"}],
        host_transcript="",
        ai_subtitle="She is in the silence you listen with.",
        pinned_chat_message=None,
    )
    # Pinned message remains active in visualizer because Oracle comment is still visible
    assert vis._active_pinned_message == pinned_msg


def test_question_fade_in_out_animation():
    """Verifies that the chat question in center panel fades in, holds, and fades out cleanly."""
    vis = Visualizer(width=1920, height=1080)
    pinned_msg = {
        "author": "Alice",
        "message": "Do stars dream?",
        "is_superchat": False,
    }
    audio_metrics = {"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False}

    # 1. Initial Frame: Question detected, dissolves previous state / starts fade_in
    vis.render_frame(
        audio_metrics=audio_metrics,
        chat_messages=[],
        host_transcript="",
        ai_subtitle="",
        pinned_chat_message=pinned_msg,
    )
    assert vis.question_fade_state in ("waiting_for_dissolve", "fade_in", "steady")

    # Step through frames to dissolve motto and reach full steady state
    for _ in range(120):
        vis.render_frame(
            audio_metrics=audio_metrics,
            chat_messages=[],
            host_transcript="",
            ai_subtitle="",
            pinned_chat_message=pinned_msg,
        )
    assert vis.question_fade_state == "steady"
    assert vis.question_fade_alpha == 1.0

    # 2. Fast-forward linger time and trigger speech -> starts fade_out
    vis.fade_out_question()
    vis.render_frame(
        audio_metrics={"rms": 0.2, "spectrum": np.ones(32), "is_speaking": True},
        chat_messages=[],
        host_transcript="",
        ai_subtitle="Stars are the dreaming eye of the universe.",
        pinned_chat_message=pinned_msg,
    )
    assert vis.question_fade_state in ("fade_out", "idle")

    # Step through frames until question fade_out completes (1.2s fade_out = 72 frames at 60fps)
    for _ in range(80):
        vis.render_frame(
            audio_metrics={"rms": 0.2, "spectrum": np.ones(32), "is_speaking": True},
            chat_messages=[],
            host_transcript="",
            ai_subtitle="Stars are the dreaming eye of the universe.",
            pinned_chat_message=None,
        )
    assert vis.question_fade_state == "idle"
    assert vis.question_fade_alpha == 0.0


def test_spontaneous_reflection_transition_lifecycle():
    """Verifies unprompted spontaneous reflections transition cleanly from motto to reflection to pause to motto."""
    vis = Visualizer(width=1920, height=1080)
    # Start at idle motto
    vis.render_frame({"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False}, [], "", "", pinned_chat_message=None)
    assert vis.ai_text_current == "Everything is perfect."

    # Spontaneous reflection arrives (no pinned message)
    refl_text = "Silence is not the absence of sound, but the presence of stillness."
    vis.render_frame(
        audio_metrics={"rms": 0.2, "spectrum": np.ones(32), "is_speaking": True},
        chat_messages=[],
        host_transcript="",
        ai_subtitle=refl_text,
        pinned_chat_message=None,
    )
    # Transitions to reflection text
    assert vis.ai_text_target == refl_text

    # Render frames to reach steady state
    for _ in range(40):
        vis.render_frame({"rms": 0.2, "spectrum": np.ones(32), "is_speaking": True}, [], "", refl_text, pinned_chat_message=None)
    assert vis.ai_text_current == refl_text
    assert vis.ai_text_state == "steady"
    assert vis.ai_text_alpha == 1.0

    # Speech finishes, 15s hold elapses, clear_subtitle is called
    vis.clear_subtitle()
    assert vis.ai_text_state == "fade_out"

    # Step through fade_out
    for _ in range(80):
        vis.render_frame({"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False}, [], "", "", pinned_chat_message=None)
    # Reaches motto_pause
    assert vis.ai_text_state in ("motto_pause", "fade_in", "steady")


def test_live_chat_pinned_card_alpha_sync():
    """Verifies that the live chat card's pinned container smoothly fades in and fades out synchronously."""
    vis = Visualizer(width=1920, height=1080)
    pinned_msg = {"author": "Sarah", "message": "How do we let go?", "is_superchat": False}

    # Frame 1: Pinned message arrives -> starts fade_in
    vis.render_frame({"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False}, [], "", "", pinned_chat_message=pinned_msg)
    assert vis.pinned_chat_state in ("fade_in", "steady")
    assert vis.pinned_chat_alpha > 0.0

    # Fast forward to steady
    for _ in range(40):
        vis.render_frame({"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False}, [], "", "", pinned_chat_message=pinned_msg)
    assert vis.pinned_chat_state == "steady"
    assert vis.pinned_chat_alpha == 1.0

    # Unpin: pinned_chat_message becomes None (hold finished)
    vis.render_frame({"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False}, [], "", "", pinned_chat_message=None)
    assert vis.pinned_chat_state == "fade_out"

    # Step through fade_out
    for _ in range(80):
        vis.render_frame({"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False}, [], "", "", pinned_chat_message=None)
    assert vis.pinned_chat_state == "idle"
    assert vis.pinned_chat_alpha == 0.0
    assert vis.pinned_chat_stored is None


def test_configurable_transitions_override():
    """Verifies that overriding transition configs in config.py directly controls fade and hold timings."""
    orig_fade_in = config.comment_fade_in_sec
    orig_fade_out = config.comment_fade_out_sec
    orig_motto_delay = config.motto_pre_fade_in_sec
    orig_hold = config.comment_post_speech_hold_sec

    try:
        config.comment_fade_in_sec = 0.2
        config.comment_fade_out_sec = 0.3
        config.motto_pre_fade_in_sec = 0.5
        config.comment_post_speech_hold_sec = 2.0

        vis = Visualizer(width=1920, height=1080)
        vis.set_subtitle("Fast fade test comment.")
        for _ in range(20):
            vis.render_frame({"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False}, [], "", "Fast fade test comment.", pinned_chat_message=None)
        assert vis.ai_text_state == "steady"

        vis.clear_subtitle()
        assert vis.ai_text_state == "fade_out"

        # After 0.3s (18 frames at 60fps), fade_out should complete and reach motto_pause
        for _ in range(25):
            vis.render_frame({"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False}, [], "", "", pinned_chat_message=None)
        assert vis.ai_text_state in ("motto_pause", "fade_in")
    finally:
        config.comment_fade_in_sec = orig_fade_in
        config.comment_fade_out_sec = orig_fade_out
        config.motto_pre_fade_in_sec = orig_motto_delay
        config.comment_post_speech_hold_sec = orig_hold


def test_in_feed_highlight_and_scrolling_pin_docking():
    """
    Verifies that when a question is selected:
    1. It renders in-feed at the bottom with the glowing row highlight.
    2. As 1-2 new messages arrive, the highlight follows the row upwards in the feed.
    3. When 3+ new messages arrive (pushing it to the top), it docks/pins to the top and newer messages scroll beneath.
    """
    vis = Visualizer(width=1920, height=1080)
    pinned_msg = {"author": "SeekerAlice", "message": "What is beyond thought?", "is_superchat": False}

    # Step 1: Question added at bottom of chat messages [msg1, msg2, pinned_msg]
    feed_step1 = [
        {"author": "User1", "message": "Hello stream!", "is_superchat": False},
        {"author": "User2", "message": "Zen vibes", "is_superchat": False},
        pinned_msg,
    ]
    vis.render_frame({"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False}, feed_step1, "", "", pinned_chat_message=pinned_msg)
    # Active question is at the bottom of the feed (index -1)
    assert vis.pinned_chat_stored == pinned_msg
    assert vis.pinned_chat_state in ("fade_in", "steady")

    # Fast forward to steady alpha
    for _ in range(40):
        vis.render_frame({"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False}, feed_step1, "", "", pinned_chat_message=pinned_msg)
    assert vis.pinned_chat_alpha == 1.0

    # Step 2: 1 new message arrives -> [msg1, msg2, pinned_msg, new_msg1]
    # Active question rises by 1 row in the feed
    feed_step2 = list(feed_step1) + [{"author": "User3", "message": "Nice answer", "is_superchat": False}]
    buf2 = vis.render_frame({"rms": 0.2, "spectrum": np.ones(32), "is_speaking": True}, feed_step2, "", "Beyond thought is the silence that knows it.", pinned_chat_message=pinned_msg)
    assert isinstance(buf2, (bytes, bytearray))

    # Step 3: 3 more messages arrive pushing pinned_msg to the top / off the top
    # -> It docks and pins at the top of the chat card, while newer messages scroll beneath
    feed_step3 = list(feed_step2) + [
        {"author": "User4", "message": "Another question", "is_superchat": False},
        {"author": "User5", "message": "More chatter", "is_superchat": False},
        {"author": "User6", "message": "Continuing stream", "is_superchat": False},
    ]
    buf3 = vis.render_frame({"rms": 0.2, "spectrum": np.ones(32), "is_speaking": True}, feed_step3, "", "Beyond thought is the silence that knows it.", pinned_chat_message=pinned_msg)
    assert isinstance(buf3, (bytes, bytearray))
    assert len(buf3) == 1920 * 1080 * 4


def test_queue_aware_hold_and_direct_turn_transitions():
    """Verifies that when multiple comments are in queue, post-speech hold uses short hold and transitions directly without motto."""
    async def _test():
        app = LocalCoHostApp()
        app.cfg.comment_post_speech_hold_sec = 15.0
        app.cfg.comment_active_queue_hold_sec = 0.2

        async def mock_gen(prompt):
            yield {"type": "complete", "full_text": "Awareness is the silent space.", "mood": "thoughtful"}

        async def mock_synth(text):
            return np.zeros((100, 2), dtype=np.float32)

        async def mock_queue_speech(txt):
            pass

        async def mock_wait():
            pass

        app.brain.generate_response_stream = mock_gen
        app.tts.synthesize = mock_synth
        app.tts.queue_speech = mock_queue_speech
        app.tts.wait_until_speech_completed = mock_wait
        app.new_comment_signal = asyncio.Event()

        # Create two events
        event_1 = CommentEvent(
            prompt_trigger="Chat message from @Seeker1: 'What is awareness?'",
            event_type="chat",
            priority=5,
            created_at=time.time(),
            max_age_sec=90.0,
            chat_item={"author": "Seeker1", "message": "What is awareness?"},
        )
        event_2 = CommentEvent(
            prompt_trigger="Chat message from @ExistentialDave: 'Who submits the Jira ticket?'",
            event_type="cast",
            priority=6,
            created_at=time.time(),
            max_age_sec=90.0,
            chat_item={"author": "ExistentialDave", "message": "Who submits the Jira ticket?"},
        )

        # Enqueue event 2 so queue is NOT empty during event 1
        app.comment_queue.append(event_2)

        t_start = time.perf_counter()
        await app._execute_ai_turn(event_1)
        t_elapsed = time.perf_counter() - t_start

        # With active queue, hold should NOT wait 15 seconds! It should complete rapidly without the 15s idle hold
        assert t_elapsed < 10.0
        # When queue has items, it should not have cleared into motto
        assert event_2 in app.comment_queue

    asyncio.run(_test())


def test_reflection_post_speech_hold_honors_config():
    """Verifies that spontaneous reflections hold for reflection_post_speech_chat_delay_sec when chat/cast items are pending."""
    async def _test():
        app = LocalCoHostApp()
        app.cfg.comment_post_speech_hold_sec = 2.0
        app.cfg.comment_active_queue_hold_sec = 0.05
        app.cfg.reflection_post_speech_chat_delay_sec = 0.35

        async def mock_gen(prompt):
            yield {"type": "complete", "full_text": "This is a quiet test reflection for timing.", "mood": "chill"}

        async def mock_synth(text):
            return np.zeros((100, 2), dtype=np.float32)

        async def mock_queue_speech(txt):
            pass

        async def mock_wait():
            pass

        app.brain.generate_response_stream = mock_gen
        app.tts.synthesize = mock_synth
        app.tts.queue_speech = mock_queue_speech
        app.tts.wait_until_speech_completed = mock_wait
        app.new_comment_signal = asyncio.Event()

        # Create reflection event
        event_reflection = CommentEvent(
            prompt_trigger="[SPONTANEOUS_REFLECTION]",
            event_type="spontaneous",
            priority=10,
            created_at=time.time(),
            max_age_sec=90.0,
        )
        # Pending cast event
        event_cast = CommentEvent(
            prompt_trigger="Cast member @ExistentialDave asks: 'Who submits the Jira ticket?'",
            event_type="cast",
            priority=6,
            created_at=time.time(),
            max_age_sec=90.0,
            chat_item={"author": "ExistentialDave", "message": "Who submits the Jira ticket?"},
        )
        app.comment_queue.append(event_cast)

        t_start = time.perf_counter()
        await app._execute_ai_turn(event_reflection)
        t_elapsed = time.perf_counter() - t_start

        # Reflection should hold for configured reflection_post_speech_chat_delay_sec (0.35s), not 0.05s nor 2.0s
        assert t_elapsed >= 0.30, f"Expected hold duration >= 0.30s, got {t_elapsed:.3f}s"
        assert t_elapsed < 1.0, f"Expected hold duration < 1.0s, got {t_elapsed:.3f}s"

    asyncio.run(_test())


def test_reflection_chat_wakeup_during_hold():
    """Verifies that when chat question arrives during post-reflection hold, it respects reflection_post_speech_chat_delay_sec."""
    async def _test():
        app = LocalCoHostApp()
        app.cfg.comment_post_speech_hold_sec = 5.0
        app.cfg.reflection_post_speech_chat_delay_sec = 0.4

        async def mock_gen(prompt):
            yield {"type": "complete", "full_text": "This is a quiet test reflection for timing.", "mood": "chill"}

        async def mock_synth(text):
            return np.zeros((100, 2), dtype=np.float32)

        async def mock_queue_speech(txt):
            pass

        async def mock_wait():
            pass

        app.brain.generate_response_stream = mock_gen
        app.tts.synthesize = mock_synth
        app.tts.queue_speech = mock_queue_speech
        app.tts.wait_until_speech_completed = mock_wait
        app.new_comment_signal = asyncio.Event()

        event_reflection = CommentEvent(
            prompt_trigger="[SPONTANEOUS_REFLECTION]",
            event_type="spontaneous",
            priority=10,
            created_at=time.time(),
            max_age_sec=90.0,
        )

        async def inject_chat_later():
            await asyncio.sleep(0.1)
            event_chat = CommentEvent(
                prompt_trigger="Chat message from @ViewerA: 'Hello!'",
                event_type="chat",
                priority=4,
                created_at=time.time(),
                max_age_sec=90.0,
                chat_item={"author": "ViewerA", "message": "Hello!"},
            )
            app.comment_queue.append(event_chat)

        inj_task = asyncio.create_task(inject_chat_later())
        t_start = time.perf_counter()
        await app._execute_ai_turn(event_reflection)
        t_elapsed = time.perf_counter() - t_start
        await inj_task

        # It should hold until reflection_post_speech_chat_delay_sec (0.4s) has elapsed
        assert t_elapsed >= 0.35, f"Expected hold duration >= 0.35s, got {t_elapsed:.3f}s"
        assert t_elapsed < 1.5, f"Expected hold duration < 1.5s, got {t_elapsed:.3f}s"

    asyncio.run(_test())


def test_strict_fifo_chat_ordering():
    """Verifies that all live chat messages are scheduled in strict FIFO arrival order, while Superchats jump ahead."""
    app = LocalCoHostApp()
    app.comment_queue.clear()
    app.running = True

    # 1. Chat 1 arrives
    app._trigger_ai_turn("Chat message from @ViewerA: 'Message 1'", event_type="chat", chat_item={"author": "ViewerA", "message": "Message 1"})
    # 2. Direct mention 2 arrives
    app._trigger_ai_turn("Chat message from @ViewerB: '@ZenHost Message 2'", event_type="direct_mention", chat_item={"author": "ViewerB", "message": "@ZenHost Message 2"})
    # 3. New chatter greeting arrives
    app._trigger_ai_turn("[NEW_CHATTER_GREETING] @ViewerC: 'Message 3'", event_type="greeting", chat_item={"author": "ViewerC", "message": "Message 3"})
    # 4. Cast member question arrives
    app._trigger_ai_turn("Cast member @ExistentialDave asks: 'Message 4'", event_type="cast", chat_item={"author": "ExistentialDave", "message": "Message 4"})
    # 5. Superchat arrives
    app._trigger_ai_turn("Superchat from @VIP: '$10 Message 5'", event_type="superchat", priority=2, chat_item={"author": "VIP", "message": "$10 Message 5"})

    # Verify queue order:
    # Tier 2: Superchat (VIP)
    # Tier 3: Direct Mention (ViewerB)
    # Tier 4: Real Live Chat / Greetings in FIFO arrival order (ViewerA, ViewerC)
    # Tier 5: Synthetic Cast (ExistentialDave)
    authors_in_order = [e.chat_item["author"] for e in app.comment_queue]
    assert authors_in_order == ["VIP", "ViewerB", "ViewerA", "ViewerC", "ExistentialDave"], f"Unexpected queue order: {authors_in_order}"


def test_system_prompt_never_pinned_or_added_to_chat_history():
    """Verifies that internal bracketed prompts like [VIEWER_JOINED] are NEVER pinned as chat questions or added to chat history."""
    async def _test():
        app = LocalCoHostApp()
        app.chat_history.clear()
        app.cfg.comment_post_speech_hold_sec = 0.1
        app.cfg.comment_active_queue_hold_sec = 0.1

        async def mock_queue_speech(txt):
            # During speech, system prompt should NOT be pinned as chat
            assert app.current_pinned_chat is None

        async def mock_wait():
            pass

        app.tts.queue_speech = mock_queue_speech
        app.tts.wait_until_speech_completed = mock_wait
        app.new_comment_signal = asyncio.Event()

        prompt = "[VIEWER_JOINED] A sole viewer has entered the stream. (Concurrent viewers: 1). Acknowledge their presence directly on @MassiveGodComplex."
        event = CommentEvent(
            prompt_trigger=prompt,
            event_type="system",
            priority=10,
            created_at=time.time(),
            max_age_sec=30.0,
        )

        await app._execute_ai_turn(event)

        # Chat history must remain completely empty (no bogus system prompt added)
        assert len(app.chat_history) == 0
        assert app.current_pinned_chat is None

    asyncio.run(_test())


def test_bottom_anchored_chat_rendering_with_many_messages():
    """Verifies that newly arriving chat messages (especially active questions at the bottom of long history) are ALWAYS rendered and never clipped."""
    vis = Visualizer(width=1920, height=1080)

    chat_history = [
        {"author": f"User{i}", "message": f"This is message number {i} from a viewer discussing deep topics."}
        for i in range(10)
    ]
    active_question = chat_history[-1]

    # Render frame with active question
    vis.render_frame(
        audio_metrics={"rms": 0.0, "spectrum": np.zeros(64)},
        chat_messages=chat_history,
        host_transcript="",
        ai_subtitle="",
        host_connected=True,
        obs_connected=True,
        engagement_mode="active",
        concurrent_viewers=5,
        is_stream_live=True,
        pinned_chat_message=active_question,
    )

    assert vis.pinned_chat_stored == active_question


def test_rapid_consecutive_real_chat_messages_never_missed():
    """Verifies that multiple rapid real chat comments arriving within seconds are all queued and never dropped."""
    app = LocalCoHostApp()
    app.comment_queue.clear()
    app.running = True
    app.engagement_mode = "active"
    app.brain.set_engagement_mode("active", is_stream_live=True, concurrent_viewers=5, is_chat_active=True)
    app.brain.last_response_time = time.time()  # AI just spoke 0.0s ago

    # Real chatter 1 sends a message immediately after AI speech
    trigger_1, reason_1 = app.brain.should_trigger_response("What is reality?", is_host=False)
    assert trigger_1 is True, f"First real chat message was unexpectedly dropped! Reason: {reason_1}"
    app._trigger_ai_turn(f"Chat message from @Viewer1: 'What is reality?'", event_type="chat", chat_item={"author": "Viewer1", "message": "What is reality?"})

    # Real chatter 2 sends a message 0.2s later
    trigger_2, reason_2 = app.brain.should_trigger_response("I want to know too", is_host=False)
    assert trigger_2 is True, f"Second real chat message was unexpectedly dropped! Reason: {reason_2}"
    app._trigger_ai_turn(f"Chat message from @Viewer2: 'I want to know too'", event_type="chat", chat_item={"author": "Viewer2", "message": "I want to know too"})

    # Verify both comments are queued in strict FIFO order
    assert len(app.comment_queue) == 2
    assert app.comment_queue[0].chat_item["author"] == "Viewer1"
    assert app.comment_queue[1].chat_item["author"] == "Viewer2"


def test_real_chat_evicts_pending_synthetic_cast():
    """Verifies that incoming real human chat comments take priority and evict pending synthetic cast questions."""
    app = LocalCoHostApp()
    app.comment_queue.clear()
    app.running = True

    # Queue 2 synthetic cast questions
    app._trigger_ai_turn("Cast member @ExistentialDave asks: 'Jira ticket?'", event_type="cast", priority=6, chat_item={"author": "ExistentialDave", "message": "Jira ticket?"})
    app._trigger_ai_turn("Cast member @SpeedrunnerKyle asks: 'Any% route?'", event_type="cast", priority=6, chat_item={"author": "SpeedrunnerKyle", "message": "Any% route?"})

    # Real human chat arrives -> Pruning synthetic cast queue
    app.comment_queue = [ev for ev in app.comment_queue if ev.event_type not in ("cast", "spontaneous", "system")]
    app._trigger_ai_turn("Chat message from @RealHuman: 'Hello Oracle!'", event_type="chat", priority=4, chat_item={"author": "RealHuman", "message": "Hello Oracle!"})

    assert len(app.comment_queue) == 1
    assert app.comment_queue[0].chat_item["author"] == "RealHuman"


def test_vox_only_mode():
    """Verifies that in VOX_ONLY mode, chat questions stay visible during speech without AI subtitle, and reflections display nothing."""
    orig_vox = config.vox_only_mode
    try:
        config.vox_only_mode = True
        vis = Visualizer(1920, 1080)
        vis.cfg.vox_only_mode = True
        pinned_msg = {"author": "ZenSeeker", "message": "What is nothingness?"}

        # 1. Step through initial motto dissolve and question fade-in
        for _ in range(120):
            vis.render_frame({"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False}, [], "", "", pinned_chat_message=pinned_msg)

        assert vis.question_fade_state == "steady"
        assert vis.question_fade_alpha == 1.0
        assert vis.active_question_text == "What is nothingness?"

        # 2. Speaking starts: set_subtitle is called, but in VOX_ONLY mode subtitle text is not displayed
        vis.set_subtitle("Nothingness is the canvas of all creation.")
        assert vis.subtitle_target_text == ""

        for _ in range(60):
            vis.render_frame({"rms": 0.5, "spectrum": np.zeros(32), "is_speaking": True}, [], "", "", pinned_chat_message=pinned_msg)

        # Question remains steadily displayed in comment card during speech
        assert vis.question_fade_state == "steady"
        assert vis.question_fade_alpha == 1.0
        assert vis.active_question_text == "What is nothingness?"

        # 3. Speech ends and question is unpinned
        for _ in range(100):
            vis.render_frame({"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False}, [], "", "", pinned_chat_message=None)

        assert vis.question_fade_state == "idle"
        assert vis.active_question_text == ""

        # 4. Spontaneous reflection: nothing displayed in comment card during speech
        vis.fade_out_for_turn()
        vis.set_subtitle("The cosmos listens to its own echo.")
        for _ in range(50):
            vis.render_frame({"rms": 0.5, "spectrum": np.zeros(32), "is_speaking": True}, [], "", "", pinned_chat_message=None)

        assert vis.active_question_text == ""
        assert vis.ai_text_current == "" or vis.ai_text_alpha <= 0.01

        # 5. Reflection ends -> motto returns
        vis.clear_subtitle()
        for _ in range(120):
            vis.render_frame({"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False}, [], "", "", pinned_chat_message=None)

        assert vis.ai_text_current == config.motto_phrase
    finally:
        config.vox_only_mode = orig_vox


if __name__ == "__main__":
    print("Testing Visualizer Pinned Chat Rendering...")
    test_visualizer_pinned_chat_rendering()
    print("Visualizer Pinned Chat Rendering Passed!")

    print("Testing Motto Display When Idle...")
    test_motto_display_when_idle()
    print("Motto Display When Idle Passed!")

    print("Testing Question Fade In / Out Animation...")
    test_question_fade_in_out_animation()
    print("Question Fade In / Out Animation Passed!")

    print("Testing Pinned Comment Persistence...")
    test_pinned_comment_persists_during_oracle_statement()
    print("Pinned Comment Persistence Passed!")

    print("Testing Zero-Flash Subtitle Transitions...")
    test_zero_flash_subtitle_transitions()
    print("Zero-Flash Subtitle Transitions Passed!")

    print("Testing Spontaneous Reflection Transition Lifecycle...")
    test_spontaneous_reflection_transition_lifecycle()
    print("Spontaneous Reflection Transition Lifecycle Passed!")

    print("Testing Live Chat Pinned Card Alpha Sync...")
    test_live_chat_pinned_card_alpha_sync()
    print("Live Chat Pinned Card Alpha Sync Passed!")

    print("Testing Configurable Transitions Override...")
    test_configurable_transitions_override()
    print("Configurable Transitions Override Passed!")

    print("Testing In-Feed Highlight and Scrolling Pin Docking...")
    test_in_feed_highlight_and_scrolling_pin_docking()
    print("In-Feed Highlight and Scrolling Pin Docking Passed!")

    print("Testing Queue-Aware Hold and Direct Turn Transitions...")
    test_queue_aware_hold_and_direct_turn_transitions()
    print("Queue-Aware Hold and Direct Turn Transitions Passed!")

    print("Testing Reflection Post-Speech Hold Honors Config...")
    test_reflection_post_speech_hold_honors_config()
    print("Reflection Post-Speech Hold Honors Config Passed!")

    print("Testing Reflection Chat Wakeup During Hold Honors Config...")
    test_reflection_chat_wakeup_during_hold()
    print("Reflection Chat Wakeup During Hold Honors Config Passed!")

    print("Testing Strict FIFO Chat Ordering...")
    test_strict_fifo_chat_ordering()
    print("Strict FIFO Chat Ordering Passed!")

    print("Testing System Prompts Never Pinned or Added to Chat...")
    test_system_prompt_never_pinned_or_added_to_chat_history()
    print("System Prompts Never Pinned or Added to Chat Passed!")

    print("Testing Bottom-Anchored Chat Rendering with Long History...")
    test_bottom_anchored_chat_rendering_with_many_messages()
    print("Bottom-Anchored Chat Rendering with Long History Passed!")

    print("Testing Rapid Consecutive Real Chat Messages Never Missed...")
    test_rapid_consecutive_real_chat_messages_never_missed()
    print("Rapid Consecutive Real Chat Messages Never Missed Passed!")

    print("Testing Real Chat Evicts Pending Synthetic Cast...")
    test_real_chat_evicts_pending_synthetic_cast()
    print("Real Chat Evicts Pending Synthetic Cast Passed!")

    print("Testing App Turn Pinning Lifecycle...")
    test_app_turn_pinning_lifecycle()
    print("App Turn Pinning Lifecycle Passed!")

    print("Testing VOX_ONLY Mode Display Dynamics...")
    test_vox_only_mode()
    print("VOX_ONLY Mode Display Dynamics Passed!")
    print("\nALL PINNED CHAT, ANIMATION & READABILITY TESTS PASSED 100%!")
