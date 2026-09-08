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

from emoji_text import (  # noqa: E402
    contains_emoji, font_can_draw, has_renderable_content, load_emoji_font,
    normalize_chat_text, render_mixed, split_emoji_runs, strip_unrenderable,
)


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


def test_visualizer_draws_emoji_with_a_dedicated_font():
    """
    Stripping emoji left a viewer's "😂" as a blank chat row. The visualizer must draw emoji runs
    with an emoji-capable font and only fall back to stripping when the machine has none.
    """
    src = (ROOT / "visualizer.py").read_text(encoding="utf-8", errors="ignore")
    assert "load_emoji_font" in src and "render_mixed" in src
    assert "_get_emoji_font" in src, "the emoji font must be cached per size, not reloaded per string"
    assert "strip_unrenderable(text, font)" in src, "fallback for machines without an emoji font"


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


def test_font_can_draw_detects_tofu_not_metrics():
    """
    font.metrics() reports None for characters a color emoji font renders perfectly, so it cannot
    be used to detect missing glyphs. Detection compares the rendered pixels against an unassigned
    codepoint instead.
    """
    pygame = pytest.importorskip("pygame")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.font.init()
    ui = pygame.font.SysFont("Arial, sans-serif", 24)

    assert font_can_draw(ui, "A")
    assert not font_can_draw(ui, "\U0001F602"), "a UI font should not claim to draw emoji"
    assert not font_can_draw(None, "A")

    emoji = load_emoji_font(24)
    if emoji is not None:
        assert font_can_draw(emoji, "\U0001F602")
        # ...and metrics() would have been wrong about it
        assert emoji.metrics("\U0001F602") == [None]


def test_split_emoji_runs_separates_text_from_emoji():
    assert list(split_emoji_runs("lmao 😂😂 ok")) == [
        (False, "lmao "), (True, "😂😂"), (False, " ok"),
    ]
    assert list(split_emoji_runs("plain")) == [(False, "plain")]
    assert list(split_emoji_runs("")) == []
    assert contains_emoji("hi 🔥") and not contains_emoji("hi")


def test_render_mixed_produces_one_line_height_surface():
    pygame = pytest.importorskip("pygame")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.font.init()
    ui = pygame.font.SysFont("Arial, sans-serif", 28, bold=True)
    emoji = load_emoji_font(28)
    if emoji is None:
        pytest.skip("no emoji font on this machine")

    # Plain text takes the caller's fast path
    assert render_mixed("plain text", ui, emoji, (255, 255, 255)) is None

    for text in ("😂", "lmao 😂😂", "Do cats go to heaven? 🤔"):
        surf = render_mixed(text, ui, emoji, (255, 255, 255))
        assert surf is not None, text
        assert surf.get_height() == ui.get_height(), "emoji must be scaled to the text line height"
        assert surf.get_width() > 0


def test_emoji_only_message_is_not_blank():
    """The reported bug: a message of just 😂 rendered as an empty chat row."""
    pygame = pytest.importorskip("pygame")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.font.init()
    ui = pygame.font.SysFont("Arial, sans-serif", 28)
    emoji = load_emoji_font(28)
    if emoji is None:
        pytest.skip("no emoji font on this machine")

    surf = render_mixed(normalize_chat_text(":face_with_tears_of_joy:"), ui, emoji, (255, 255, 255))
    assert surf is not None and surf.get_width() > 4, "emoji-only message rendered blank"
