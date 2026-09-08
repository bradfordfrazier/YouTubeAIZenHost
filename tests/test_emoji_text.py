"""
Emoji handling. pytchat delivers emoji as :shortcode: text, so without normalization a viewer's
😂😂 reaches the chat card, the Gemini prompt, and the chatter DB as
":face_with_tears_of_joy::face_with_tears_of_joy:" — which is what appeared on stream.
"""
from pathlib import Path
import os
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent

from emoji_text import normalize_chat_text, strip_unrenderable, has_renderable_content  # noqa: E402


def test_known_shortcodes_become_emoji():
    assert normalize_chat_text(":face_with_tears_of_joy::face_with_tears_of_joy:") == "😂😂"
    assert normalize_chat_text("lmao :skull:") == "lmao 💀"
    assert normalize_chat_text("really? :thinking_face:") == "really? 🤔"


def test_unknown_shortcodes_are_dropped_not_shown_as_words():
    out = normalize_chat_text(":some_custom_channel_badge: hello")
    assert "some_custom" not in out
    assert out == "hello"
    # keep_unknown is available for debugging what a source actually sent
    assert ":some_custom_channel_badge:" in normalize_chat_text(":some_custom_channel_badge: hi", keep_unknown=True)


def test_plain_text_and_empty_are_untouched():
    assert normalize_chat_text("no emoji here") == "no emoji here"
    assert normalize_chat_text("") == ""
    assert normalize_chat_text(None) == ""
    # A bare colon-word must not be eaten
    assert normalize_chat_text("time: 4pm") == "time: 4pm"


def test_app_normalizes_at_ingestion():
    """One normalization point, before the prompt, the chat card and the chatter DB diverge."""
    src = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")
    assert "from emoji_text import normalize_chat_text" in src
    assert "msg = normalize_chat_text(item.message)" in src


def test_visualizer_filters_unrenderable_glyphs_at_the_render_chokepoint():
    src = (ROOT / "visualizer.py").read_text(encoding="utf-8", errors="ignore")
    assert "from emoji_text import strip_unrenderable" in src
    assert "strip_unrenderable(text, font)" in src, \
        "the filter must sit in _render_text so every surface gets it"


def test_strip_unrenderable_drops_missing_glyphs_only():
    pygame = pytest.importorskip("pygame")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.font.init()
    font = pygame.font.SysFont("Arial, sans-serif", 24)

    assert strip_unrenderable("plain text", font) == "plain text"
    # Whatever the font can draw is kept; whatever it cannot is removed rather than tofu-boxed.
    out = strip_unrenderable("lmao 😂", font)
    assert out.startswith("lmao")
    assert "😂" not in out or font.metrics("😂")[0] is not None
    assert strip_unrenderable("", font) == ""
    assert strip_unrenderable("abc", None) == "abc"


def test_has_renderable_content():
    assert has_renderable_content("hello")
    assert not has_renderable_content("   ")
    assert not has_renderable_content("!!! ...")
