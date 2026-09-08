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


def strip_unrenderable(text: str, font) -> str:
    """
    Drops characters the given pygame font cannot draw. A missing glyph renders as a tofu box,
    which looks like a bug on stream; dropping it just looks like the viewer typed less.

    Falls back to returning the text unchanged if the font cannot be queried.
    """
    if not text or font is None:
        return text or ""
    try:
        metrics = font.metrics(text)
    except Exception:
        return text
    if not metrics or len(metrics) != len(text):
        return text
    kept = "".join(ch for ch, m in zip(text, metrics) if m is not None)
    return _WS_RE.sub(" ", kept).strip()


def has_renderable_content(text: str) -> bool:
    """True when there is something worth drawing beyond whitespace and punctuation."""
    return bool(re.sub(r"[\s\W_]+", "", text or ""))
