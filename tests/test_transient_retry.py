"""
Transient upstream failures must not cost a turn.

A single Gemini 500 used to drop the reply straight to the scripted simulation fallback, so the
viewer heard canned text instead of an answer to their question. These errors almost always
succeed on a second attempt.
"""
from pathlib import Path
import asyncio
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent


class _ServerError(Exception):
    pass


_ServerError.__name__ = "ServerError"


def _brain():
    import ai_brain
    b = ai_brain.AIBrain()
    b.client = object()          # bypass the simulated-mode guard
    b.cfg.transient_retry_base_sec = 0.01
    return b


def _run(brain, trigger="Chat message from @X: 'hi'"):
    async def go():
        return [ev async for ev in brain.generate_response_stream(trigger, bypass_cache=True)]
    return asyncio.run(go())


def test_transient_errors_are_classified_correctly():
    from ai_brain import AIBrain
    for exc in (_ServerError("500 Internal Server Error"), Exception("503 Service Unavailable"),
                Exception("Deadline Exceeded"), Exception("connection reset by peer"),
                Exception("model is overloaded, try again")):
        assert AIBrain._is_transient_error(exc), exc
    # 4xx will fail identically on a retry; retrying only adds dead air.
    for exc in (Exception("400 invalid_request_error"), Exception("403 quota exceeded"),
                Exception('"thinking.type.enabled" is not supported')):
        assert not AIBrain._is_transient_error(exc), exc


def test_a_500_is_retried_and_produces_a_real_answer():
    b = _brain()
    calls = {"n": 0}

    async def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _ServerError("500 Internal Server Error")
        yield "[MOOD: snarky] A real answer from the model. "

    b._delta_stream = lambda *a, **k: flaky()
    events = _run(b)

    assert calls["n"] == 2, "the failure should have been retried"
    assert [e["mood"] for e in events if e["type"] == "mood"] == ["snarky"]
    spoken = [e["full_text"] for e in events if e["type"] == "complete"]
    assert spoken and "real answer" in spoken[0], "viewer got scripted text instead of a reply"
    assert b.consecutive_gemini_errors == 0, "a recovered turn must not advance the circuit breaker"


def test_permanent_errors_are_not_retried():
    b = _brain()
    calls = {"n": 0}

    async def hard(*a, **k):
        calls["n"] += 1
        raise Exception("400 invalid_request_error")
        yield  # pragma: no cover

    b._delta_stream = lambda *a, **k: hard()
    _run(b)
    assert calls["n"] == 1


def test_retry_does_not_duplicate_a_partial_answer():
    """If text was already emitted, a retry would speak the first half twice."""
    b = _brain()
    calls = {"n": 0}

    async def midstream(*a, **k):
        calls["n"] += 1
        yield "[MOOD: chill] The first half arrived fine. "
        raise _ServerError("500 Internal Server Error")

    b._delta_stream = lambda *a, **k: midstream()
    _run(b)
    assert calls["n"] == 1, "a mid-stream failure must not restart the turn"


def test_retry_count_is_configurable():
    from config import config
    assert hasattr(config, "transient_retry_attempts")
    assert hasattr(config, "transient_retry_base_sec")
