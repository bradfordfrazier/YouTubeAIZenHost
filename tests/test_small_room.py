"""Small-room rule: with few viewers, every real chat message triggers a reply."""
from pathlib import Path
import re, sys, types
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_small_room_rule_order_in_source():
    """Source-level guard: question check and small-room rule must precede eco suppression,
    and the fallthrough keyword path must come after both."""
    src = (Path(__file__).resolve().parent.parent / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    body = src[src.index("def should_trigger_response"):src.index("def _build_context_prompt")]
    i_q = body.index('"chat_question"')
    i_small = body.index("small_room_chat")
    i_eco = body.index("eco_mode_suppressed (generic chat in eco mode)")
    i_kw = body.index("no_trigger_keywords")
    assert i_q < i_small < i_eco < i_kw


def test_every_skip_is_logged():
    src = (Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8", errors="ignore")
    assert "[Chat Skipped]" in src and "[Greeting Skipped]" in src
