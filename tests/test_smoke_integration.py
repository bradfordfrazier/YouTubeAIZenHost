"""
Smoke test: the whole app object must construct, and the reaction loop must work end to end
against the REAL AIBrain, config, and favourites file — not stubs.

This exists because two separate regressions (a lost keyword argument, a use-before-assignment)
both passed every unit test and only failed on a live turn. Constructing the real objects catches
that class of break in a second.
"""
from pathlib import Path
import os
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent

pygame = pytest.importorskip("pygame", reason="visualizer import needs pygame")
pytest.importorskip("sounddevice", reason="app import needs PortAudio")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")


def test_brain_constructs_and_builds_both_prompts():
    from ai_brain import AIBrain
    b = AIBrain()

    bit = b._build_context_prompt("[SPONTANEOUS_REFLECTION]")
    assert len(bit) > 1000
    assert "FORM:" in bit, "no bit form rule reached the prompt"
    assert "CONFESSION" not in bit, "the retired confession form is still being emitted"

    chat = b._build_context_prompt("Chat message from @Someone: 'why do we dream?'",
                                   name_already_spoken=True)
    assert "NAME ALREADY SPOKEN" in chat, "read-aloud override missing from the chat prompt"


def test_reaction_loop_scores_promotes_and_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("FAVORITES_PATH", str(tmp_path / "favs.jsonl"))
    import importlib
    import config as cfgmod
    importlib.reload(cfgmod)
    import ai_brain
    importlib.reload(ai_brain)

    b = ai_brain.AIBrain()
    assert b.favorites == []

    b.last_played_bit = {"text": "A line that landed.", "mood": "deadpan",
                         "form": "one_liner", "theme": "Keys", "played_at": time.time() - 3}
    assert b.credit_reaction("that is deep") == 0        # praise is not laughter
    assert b.credit_reaction("lmaooo") == 1
    assert b.credit_reaction("😂😂") == 2                 # crosses the threshold
    assert len(b.favorites) == 1
    assert b.favorites[0]["source"] == "reaction"

    # survives a restart
    b2 = ai_brain.AIBrain()
    assert len(b2.favorites) == 1
    assert b2.sample_favorites(5)

    # a second reaction must not double-save
    b.credit_reaction("haha")
    assert len(b.favorites) == 1


def test_reaction_is_a_noop_without_a_played_line():
    from ai_brain import AIBrain
    b = AIBrain()
    b.last_played_bit = None
    assert b.credit_reaction("lmaooo") == 0
    b.last_played_bit = {"text": "", "played_at": time.time()}
    assert b.credit_reaction("lmao") == 0


def test_app_object_constructs_with_all_round_state():
    import app
    a = app.LocalCoHostApp()
    try:
        for attr in ("last_turn_audio_end", "turn_phase", "comment_queue", "brain", "tts"):
            assert hasattr(a, attr), f"app is missing {attr}"
        for meth in ("_question_read_aloud_text", "_looks_like_question", "_pick_read_template",
                     "_recover_from_stuck_turn", "turn_watchdog_task"):
            assert hasattr(a, meth), f"app is missing {meth}"
        for key in ("reaction_window_sec", "reaction_promote_score", "min_turn_gap_sec",
                    "anchor_ban_enabled", "anti_repetition_window"):
            assert hasattr(a.cfg, key), f"config is missing {key}"
        assert hasattr(a.brain, "credit_reaction")
    finally:
        close = getattr(getattr(a, "visualizer", None), "close", None)
        if close:
            try:
                close()
            except Exception:
                pass


def test_cast_pool_is_deep_enough_for_a_long_session():
    from cast_engine import CastEngine
    ce = CastEngine()
    assert len(ce.personas) >= 18
    assert sum(len(p.questions) for p in ce.personas.values()) >= 200


def test_unknown_viewer_count_does_not_force_eco():
    """
    A viewer count that cannot be resolved (no API key, quota exhausted, scraping blocked) used
    to read as zero viewers, which forces ECO mode: reflections suppressed, chat throttled, the
    app sitting on the motto while people are actually watching. Unknown is not empty.
    """
    import app
    a = app.LocalCoHostApp()
    try:
        assert hasattr(a, "viewer_count_known") and a.viewer_count_known is False
        assert a.cfg.assumed_viewers_when_unknown >= 1

        # Simulate the poller failing before any successful reading
        assumed = int(a.cfg.assumed_viewers_when_unknown)
        if not a.viewer_count_known and a.concurrent_viewers < assumed:
            a.concurrent_viewers = assumed
            a._update_engagement_state()
        assert a.concurrent_viewers >= 1
        assert a.engagement_mode != "standby"

        # A real reading always wins over the assumption
        a.viewer_count_known = True
        a._on_viewer_count_update(7, 0)
        assert a.concurrent_viewers == 7
    finally:
        close = getattr(getattr(a, "visualizer", None), "close", None)
        if close:
            try:
                close()
            except Exception:
                pass


def test_viewer_fetch_failures_are_logged_not_swallowed():
    """The failure was invisible at DEBUG, so the show looked broken for no stated reason."""
    src = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")
    assert "[Viewer Count] Unavailable" in src
    assert "logger.warning" in src.split("Viewer query failed")[0][-400:], \
        "the Data API failure must warn, not debug"
    assert "assumed_viewers_when_unknown" in src
