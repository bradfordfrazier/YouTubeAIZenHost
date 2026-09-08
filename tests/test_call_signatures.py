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


def test_no_use_before_assignment_in_prompt_builders():
    """
    Guards UnboundLocalError in the prompt builders. A local read before its first assignment
    raises only at runtime, and in _build_context_prompt that means every turn fails, the guard
    swallows it, and the stream goes silent with nothing but the motto.
    """
    import ast as _ast

    def first_lines(fn_node, name, ctx):
        return [
            n.lineno for n in _ast.walk(fn_node)
            if isinstance(n, _ast.Name) and n.id == name and isinstance(n.ctx, ctx)
        ]

    tree = _ast.parse((ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore"))
    checked = 0
    for node in _ast.walk(tree):
        if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith(("_build_", "generate_")):
            continue
        params = {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}

        # Comprehensions and generator expressions have their own scope, and their targets appear
        # textually after the element expression, so skip anything bound inside one.
        comp_targets = set()
        comp_nodes = [
            n for n in _ast.walk(node)
            if isinstance(n, (_ast.ListComp, _ast.SetComp, _ast.DictComp, _ast.GeneratorExp))
        ]
        for comp in comp_nodes:
            for gen in comp.generators:
                for t in _ast.walk(gen.target):
                    if isinstance(t, _ast.Name):
                        comp_targets.add(t.id)

        def _inside_comprehension(lineno):
            return any(
                c.lineno <= lineno <= (getattr(c, "end_lineno", c.lineno) or c.lineno)
                for c in comp_nodes
            )

        assigned = {
            n.id for n in _ast.walk(node)
            if isinstance(n, _ast.Name) and isinstance(n.ctx, _ast.Store)
        } - comp_targets
        for name in assigned:
            if name in params:
                continue
            stores = first_lines(node, name, _ast.Store)
            loads = [l for l in first_lines(node, name, _ast.Load) if not _inside_comprehension(l)]
            if not stores or not loads:
                continue
            # Comprehension/loop targets legitimately load after storing in the same statement.
            if min(loads) < min(stores):
                raise AssertionError(
                    f"{node.name}: '{name}' is read at line {min(loads)} but first assigned at "
                    f"line {min(stores)} — UnboundLocalError at runtime."
                )
        checked += 1
    assert checked >= 2, "expected to scan at least the prompt builder and the stream generator"


def test_degenerate_turn_still_restores_the_motto():
    """
    The post-speech section (hold, unpin, motto transition, record_completed_turn) is gated behind
    `pushed_chunks > 0 and clean_speech`. Without an else branch, a turn that produced no audio or
    no usable text skipped all of it silently and the screen kept the previous state — which is why
    the motto sometimes failed to appear between reflections.
    """
    import ast as _ast
    src = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")
    tree = _ast.parse(src)

    found = False
    for node in _ast.walk(tree):
        if not (isinstance(node, _ast.AsyncFunctionDef) and node.name == "_execute_ai_turn"):
            continue
        for sub in _ast.walk(node):
            if not isinstance(sub, _ast.If):
                continue
            seg = _ast.get_source_segment(src, sub.test) or ""
            if "pushed_chunks > 0" in seg and "clean_speech" in seg:
                found = True
                assert sub.orelse, (
                    "the speech-bookkeeping guard has no else branch; a degenerate turn will "
                    "leave the motto unset"
                )
    assert found, "could not locate the `pushed_chunks > 0 and clean_speech` guard"
    assert "[Degenerate Turn]" in src, "the skip path must log, or it stays invisible"


def test_cast_roster_has_range_and_depth():
    """
    The cast is the only chat traffic until real viewers arrive, so it needs enough questions to
    avoid cycling in a long session, and enough tonal range that consecutive questions do not all
    read as 'earnest seeker asks about the self'.
    """
    import sys
    sys.path.insert(0, str(ROOT))
    from cast_engine import CastEngine

    ce = CastEngine()
    assert len(ce.personas) >= 18, f"only {len(ce.personas)} personas"
    total = sum(len(p.questions) for p in ce.personas.values())
    assert total >= 200, f"only {total} cast questions"
    assert min(len(p.questions) for p in ce.personas.values()) >= 8

    # No question may repeat inside a long session
    seen = {}
    for _ in range(120):
        _, q = ce.next_cast_question()
        seen[q] = seen.get(q, 0) + 1
    assert not [q for q, c in seen.items() if c > 1], "cast question repeated within 120 picks"

    # Card-readable: the pinned question must fit on screen
    long_qs = [q for p in ce.personas.values() for q in p.questions if len(q.split()) > 24]
    assert not long_qs, f"questions too long for the pinned card: {long_qs[:2]}"



