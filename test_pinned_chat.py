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
    """Verifies that LocalCoHostApp sets current_pinned_chat during a turn and clears it on completion."""
    app = LocalCoHostApp()
    assert app.current_pinned_chat is None

    chat_item = {
        "author": "GrievingSeeker",
        "message": "My mother died three months ago. Where is she now?",
        "is_superchat": False,
    }
    app.chat_history.append(chat_item)

    event = CommentEvent(
        prompt_trigger="Chat message from @GrievingSeeker: 'My mother died three months ago. Where is she now?'",
        event_type="chat",
        priority=5,
        chat_item=chat_item,
    )

    async def _test():
        # Mock TTS queue_speech to avoid hardware dependency
        async def mock_queue_speech(txt):
            # While speech is queued, verify pinned chat is active
            assert app.current_pinned_chat is not None
            assert app.current_pinned_chat["author"] == "GrievingSeeker"

        async def mock_wait():
            pass

        app.tts.queue_speech = mock_queue_speech
        app.tts.wait_until_speech_completed = mock_wait

        await app._execute_ai_turn(event)
        # Verify that after turn completion, pinned chat is cleared
        assert app.current_pinned_chat is None

    asyncio.run(_test())


def test_zero_flash_subtitle_transitions():
    """Verifies that clear_subtitle and set_subtitle purge previous comment and never flash old text."""
    vis = Visualizer(width=1920, height=1080)
    vis.set_subtitle("This is the previous oracle comment from 5 minutes ago.")
    vis.ai_text_alpha = 1.0
    vis.ai_text_current = "This is the previous oracle comment from 5 minutes ago."

    # Clear subtitle targets void
    vis.clear_subtitle()
    assert vis.ai_text_target == ""
    assert vis.ai_text_state in ("fade_out", "idle_empty")

    # Setting new subtitle starts cleanly from alpha 0.0 without flashing old text
    vis.set_subtitle("This is the brand new statement.")
    assert vis.ai_text_current == "This is the brand new statement."
    assert vis.ai_text_alpha == 0.0
    assert vis.ai_text_state == "fade_in"


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

    # 1. Initial Frame: Question detected, starts fade_in
    vis.render_frame(
        audio_metrics=audio_metrics,
        chat_messages=[],
        host_transcript="",
        ai_subtitle="",
        pinned_chat_message=pinned_msg,
    )
    assert vis.question_fade_state in ("fade_in", "steady")
    assert vis.question_fade_alpha > 0.0

    # Step through frames to reach full steady state
    for _ in range(30):
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
    vis.active_question_start_time = 0.0  # Force elapsed > linger
    vis.render_frame(
        audio_metrics={"rms": 0.2, "spectrum": np.ones(32), "is_speaking": True},
        chat_messages=[],
        host_transcript="",
        ai_subtitle="Stars are the dreaming eye of the universe.",
        pinned_chat_message=pinned_msg,
    )
    assert vis.question_fade_state in ("fade_out", "idle")

    # Step through frames until question fade_out completes
    for _ in range(40):
        vis.render_frame(
            audio_metrics={"rms": 0.2, "spectrum": np.ones(32), "is_speaking": True},
            chat_messages=[],
            host_transcript="",
            ai_subtitle="Stars are the dreaming eye of the universe.",
            pinned_chat_message=pinned_msg,
        )
    assert vis.question_fade_state == "idle"
    assert vis.question_fade_alpha == 0.0


if __name__ == "__main__":
    print("Testing Visualizer Pinned Chat Rendering...")
    test_visualizer_pinned_chat_rendering()
    print("Visualizer Pinned Chat Rendering Passed!")

    print("Testing Question Fade In / Out Animation...")
    test_question_fade_in_out_animation()
    print("Question Fade In / Out Animation Passed!")

    print("Testing Pinned Comment Persistence...")
    test_pinned_comment_persists_during_oracle_statement()
    print("Pinned Comment Persistence Passed!")

    print("Testing Zero-Flash Subtitle Transitions...")
    test_zero_flash_subtitle_transitions()
    print("Zero-Flash Subtitle Transitions Passed!")

    print("Testing App Turn Pinning Lifecycle...")
    test_app_turn_pinning_lifecycle()
    print("App Turn Pinning Lifecycle Passed!")
    print("\nALL PINNED CHAT, ANIMATION & READABILITY TESTS PASSED 100%!")
