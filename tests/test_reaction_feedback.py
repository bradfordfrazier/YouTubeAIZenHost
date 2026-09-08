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


def _scorer(window=25.0, promote=2):
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    i = src.index("    _LAUGH_RE = re.compile(")
    j = src.index("    def add_favorite(self")
    body = "\n".join(l[4:] if l.startswith("    ") else l for l in src[i:j].splitlines())
    ns = {"re": re, "time": time, "logger": logging.getLogger("test")}
    exec("import re, time\nfrom typing import Optional, Dict, Any\n" + body, ns)

    stub = types.SimpleNamespace(
        cfg=types.SimpleNamespace(reaction_window_sec=window, reaction_promote_score=promote),
        _LAUGH_RE=ns["_LAUGH_RE"], last_played_bit=None, saved=[],
    )
    stub.score_reaction = types.MethodType(ns["score_reaction"], stub)
    stub.credit_reaction = types.MethodType(ns["credit_reaction"], stub)
    stub.add_favorite = lambda bit=None: (stub.saved.append(bit) or bit)
    return stub


def test_laughter_is_detected_and_non_laughter_is_not():
    s = _scorer()
    for msg in ("lmaooo", "LOL", "haha", "hehe", "rofl", "😂", "💀", "that killed me... crying"):
        assert s.score_reaction(msg, 3) > 0, msg
    for msg in ("that's actually deep", "hmm", "what do you mean", "", "I love this stream"):
        assert s.score_reaction(msg, 3) == 0, msg


def test_reactions_decay_and_expire():
    s = _scorer(window=25.0)
    early = s.score_reaction("😂😂", 4)
    late = s.score_reaction("😂😂", 20)      # past the halfway point -> decayed
    expired = s.score_reaction("😂😂", 40)   # outside the window entirely
    assert early > late > 0
    assert expired == 0
    assert s.score_reaction("lol", -1) == 0


def test_promotion_happens_once_at_threshold():
    s = _scorer(promote=2)
    s.last_played_bit = {"text": "A line that landed.", "played_at": time.time() - 3}
    s.credit_reaction("lmao")          # 1 point, below threshold
    assert not s.saved
    s.credit_reaction("😂 dead")        # crosses it
    assert len(s.saved) == 1
    assert s.saved[0]["source"] == "reaction"
    s.credit_reaction("haha")          # must not save twice
    assert len(s.saved) == 1


def test_no_bit_playing_is_a_no_op():
    s = _scorer()
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
