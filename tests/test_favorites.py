"""Favourites store + bit generation settings (source-level and behavioural)."""
from pathlib import Path
import json, random, sys, types, time, logging
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent


def _fav_stub(tmp_path):
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    start = src.index("    def _load_favorites(self)")
    end = src.index("    # Bit forms for spontaneous material.")
    body = "\n".join(l[4:] if l.startswith("    ") else l for l in src[start:end].splitlines())
    ns = {"json": json, "random": random, "time": time, "logger": logging.getLogger("t"),
          "List": list, "Dict": dict, "Any": object, "Optional": object}
    exec("from typing import List, Dict, Any, Optional\n" + body, ns)
    stub = types.SimpleNamespace(favorites_path=tmp_path / "favs.jsonl", favorites=[], last_played_bit=None)
    for name in ("_load_favorites", "add_favorite", "sample_favorites"):
        setattr(stub, name, types.MethodType(ns[name], stub))
    return stub


def test_add_favorite_persists_and_dedupes(tmp_path):
    b = _fav_stub(tmp_path)
    assert b.add_favorite() is None  # nothing played yet
    b.last_played_bit = {"text": "I bought a clock that runs on regret.", "form": "one_liner", "theme": "Time", "mood": "deadpan"}
    assert b.add_favorite()["text"].startswith("I bought")
    b.add_favorite()  # duplicate ignored
    assert len(b.favorites) == 1
    # reload from disk
    b2 = _fav_stub(tmp_path)
    b2.favorites = b2._load_favorites()
    assert len(b2.favorites) == 1 and b2.favorites[0]["form"] == "one_liner"
    assert len(b2.sample_favorites(5)) == 1 and b2.sample_favorites(0) == []


def test_bits_use_offline_budget_and_prompt_has_craft_rules():
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    assert 'return True, "spontaneous_bit_offline"' in src
    assert "is_bit=(match_term == \"spontaneous_bit_offline\")" in src
    assert "budget = self.cfg.bit_thinking_budget" in src
    assert "CRAFT: Anchor the bit in ONE specific physical object" in src
    assert "DRAFTING: In your private reasoning, write three" in src
    assert "Your best work so far" in src
    assert "gaming analogies" not in src
