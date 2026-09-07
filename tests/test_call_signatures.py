"""
Integration guard: every keyword app.py passes to AIBrain.generate_response_stream must exist
in the brain's signature.

This exists because a stale ai_brain.py once shipped without `name_already_spoken` while app.py
was already passing it. Every turn raised TypeError, the turn guard swallowed it, and the stream
silently showed nothing but the motto for the whole session.
"""
from pathlib import Path
import ast
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent


def _brain_kwargs(method: str) -> set:
    tree = ast.parse((ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method:
            a = node.args
            names = {x.arg for x in a.args} | {x.arg for x in a.kwonlyargs}
            return names - {"self"}
    raise AssertionError(f"{method} not found in ai_brain.py")


def _kwargs_passed_in_app(attr: str) -> set:
    """Collects keyword names used at every call site of self.brain.<attr>( in app.py."""
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8", errors="ignore"))
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == attr:
            for kw in node.keywords:
                if kw.arg:
                    found.add(kw.arg)
    return found


def test_generate_response_stream_kwargs_match():
    accepted = _brain_kwargs("generate_response_stream")
    passed = _kwargs_passed_in_app("generate_response_stream")
    missing = passed - accepted
    assert not missing, (
        f"app.py passes {sorted(missing)} to generate_response_stream but ai_brain.py accepts "
        f"{sorted(accepted)} — the two files are out of sync."
    )


def test_record_completed_turn_kwargs_match():
    accepted = _brain_kwargs("record_completed_turn")
    passed = _kwargs_passed_in_app("record_completed_turn")
    missing = passed - accepted
    assert not missing, f"app.py passes {sorted(missing)} to record_completed_turn; brain accepts {sorted(accepted)}"


def test_read_aloud_override_present_when_app_uses_it():
    """If app.py can suppress the name, the brain must actually act on it."""
    app_src = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")
    brain_src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    if "name_already_spoken" in app_src:
        assert "NAME ALREADY SPOKEN" in brain_src, "brain accepts the flag but ignores it"


def test_cast_roster_is_single_sourced():
    """
    chatter_db and memory_manager must derive the cast roster from cast_engine, not hardcode it.
    A hardcoded list drifted out of sync when SynergyLinda and BetaBot_7 were retired and
    ConspiracyCarl and ChefMarco were added, mis-flagging cast members as real returning viewers.
    """
    db = (ROOT / "chatter_db.py").read_text(encoding="utf-8", errors="ignore")
    mm = (ROOT / "memory_manager.py").read_text(encoding="utf-8", errors="ignore")
    assert "from cast_engine import CastEngine" in db
    assert "_load_cast_handles" in db and "_prune_retired_cast_unlocked" in db
    assert "from cast_engine import CastEngine" in mm
    assert "refresh_cast_lore" in mm
    # Retired personas must not appear in the fallback roster (comments explaining the history are fine)
    fb = db[db.index("return {", db.index("_load_cast_handles")):]
    fb = fb[:fb.index("}") + 1].lower()
    for retired in ("synergylinda", "betabot_7", "betabot7", "synergalinda"):
        assert retired not in fb, f"{retired} still listed in the fallback cast roster"
    for current in ("conspiracycarl", "chefmarco"):
        assert current in fb, f"{current} missing from the fallback cast roster"


def test_cast_session_cap_is_enforced():
    src = (ROOT / "cast_engine.py").read_text(encoding="utf-8", errors="ignore")
    assert "cast_max_per_session" in src, "the configured cap must actually gate cast triggering"
    assert "total_cast_questions_served >= cap" in src
