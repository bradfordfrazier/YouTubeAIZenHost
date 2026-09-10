"""
Delivery markers must never be spoken aloud.

The mood tag was being read out on stream because the pattern only accepted one exact shape.
Models emit it several ways depending on model and version, and any shape the pattern misses goes
straight to the synthesizer. Both layers now scrub: the brain (which also needs the value) and
the TTS engine (which is the last thing before audio).
"""
from pathlib import Path
import asyncio
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent

SHAPES = [
    ("[MOOD: deadpan] text", "deadpan"),
    ("[MOOD:deadpan] text", "deadpan"),
    ("**[MOOD: deadpan]** text", "deadpan"),
    ("*[MOOD: deadpan]* text", "deadpan"),
    ("(MOOD: deadpan) text", "deadpan"),
    ("MOOD: deadpan\ntext", "deadpan"),
    ("[Mood: Deadpan] text", "deadpan"),
    ("[MOOD - deadpan] text", "deadpan"),
    ("[ MOOD: deadpan ] text", "deadpan"),
    ("[MOOD: dead pan] text", "dead_pan"),
]


def test_brain_detects_and_strips_every_shape():
    from ai_brain import AIBrain
    b = AIBrain()
    for raw, expected in SHAPES:
        m = b.mood_pattern.search(raw)
        assert m, f"pattern missed {raw!r} — it would be spoken aloud"
        mood = (m.group(1) or m.group(2) or "").strip().lower().replace(" ", "_")
        assert mood == expected, (raw, mood)
        assert "MOOD" not in b.mood_pattern.sub("", raw).upper()


def test_viewer_text_is_not_mistaken_for_a_tag():
    """The bare form must only match at the very start, or chat gets eaten."""
    from ai_brain import AIBrain
    b = AIBrain()
    for benign in ("my mood: terrible today", "the mood in here is weird",
                   "I was in a mood: annoyed", "what mood are you in"):
        assert not b.mood_pattern.search(benign), f"false positive on {benign!r}"


def test_tts_layer_scrubs_markers_as_a_last_resort():
    from tts_engine import TTSEngine
    e = TTSEngine()
    for raw in ("[MOOD: savage] I bought a clock.", "(MOOD: deadpan) A line.",
                "MOOD: hyped\nA line.", "A setup. [BEAT] A punchline.",
                "A line. [pause] Another.", "A line [laughs] more."):
        clean, _, _, _ = e._prepare_text(raw, "neutral")
        upper = clean.upper()
        assert "MOOD" not in upper and "[BEAT]" not in upper
        assert "[PAUSE]" not in upper and "[LAUGHS]" not in upper
        assert clean.strip(), f"scrub emptied {raw!r}"


def test_stripping_the_tag_does_not_join_words():
    """
    .strip() on the accumulated text removed the streamed chunk's trailing space, so the next
    delta fused onto the last word: "a spare key" + "for a house" -> "a spare keyfor a house".
    """
    import ai_brain
    b = ai_brain.AIBrain()

    async def fake(*a, **k):
        for piece in ["(MOOD: deadpan) I keep a spare key ", "for a house I do not own. "]:
            yield piece

    b._delta_stream = lambda *a, **k: fake()
    b.client = object()

    async def run():
        return [ev async for ev in b.generate_response_stream("[SPONTANEOUS_REFLECTION]",
                                                              bypass_cache=True)]
    events = asyncio.run(run())
    spoken = [e["full_text"] for e in events if e["type"] == "complete"][0]
    assert "keyfor" not in spoken, spoken
    assert "spare key for a house" in spoken
    assert "MOOD" not in spoken.upper()
