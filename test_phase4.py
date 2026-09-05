"""
Test Suite for Phase 4: Synthetic Cast Transparency.
Verifies:
1. Config: cast_badge_label configuration.
2. ChatterDB: Cast profiles, context snippets, and exclusion from returning viewer statistics.
3. AI Brain: Cast chat formatting and fictional character fourth-wall prompt guidance.
4. Visualizer: Rendering of [CAST] badges in 16:9 landscape and 9:16 vertical modes.
"""

import os
import shutil
import tempfile
import time
from pathlib import Path
import pygame

from config import config
from chatter_db import ChatterDB, ChatterProfile
from ai_brain import AIBrain
from visualizer import Visualizer


def test_config_cast_badge():
    """Verify cast_badge_label in config."""
    assert hasattr(config, "cast_badge_label")
    assert config.cast_badge_label == "CAST"


def test_chatter_db_cast_transparency():
    """Verify ChatterDB cast context formatting and exclusion from returning viewers."""
    test_dir = Path(tempfile.mkdtemp())
    try:
        db_path = str(test_dir / "chatter_db_test.json")
        db = ChatterDB(db_path=db_path)

        # 1. Cast profile should have [CAST CONTEXT: ...] snippet
        cast_profile = db.get_profile("ExistentialDave")
        assert cast_profile is not None
        assert cast_profile.is_cast is True
        snippet = cast_profile.generate_context_snippet()
        assert "[CAST CONTEXT:" in snippet
        assert "Synthetic Cast Member (Recurring Fictional Cast Character)" in snippet
        assert "Visit #" not in snippet

        # 2. Record activity for cast member across sessions: visit_count should NOT increase
        db.record_activity("ExistentialDave", "ExistentialDave", "Is free will a bug?", is_cast=True, session_id="sess_1")
        db.record_activity("ExistentialDave", "ExistentialDave", "Jira ticket updated", is_cast=True, session_id="sess_2")
        p = db.get_profile("ExistentialDave")
        assert p.visit_count == 1
        assert p.is_cast is True

        # 3. Real chatter should have normal [CHATTER CONTEXT: ...] snippet and increment visit_count
        db.record_activity("AliceRealViewer", "Alice", "Hello I AM!", is_cast=False, session_id="sess_1")
        db.record_activity("AliceRealViewer", "Alice", "Back again!", is_cast=False, session_id="sess_2")
        alice = db.get_profile("AliceRealViewer")
        assert alice.is_cast is False
        assert alice.visit_count == 2
        alice_snippet = alice.generate_context_snippet()
        assert "[CHATTER CONTEXT:" in alice_snippet
        assert "Visit #2" in alice_snippet

        # 4. get_returning_viewers must strictly exclude cast
        returning = db.get_returning_viewers()
        returning_handles = [r.handle for r in returning]
        assert "AliceRealViewer" in returning_handles
        assert "ExistentialDave" not in returning_handles
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_ai_brain_cast_context_and_prompts():
    """Verify AI Brain cast formatting in chat buffer and prompt guidance."""
    brain = AIBrain()

    # Add cast message and real viewer message
    brain.add_chat_message("ExistentialDave", "Can you speedrun enlightenment?", is_cast=True, cast_persona="existential_it")
    brain.add_chat_message("BobRealUser", "What is the meaning of life?", is_cast=False)

    # Build context prompt
    prompt = brain._build_context_prompt()
    assert "Cast @ExistentialDave [CAST]: Can you speedrun enlightenment?" in prompt
    assert "Viewer @BobRealUser: What is the meaning of life?" in prompt

    # Prompt guidance for cast question
    cast_turn_prompt = brain._build_context_prompt(override_prompt="Cast member @ExistentialDave (Overthinking IT Specialist) asks: 'Is death a kernel panic?'")
    assert "Special Mode: SYNTHETIC CAST INTERACTION" in cast_turn_prompt
    assert "FICTIONAL CHARACTER FOURTH-WALL GUIDANCE" in cast_turn_prompt
    assert "@ExistentialDave" in cast_turn_prompt


def test_visualizer_cast_badge_rendering():
    """Verify visualizer renders cast badges on 16:9 and 9:16 layouts without errors."""
    output_dir = Path("artifacts")
    output_dir.mkdir(parents=True, exist_ok=True)

    chat_messages = [
        {"author": "ExistentialDave", "message": "Does the universe have garbage collection?", "is_cast": True, "author_type": "cast", "is_superchat": False},
        {"author": "RealViewer123", "message": "How do I find peace?", "is_cast": False, "author_type": "viewer", "is_superchat": False},
        {"author": "AstralBrenda", "message": "Can you read my aura?", "is_cast": True, "author_type": "cast", "is_superchat": False},
        {"author": "CryptoFan", "message": "To the moon!", "is_superchat": True, "amount": "$10.00", "is_cast": False},
    ]

    pinned_cast = {
        "author": "ExistentialDave",
        "message": "Does the universe have garbage collection, or do abandoned egos leak forever?",
        "is_cast": True,
        "author_type": "cast",
        "is_superchat": False,
    }

    pinned_real = {
        "author": "RealViewer123",
        "message": "How do I find peace in a chaotic world?",
        "is_cast": False,
        "author_type": "viewer",
        "is_superchat": False,
    }

    # Test 16:9 Landscape Mode
    os.environ["VISUALIZER_ASPECT_RATIO"] = "16:9"
    os.environ["VISUALIZER_HEADLESS"] = "true"
    viz_16_9 = Visualizer()
    viz_16_9.set_mood("transcendent")

    audio_metrics = {"rms": 0.04, "spectrum": [0.02]*32, "is_speaking": False}

    # Render frame with pinned cast question
    frame_16_9 = viz_16_9.render_frame(
        audio_metrics=audio_metrics,
        chat_messages=chat_messages,
        ai_subtitle="",
        pinned_chat_message=pinned_cast,
    )
    assert frame_16_9 is not None
    assert len(frame_16_9) == 1920 * 1080 * 4

    # Save test screenshot
    surf_16_9 = viz_16_9.screen.copy()
    pygame.image.save(surf_16_9, str(output_dir / "test_phase4_16_9_cast.png"))

    # Test 9:16 Vertical Mode
    os.environ["VISUALIZER_ASPECT_RATIO"] = "9:16"
    viz_9_16 = Visualizer()
    viz_9_16.set_mood("snarky")

    frame_9_16 = viz_9_16.render_frame(
        audio_metrics=audio_metrics,
        chat_messages=chat_messages,
        ai_subtitle="",
        pinned_chat_message=pinned_cast,
    )
    assert frame_9_16 is not None
    assert len(frame_9_16) == 1080 * 1920 * 4

    surf_9_16 = viz_9_16.screen.copy()
    pygame.image.save(surf_9_16, str(output_dir / "test_phase4_9_16_cast.png"))

    # Render frame with real viewer pinned question
    frame_real = viz_16_9.render_frame(
        audio_metrics=audio_metrics,
        chat_messages=chat_messages,
        ai_subtitle="",
        pinned_chat_message=pinned_real,
    )
    assert frame_real is not None
    pygame.image.save(viz_16_9.screen.copy(), str(output_dir / "test_phase4_16_9_real.png"))

    print("Successfully rendered 16:9 and 9:16 test frames with [CAST] badges!")


if __name__ == "__main__":
    test_config_cast_badge()
    test_chatter_db_cast_transparency()
    test_ai_brain_cast_context_and_prompts()
    test_visualizer_cast_badge_rendering()
    print("All Phase 4 tests passed successfully!")
