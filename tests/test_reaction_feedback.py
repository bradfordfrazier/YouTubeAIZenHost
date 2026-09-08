"""
Reaction feedback loop: chat laughter credits the line that just aired, and lines the audience
laughs at are promoted to few-shot exemplars.

This is the only signal in the system grounded in the actual audience rather than in a prompt
rule, so its scoring boundaries matter: too loose and every line gets promoted, too tight and
nothing ever learns.
"""
from pathlib import Path
import logging
import re
import sys
import time
import types

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent


def _scorer(window=25.0, promote=2, tmp_path=None, monkeypatch=None):
    """
    Uses the real AIBrain rather than exec'ing a slice of its source. The slice approach broke as
    soon as the regex referenced a sibling class attribute, and it could not have caught the
    shortcode bug anyway — only the real object sees what pytchat actually delivers.
    """
    import importlib
    if monkeypatch is not None and tmp_path is not None:
        monkeypatch.setenv("FAVORITES_PATH", str(tmp_path / "scorer.jsonl"))
    import config as cfgmod
    importlib.reload(cfgmod)
    import ai_brain
    importlib.reload(ai_brain)
    b = ai_brain.AIBrain()
    b.cfg.reaction_window_sec = window
    b.cfg.reaction_promote_score = promote
    b.favorites = []
    b.saved = b.favorites
    return b


def test_laughter_is_detected_and_non_laughter_is_not(tmp_path, monkeypatch):
    s = _scorer(tmp_path=tmp_path, monkeypatch=monkeypatch)
    for msg in ("lmaooo", "LOL", "haha", "hehe", "rofl", "😂", "💀", "that killed me... crying"):
        assert s.score_reaction(msg, 3) > 0, msg
    for msg in ("that's actually deep", "hmm", "what do you mean", "", "I love this stream"):
        assert s.score_reaction(msg, 3) == 0, msg


def test_reactions_decay_and_expire(tmp_path, monkeypatch):
    s = _scorer(window=25.0, tmp_path=tmp_path, monkeypatch=monkeypatch)
    early = s.score_reaction("😂😂", 4)
    late = s.score_reaction("😂😂", 20)      # past the halfway point -> decayed
    expired = s.score_reaction("😂😂", 40)   # outside the window entirely
    assert early > late > 0
    assert expired == 0
    assert s.score_reaction("lol", -1) == 0


def test_promotion_happens_once_at_threshold(tmp_path, monkeypatch):
    s = _scorer(promote=2, tmp_path=tmp_path, monkeypatch=monkeypatch)
    s.last_played_bit = {"text": "A line that landed.", "played_at": time.time() - 3}
    s.credit_reaction("lmao")          # 1 point, below threshold
    assert not s.favorites
    s.credit_reaction("😂 dead")        # crosses it
    assert len(s.favorites) == 1
    assert s.favorites[0]["source"] == "reaction"
    s.credit_reaction("haha")          # must not save twice
    assert len(s.favorites) == 1


def test_no_bit_playing_is_a_no_op(tmp_path, monkeypatch):
    s = _scorer(tmp_path=tmp_path, monkeypatch=monkeypatch)
    s.last_played_bit = None
    assert s.credit_reaction("lmaooo") == 0


def test_app_credits_every_chat_message():
    """Scoring must run before any trigger/skip branch, or skipped messages lose their signal."""
    src = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")
    assert "self.brain.credit_reaction(msg)" in src
    idx_credit = src.index("self.brain.credit_reaction(msg)")
    idx_trigger = src.index("should_trigger_response", idx_credit - 4000 if idx_credit > 4000 else 0)
    assert idx_credit < src.index("should_trigger_response", idx_credit), \
        "credit_reaction must run before the trigger decision"


# --- Regressions found in a live session (see the "lmao / :face_with_tears_of_joy:" report) ---

def _real_brain(tmp_path, monkeypatch):
    monkeypatch.setenv("FAVORITES_PATH", str(tmp_path / "f.jsonl"))
    import importlib
    import config as cfgmod
    importlib.reload(cfgmod)
    import ai_brain
    importlib.reload(ai_brain)
    return ai_brain.AIBrain()


def test_pytchat_emoji_shortcodes_are_detected(tmp_path, monkeypatch):
    """
    pytchat delivers emoji as :shortcode: text, not codepoints. Matching only codepoints meant
    every real emoji reaction scored zero — the bug that made the feature look dead on stream.
    """
    b = _real_brain(tmp_path, monkeypatch)
    assert b.score_reaction(":face_with_tears_of_joy::face_with_tears_of_joy:", 3) == 2
    assert b.score_reaction(":skull:", 3) >= 1
    assert b.score_reaction(":thinking_face:", 3) == 0, "not every shortcode is laughter"


def test_reactions_do_not_trigger_a_reply(tmp_path, monkeypatch):
    """Answering 'lmao' with a considered reply is the wrong beat and spends a turn."""
    b = _real_brain(tmp_path, monkeypatch)
    for msg in ("lmao", "LMAOOO", "haha", ":face_with_tears_of_joy:", "😂😂", "bruh", "ok"):
        triggered, reason = b.should_trigger_response(msg)
        assert not triggered, f"{msg!r} should not trigger a reply"
        assert "reaction_only" in reason

    # ...but a reaction carrying content still gets answered
    for msg in ("lmao but really why", "Do cats go to heaven?", "haha ok so what happens when we die"):
        triggered, _ = b.should_trigger_response(msg)
        assert triggered, f"{msg!r} carries content and should be answered"

    # a superchat is always answered, even if it is only laughter
    triggered, _ = b.should_trigger_response("lmao", is_superchat=True)
    assert triggered


def test_any_completed_turn_is_creditable_not_just_bits(tmp_path, monkeypatch):
    """
    last_played_bit used to be set only for spontaneous reflections, so a laugh following a cast
    or chat answer credited nothing. Most laughs follow answers.
    """
    b = _real_brain(tmp_path, monkeypatch)
    b.record_completed_turn(trigger="Cast member @NocturnalNadia asks: ...",
                            full_text="You are the night, taking notes.",
                            mood="deadpan", author="NocturnalNadia")
    assert b.last_played_bit is not None
    assert b.last_played_bit["kind"] == "reply"
    assert b.credit_reaction("lmao") == 1

    b.record_completed_turn(trigger="[SPONTANEOUS_REFLECTION]",
                            full_text="A bit that aired.", mood="deadpan", author="")
    assert b.last_played_bit["kind"] == "bit"
