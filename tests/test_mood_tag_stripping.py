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
    # Bare bracketed mood name — what gemini-3.8-flash actually emitted, and what got spoken
    # aloud on stream because the pattern required the literal word "MOOD".
    ("[DEADPAN] text", "deadpan"),
    ("[deadpan] text", "deadpan"),
    ("(SAVAGE) text", "savage"),
    ("**[HYPED]** text", "hyped"),
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
        mood = next((g for g in m.groups() if g), "").strip().lower().replace(" ", "_")
        assert mood == expected, (raw, mood)
        assert "MOOD" not in b.mood_pattern.sub("", raw).upper()


def test_viewer_text_is_not_mistaken_for_a_tag():
    """The bare form must only match at the very start, or chat gets eaten."""
    from ai_brain import AIBrain
    b = AIBrain()
    for benign in ("my mood: terrible today", "the mood in here is weird",
                   "I was in a mood: annoyed", "what mood are you in",
                   # other bracketed markup must survive: the CAST badge and the beat marker
                   "[CAST] badge", "[BEAT] punchline", "(laughs) something"):
        assert not b.mood_pattern.search(benign), f"false positive on {benign!r}"


def test_tts_layer_scrubs_markers_as_a_last_resort():
    from tts_engine import TTSEngine
    e = TTSEngine()
    for raw in ("[DEADPAN] Management regrets to inform the steel.",
                "(HYPED) A line.", "**[CHILL]** A line.",
                "[MOOD: savage] I bought a clock.", "(MOOD: deadpan) A line.",
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


def test_bare_mood_name_recovers_the_right_mood_not_just_strips_it():
    """
    A missed tag cost twice over: the bracket was spoken AND the mood fell back to the default,
    so a deadpan bit was synthesized at chill's exaggeration.
    """
    from tts_engine import TTSEngine
    e = TTSEngine()
    clean, mood, exag, _ = e._prepare_text("[DEADPAN] Management regrets to inform the steel.", "neutral")
    assert mood == "deadpan"
    assert exag == e.mood_exaggeration_map["deadpan"]
    assert clean.startswith("Management regrets")


def test_mood_vocabulary_is_shared_by_construction():
    """Both layers build the bare-name alternation from the config map, so they cannot drift."""
    brain_src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    tts_src = (ROOT / "tts_engine.py").read_text(encoding="utf-8", errors="ignore")
    assert "tts_mood_exaggeration_map" in brain_src
    assert "tts_mood_exaggeration_map" in tts_src
    assert "_build_mood_tag_re" in tts_src


def test_invented_mood_names_are_mapped_not_spoken():
    """
    Models invent moods that are not in the vocabulary. "[DRY]" was read aloud as "D-R-Y" because
    the bare-name pattern only matched known moods. Common inventions now map onto real moods.
    """
    from ai_brain import AIBrain
    b = AIBrain()
    for raw, expected in (("[DRY] text", "deadpan"), ("[WRY] text", "deadpan"),
                          ("[SARDONIC] text", "snarky"), ("[AMUSED] text", "laughing"),
                          ("[MOOD: dry] text", "deadpan")):
        m = b.mood_pattern.search(raw)
        assert m, f"pattern missed {raw!r}"
        got = next((g for g in m.groups() if g), "")
        assert b._resolve_mood(got) == expected, (raw, b._resolve_mood(got))


def test_unrecognised_leading_tag_is_stripped_anyway():
    """
    An invented tag with no sensible mapping ("[WHISPERING]") must still never be synthesized.
    The catch-all is start-anchored so [CAST] and [BEAT] elsewhere are untouched.
    """
    from tts_engine import TTSEngine
    e = TTSEngine()
    clean, mood, _, _ = e._prepare_text("[WHISPERING] A line that should survive.", "neutral")
    assert clean == "A line that should survive."
    assert mood == "neutral", "an unmappable tag must not change the mood"

    # ...but a beat marker mid-text is handled by its own rule, not eaten by the catch-all
    clean2, _, _, _ = e._prepare_text("A setup. [BEAT] A punchline.", "deadpan")
    assert "setup" in clean2 and "punchline" in clean2 and "[" not in clean2


def test_alias_map_is_shared_by_both_layers():
    brain_src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    tts_src = (ROOT / "tts_engine.py").read_text(encoding="utf-8", errors="ignore")
    assert "tts_mood_aliases" in brain_src and "tts_mood_aliases" in tts_src
    assert "leading_tag_pattern" in brain_src
    assert "_LEADING_TAG_RE" in tts_src


def test_bit_prompt_offers_the_full_mood_vocabulary():
    """
    A prompt strip-down removed the mood list from the bit block, leaving only the
    "[MOOD: deadpan]" inside the one-liner rule. Every bit of every form then came out deadpan,
    which also froze the avatar colour and the TTS exaggeration for a whole session.
    """
    import re as _re
    import sys as _s
    _s.path.insert(0, str(ROOT))
    import ai_brain
    from config import config

    b = ai_brain.AIBrain()
    for trigger in ("[SPONTANEOUS_REFLECTION]", "Chat message from @X: 'why do we dream?'"):
        p = b._build_context_prompt(trigger)
        offered = {m.lower() for m in _re.findall(r"\[MOOD:\s*([a-z_]+)\]", p, _re.I)} - {"x"}
        assert len(offered) >= 8, f"{trigger} offers only {sorted(offered)}"
        assert "deadpan" in offered and "transcendent" in offered

    # And the list is built from config, so adding a mood cannot leave the prompt stale.
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    assert "tts_mood_exaggeration_map" in src
    for mood in ("savage", "chill", "curious"):
        assert mood in config.tts_mood_exaggeration_map
