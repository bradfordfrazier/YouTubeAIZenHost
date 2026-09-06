"""Read-question-aloud: question vs statement detection and template rotation."""
from pathlib import Path
import random, re, sys, types

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent


def _helpers():
    """Binds the read-aloud helper methods from app.py onto a stub (no app import needed)."""
    src = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")
    start = src.index("    @staticmethod\n    def _speakable_handle")
    end = src.index("    async def _recover_from_stuck_turn")
    body = "\n".join(l[4:] if l.startswith("    ") else l for l in src[start:end].splitlines())
    ns = {"re": re, "random": random}
    exec("from typing import Optional\n" + body, ns)

    class Stub:
        _QUESTION_OPENERS = ns["_QUESTION_OPENERS"]
        _looks_like_question = classmethod(ns["_looks_like_question"].__func__
                                           if hasattr(ns["_looks_like_question"], "__func__")
                                           else ns["_looks_like_question"])
    s = Stub()
    s.cfg = types.SimpleNamespace(
        read_question_aloud="all", read_question_mood="neutral", read_question_max_words=40,
        read_question_template="{author} asks: {question}|{author} wants to know: {question}",
        read_statement_template="{author} says: {question}|{author}: {question}",
    )
    s.current_pinned_chat = None
    s._speakable_handle = staticmethod(ns["_speakable_handle"])
    for name in ("_speakable_question", "_pick_read_template", "_question_read_aloud_text"):
        setattr(s, name, types.MethodType(ns[name], s))
    return s, ns


def test_question_detection():
    _, ns = _helpers()
    QO = ns["_QUESTION_OPENERS"]

    def looks(t):
        t = (t or "").strip().lower()
        if not t:
            return False
        if "?" in t:
            return True
        w = t.split()
        return w[0] in QO or " ".join(w[:2]) in QO

    assert looks("Where are my keys?")
    assert looks("how do i stop overthinking")      # no '?' but a question word
    assert looks("Is the cloud where photos go")
    assert looks("tell me something true")          # imperative ask
    assert not looks("They aren't in my jacket pocket")
    assert not looks("I love this stream")
    assert not looks("yo dog did you hear me")      # no marker; reads as a statement
    assert not looks("")


def test_statement_uses_says_and_question_uses_asks():
    s, _ = _helpers()
    ev = types.SimpleNamespace(event_type="chat")

    s.current_pinned_chat = {"author": "MillCreekExchange", "message": "Where are my keys?"}
    # Call once: the template rotates, so a second call would pick a different variant.
    out_q = s._question_read_aloud_text(ev)
    assert ("asks" in out_q) or ("wants to know" in out_q), out_q

    s.current_pinned_chat = {"author": "MillCreekExchange", "message": "They aren't in my jacket pocket"}
    out = s._question_read_aloud_text(ev)
    assert "asks" not in out and "wants to know" not in out
    assert out.startswith("Mill Creek Exchange")


def test_template_rotation_avoids_immediate_repeat():
    s, _ = _helpers()
    ev = types.SimpleNamespace(event_type="chat")
    s.current_pinned_chat = {"author": "TestUser", "message": "Why is this happening?"}
    random.seed(3)
    outs = [s._question_read_aloud_text(ev) for _ in range(10)]
    for a, b in zip(outs, outs[1:]):
        assert a != b, "same intro template twice in a row"
    assert len(set(outs)) > 1
