"""
Emoji handling for chat text.

pytchat delivers emoji as :shortcode: text — a viewer sending 😂😂 arrives as
":face_with_tears_of_joy::face_with_tears_of_joy:". Left alone, that shortcode reaches three
places it should not: the on-screen chat card (where it reads as an odd descriptive label), the
Gemini prompt (where the model tries to interpret the words), and the chatter database.

`normalize_chat_text()` runs once at ingestion so all three receive the same clean text.
`strip_unrenderable()` runs at draw time, because a pygame font that lacks a glyph draws a tofu
box, which looks worse than nothing.
"""

from __future__ import annotations

import re
from typing import Optional

# Shortcodes worth turning back into real emoji. Deliberately a curated list rather than a full
# emoji database: YouTube's shortcode vocabulary is large, mostly rare, and an unknown code is
# better dropped than rendered as words.
SHORTCODE_TO_EMOJI = {
    "face_with_tears_of_joy": "😂",
    "joy": "😂",
    "rolling_on_the_floor_laughing": "🤣",
    "rofl": "🤣",
    "grinning_squinting_face": "😆",
    "grinning_face_with_sweat": "😅",
    "smiling_face_with_smiling_eyes": "😊",
    "smiling_face_with_heart_eyes": "😍",
    "slightly_smiling_face": "🙂",
    "winking_face": "😉",
    "loudly_crying_face": "😭",
    "sob": "😭",
    "crying_face": "😢",
    "skull": "💀",
    "skull_and_crossbones": "☠️",
    "fire": "🔥",
    "clapping_hands": "👏",
    "thumbs_up": "👍",
    "thumbs_down": "👎",
    "folded_hands": "🙏",
    "red_heart": "❤️",
    "sparkling_heart": "💖",
    "thinking_face": "🤔",
    "face_with_raised_eyebrow": "🤨",
    "exploding_head": "🤯",
    "eyes": "👀",
    "hundred_points": "💯",
    "party_popper": "🎉",
    "raising_hands": "🙌",
    "flexed_biceps": "💪",
    "brain": "🧠",
    "alien": "👽",
    "robot": "🤖",
    "ghost": "👻",
    "star": "⭐",
    "sparkles": "✨",
    "sun": "☀️",
    "crescent_moon": "🌙",
    "cat": "🐱",
    "dog": "🐶",
    "smiling_face_with_sunglasses": "😎",
    "zany_face": "🤪",
    "upside_down_face": "🙃",
    "expressionless_face": "😑",
    "neutral_face": "😐",
    "yawning_face": "🥱",
    "sleeping_face": "😴",
    "pleading_face": "🥺",
    "face_screaming_in_fear": "😱",
    "person_shrugging": "🤷",
    "ok_hand": "👌",
    "victory_hand": "✌️",
    "waving_hand": "👋",
}

_SHORTCODE_RE = re.compile(r":([a-z0-9_+\-]{2,64}):", re.IGNORECASE)
_WS_RE = re.compile(r"\s{2,}")


def normalize_chat_text(text: Optional[str], keep_unknown: bool = False) -> str:
    """
    Converts :shortcode: tokens to real emoji. Unknown shortcodes are removed by default —
    ":some_obscure_custom_badge:" as literal words is noise in both the prompt and the chat card.

    Set keep_unknown=True to preserve them (useful when debugging what a source actually sent).
    """
    if not text:
        return ""

    def _sub(m: re.Match) -> str:
        name = m.group(1).lower()
        if name in SHORTCODE_TO_EMOJI:
            return SHORTCODE_TO_EMOJI[name]
        return m.group(0) if keep_unknown else ""

    out = _SHORTCODE_RE.sub(_sub, text)
    return _WS_RE.sub(" ", out).strip()


# Codepoint ranges that an emoji font should handle. Kept broad but not greedy: plain punctuation
# and Latin text must never be routed to the emoji font.
_EMOJI_RE = re.compile(
    "[" 
    "\U0001F000-\U0001FAFF"   # pictographs, emoticons, symbols, supplemental
    "\U00002600-\U000027BF"   # misc symbols and dingbats
    "\U00002190-\U000021FF"   # arrows
    "\U00002B00-\U00002BFF"
    "\U0001F1E6-\U0001F1FF"   # regional indicators (flags)
    "\U0000FE0F\U0000200D\U000020E3"  # variation selector, ZWJ, keycap
    "]"
)


def contains_emoji(text: str) -> bool:
    return bool(text) and bool(_EMOJI_RE.search(text))


def split_emoji_runs(text: str):
    """Yields (is_emoji, chunk) runs so each can be drawn with the font that can draw it."""
    if not text:
        return
    runs, cur, cur_is = [], [], None
    for ch in text:
        is_e = bool(_EMOJI_RE.match(ch))
        if cur_is is None or is_e == cur_is:
            cur.append(ch)
            cur_is = is_e
        else:
            runs.append((cur_is, "".join(cur)))
            cur, cur_is = [ch], is_e
    if cur:
        runs.append((cur_is, "".join(cur)))
    for r in runs:
        yield r


def font_can_draw(font, ch: str) -> bool:
    """
    True if `font` draws a real glyph for `ch`.

    font.metrics() is not usable here: a color emoji font reports None for characters it renders
    perfectly well. Instead render the character and compare it against an unassigned codepoint —
    if the pixels are identical, the font is drawing a tofu box.
    """
    if font is None or not ch:
        return False
    try:
        import pygame
        a = font.render(ch, True, (255, 255, 255))
        b = font.render("\uFFFF", True, (255, 255, 255))
        if a.get_size() != b.get_size():
            return True
        return pygame.image.tostring(a, "RGBA") != pygame.image.tostring(b, "RGBA")
    except Exception:
        return True


def strip_unrenderable(text: str, font) -> str:
    """
    Drops characters the font draws as a tofu box. Used only when no emoji font is available;
    the preferred path is render_mixed(), which draws them properly instead.
    """
    if not text or font is None:
        return text or ""
    kept = "".join(ch for ch in text if not _EMOJI_RE.match(ch) or font_can_draw(font, ch))
    return _WS_RE.sub(" ", kept).strip()


def load_emoji_font(size: int):
    """
    Finds a font that can actually draw emoji, at the requested size.
    Tries the platform's emoji font by name, then known file paths. Returns None if none works.
    """
    try:
        import pygame
    except Exception:
        return None

    for name in ("Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji",
                 "Twemoji Mozilla", "Segoe UI Symbol", "Symbola"):
        try:
            f = pygame.font.SysFont(name, size)
            if f and font_can_draw(f, "\U0001F602"):
                return f
        except Exception:
            pass

    for path in ("C:/Windows/Fonts/seguiemj.ttf",
                 "/System/Library/Fonts/Apple Color Emoji.ttc",
                 "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"):
        try:
            f = pygame.font.Font(path, size)
            if f and font_can_draw(f, "\U0001F602"):
                return f
        except Exception:
            pass
    return None


def render_mixed(text: str, font, emoji_font, color):
    """
    Renders `text` as one surface, drawing emoji with `emoji_font` and everything else with
    `font`. Emoji surfaces are scaled to the text line height and baseline-aligned, because
    bitmap color fonts render at a fixed (large) size regardless of the size requested.

    Returns None when no emoji handling is needed, so the caller can use its normal fast path.
    """
    import pygame

    if not text or emoji_font is None or not contains_emoji(text):
        return None

    line_h = font.get_height()
    ascent = font.get_ascent()
    parts = []
    for is_emoji, chunk in split_emoji_runs(text):
        if not chunk:
            continue
        if is_emoji:
            surf = emoji_font.render(chunk, True, color)
            if surf.get_height() != line_h and surf.get_height() > 0:
                scale = line_h / surf.get_height()
                surf = pygame.transform.smoothscale(
                    surf, (max(1, int(surf.get_width() * scale)), line_h)
                )
            parts.append((surf, True))
        else:
            parts.append((font.render(chunk, True, color), False))

    if not parts:
        return None

    width = sum(p.get_width() for p, _ in parts)
    out = pygame.Surface((max(1, width), line_h), pygame.SRCALPHA)
    x = 0
    for surf, is_emoji in parts:
        # Text runs sit on the baseline; scaled emoji already fill the line box.
        y = 0 if is_emoji else max(0, ascent - font.get_ascent())
        out.blit(surf, (x, y))
        x += surf.get_width()
    return out


def has_renderable_content(text: str) -> bool:
    """True when there is something worth drawing beyond whitespace and punctuation."""
    return bool(re.sub(r"[\s\W_]+", "", text or ""))
