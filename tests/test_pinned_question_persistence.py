import pytest
import numpy as np
from visualizer import Visualizer
from config import config


def test_question_persists_through_fade_out_for_turn():
    """Verifies that calling fade_out_for_turn() when a question is pinned does not clear _active_pinned_message."""
    vis = Visualizer(width=1920, height=1080)
    pinned_item = {
        "author": "CosmicSeeker",
        "message": "What lies beyond the event horizon?",
        "is_superchat": True,
        "amount": "$10.00",
    }

    # 1. Orchestrator sets pinned message
    vis.set_pinned(pinned_item)
    assert vis._active_pinned_message == pinned_item

    # 2. Orchestrator calls fade_out_for_turn() to clear old canvas/motto
    vis.fade_out_for_turn()
    assert vis._active_pinned_message == pinned_item, "fade_out_for_turn() must NOT erase the active pinned question!"

    # 3. Render frames while motto dissolves and question emerges
    for _ in range(120):
        vis.render_frame(
            audio_metrics={"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False},
            chat_messages=[],
            ai_subtitle="",
            pinned_chat_message=vis._active_pinned_message,
        )

    # 4. Question reaches steady state at 100% opacity
    assert vis.question_fade_state == "steady"
    assert vis.question_fade_alpha == 1.0
    assert vis.active_question_text == "What lies beyond the event horizon?"
    assert vis.active_question_is_sc is True
    assert vis.active_question_amount == "$10.00"


def test_question_remains_visible_during_ai_speech_and_set_subtitle():
    """Verifies that while AI is actively speaking (and calling set_subtitle), the question card remains 100% visible."""
    vis = Visualizer(width=1920, height=1080)
    pinned_item = {
        "author": "QuietObserver",
        "message": "Can stillness speak louder than words?",
        "is_superchat": False,
    }

    # 1. Initialize question to steady state
    vis.set_pinned(pinned_item)
    for _ in range(120):
        vis.render_frame(
            audio_metrics={"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False},
            chat_messages=[],
            ai_subtitle="",
            pinned_chat_message=vis._active_pinned_message,
        )

    assert vis.question_fade_state == "steady"
    assert vis.question_fade_alpha == 1.0

    # 2. AI begins speaking: set_subtitle is called for speech, audio is playing
    vis.set_subtitle("Stillness is the source of all true resonance.")

    for _ in range(180):  # 3 seconds of active speech at 60fps
        vis.render_frame(
            audio_metrics={"rms": 0.65, "spectrum": np.ones(32) * 0.5, "is_speaking": True},
            chat_messages=[],
            ai_subtitle="",
            pinned_chat_message=vis._active_pinned_message,
        )

        # Throughout speech playback, the active question MUST remain steady and visible!
        assert vis.question_fade_state == "steady"
        assert vis.question_fade_alpha == 1.0
        assert vis.active_question_text == "Can stillness speak louder than words?"


def test_question_dissolves_only_after_clear_pinned():
    """Verifies that the question dissolves and transitions to motto only after clear_pinned() is called."""
    vis = Visualizer(width=1920, height=1080)
    pinned_item = {
        "author": "Alice",
        "message": "How do we find peace?",
        "is_superchat": False,
    }

    vis.set_pinned(pinned_item)
    for _ in range(120):
        vis.render_frame(
            audio_metrics={"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False},
            chat_messages=[],
            ai_subtitle="",
            pinned_chat_message=vis._active_pinned_message,
        )

    assert vis.question_fade_state == "steady"
    assert vis.question_fade_alpha == 1.0

    # 1. Post-speech hold ends -> clear_pinned() is called
    vis.clear_pinned()
    vis.clear_subtitle()

    # 2. Step through frames: question fades out to idle
    for _ in range(80):
        vis.render_frame(
            audio_metrics={"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False},
            chat_messages=[],
            ai_subtitle="",
            pinned_chat_message=vis._active_pinned_message,
        )

    assert vis.question_fade_state == "idle"
    assert vis.question_fade_alpha == 0.0

    # 3. Step through frames: motto emerges
    for _ in range(120):
        vis.render_frame(
            audio_metrics={"rms": 0.0, "spectrum": np.zeros(32), "is_speaking": False},
            chat_messages=[],
            ai_subtitle="",
            pinned_chat_message=vis._active_pinned_message,
        )

    assert vis.ai_text_current == config.motto_phrase
