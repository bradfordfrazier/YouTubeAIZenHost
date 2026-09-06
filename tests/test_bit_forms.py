"""Spontaneous bit generator: form rotation, one-liner ratio, and cache label/beat integrity."""
from pathlib import Path
import random, re, sys, types
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent


def _brain_stub():
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    start = src.index("    BIT_FORMS = (")
    end = src.index("    def get_next_spontaneous_theme(self)")
    body = "\n".join(l[4:] if l.startswith("    ") else l for l in src[start:end].splitlines())
    ns = {"random": random}
    exec(body, ns)
    stub = types.SimpleNamespace(cfg=types.SimpleNamespace(one_liner_ratio=0.25), BIT_FORMS=ns["BIT_FORMS"])
    stub.get_next_bit_form = types.MethodType(ns["get_next_bit_form"], stub)
    return stub


def test_form_rotation_no_immediate_repeats_and_one_liner_share():
    random.seed(7)
    b = _brain_stub()
    forms = [b.get_next_bit_form() for _ in range(400)]
    assert set(forms) <= set(b.BIT_FORMS)
    for a, c in zip(forms, forms[1:]):
        assert a != c, "same form twice in a row"
    share = forms.count("one_liner") / len(forms)
    assert 0.15 < share < 0.35, share


def test_one_liner_ratio_zero_disables():
    b = _brain_stub(); b.cfg.one_liner_ratio = 0.0
    assert "one_liner" not in {b.get_next_bit_form() for _ in range(200)}


def test_cache_reads_theme_and_form_from_brain():
    src = (ROOT / "reflection_cache.py").read_text(encoding="utf-8", errors="ignore")
    assert "brain.get_next_spontaneous_theme()" not in src, "cache must not draw its own theme"
    assert "last_spontaneous_theme" in src and "last_bit_form" in src
    assert "raw_text=raw_text" in src


def test_complete_event_carries_raw_text_and_cached_path_uses_it():
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    assert '"raw_text": raw_spoken' in src
    assert 'getattr(cached, "raw_text", None) or cached.full_text' in src


def test_prompt_has_all_forms_and_cold_open_rule():
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    for f in ("observation", "announcement", "story", "address", "one_liner"):
        assert f'"{f}": (' in src
    assert "SELF-CONTAINED" in src and "Steven Wright" in src
