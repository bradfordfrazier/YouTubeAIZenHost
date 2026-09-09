"""
[BEAT] comedic-pause pipeline tests.

1. AIBrain._extract_completed_sentences flags the chunk after [BEAT], flushes the fragment
   before a mid-sentence beat, and carries a trailing beat across streaming boundaries.
2. TTSEngine.push_audio inserts tts_beat_gap_sec (not inter_sentence_gap_sec) for beat chunks.
3. Regression: sentence events carry the text under the "text" key (app.py reads that key).
"""

from pathlib import Path
import re
import sys
import types
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tts_engine import TTSEngine  # noqa: E402


def _splitter():
    """Bind AIBrain's splitter methods to a stub so the test doesn't need Gemini/pygame deps."""
    import importlib.util
    src = (Path(__file__).resolve().parent.parent / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    ns = {}
    # Pull just the two methods out of the class body by exec'ing them into a namespace.
    start = src.index("    def _split_piece(self, buffer: str)")
    end = src.index("    async def generate_response_stream(")
    body = "\n".join(line[4:] if line.startswith("    ") else line for line in src[start:end].splitlines())
    exec("import re\nfrom typing import Any, AsyncGenerator, Dict, List, Optional, Tuple\n" + body, ns)
    stub = types.SimpleNamespace(
        beat_pattern=re.compile(r"\[\s*BEAT\s*\]", re.IGNORECASE),
        mood_pattern=re.compile(r"\[MOOD:\s*([a-zA-Z_-]+)\]", re.IGNORECASE),
    )
    stub._split_piece = types.MethodType(ns["_split_piece"], stub)
    stub._extract_completed_sentences = types.MethodType(ns["_extract_completed_sentences"], stub)
    return stub


def _split(sp, text, base=None):
    sents, rem, mood_after = sp._extract_completed_sentences(text, base_mood=base)
    return [(t, b) for t, b, _ in sents], rem, [m for _, _, m in sents], mood_after


def test_beat_before_punchline_sentence():
    sp = _splitter()
    sents, rem, _, _ = _split(sp, "You asked the universe for a sign. [BEAT] It sent you a buffering icon. ")
    assert sents == [
        ("You asked the universe for a sign.", False),
        ("It sent you a buffering icon.", True),
    ]
    assert rem == ""


def test_mid_sentence_beat_flushes_fragment():
    sp = _splitter()
    sents, rem, _, _ = _split(sp, "And that is exactly why [BEAT] I invented Tuesdays. ")
    assert sents == [("And that is exactly why", False), ("I invented Tuesdays.", True)]
    assert rem == ""


def test_trailing_beat_survives_streaming_boundary():
    sp = _splitter()
    # First stream chunk ends right after the marker
    sents1, rem1, _, _ = _split(sp, "Enlightenment is simple. [BEAT] ")
    assert sents1 == [("Enlightenment is simple.", False)]
    assert rem1.startswith("[BEAT]")
    # Next tokens arrive
    sents2, rem2, _, _ = _split(sp, rem1 + "You just have to stop refreshing. ")
    assert sents2 == [("You just have to stop refreshing.", True)]
    assert rem2 == ""


def test_no_beat_is_unchanged():
    sp = _splitter()
    sents, rem, moods, _ = _split(sp, "First full sentence here. Second one arrives now. And a partial", base="deadpan")
    assert sents == [("First full sentence here.", False), ("Second one arrives now.", False)]
    assert moods == ["deadpan", "deadpan"]
    assert rem == "And a partial"


def test_push_audio_uses_beat_gap():
    e = TTSEngine()
    e.ndi_buffer_enabled = False
    e.cfg.inter_sentence_gap_sec = 0.15
    e.cfg.tts_beat_gap_sec = 0.55
    e.cfg.tts_beat_gap_jitter = 0.0  # deterministic for the exact-length assertions below
    sr = e.sample_rate
    one_sec = np.ones((sr, 2), dtype=np.float32) * 0.3

    e.begin_utterance()
    e.push_audio(one_sec)                      # first chunk: no gap
    normal = e.push_audio(one_sec)             # +150 ms
    beat = e.push_audio(one_sec, beat_before=True)  # +550 ms
    e.end_utterance()

    assert len(normal) == sr + int(sr * 0.15)
    assert len(beat) == sr + int(sr * 0.55)
    assert np.all(beat[: int(sr * 0.55)] == 0.0), "beat gap must be silence"


def test_sentence_event_key_is_text():
    """app.py reads chunk_ev['text']; the brain must yield that key (was 'sentence' vs 'text' mismatch)."""
    src = (Path(__file__).resolve().parent.parent / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    yields = re.findall(r'yield \{"type": "sentence",([^}]*)\}', src)
    assert yields, "no sentence events found"
    for y in yields:
        assert '"text":' in y and '"beat_before":' in y, y
    app_src = (Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8", errors="ignore")
    assert 'chunk_ev.get("text")' in app_src


def test_inline_mood_switch_on_closer():
    sp = _splitter()
    sents, rem, moods, after = _split(
        sp, "You asked the universe for a sign. [BEAT] [MOOD: savage] It sent you a buffering icon. ", base="deadpan"
    )
    assert sents == [("You asked the universe for a sign.", False), ("It sent you a buffering icon.", True)]
    assert moods == ["deadpan", "savage"]
    assert after == "savage"
    assert rem == ""


def test_inline_mood_is_sticky_and_survives_stream_boundary():
    sp = _splitter()
    s1, r1, m1, after1 = _split(sp, "Setup line goes here. [MOOD: hyped] ", base="deadpan")
    assert m1 == ["deadpan"] and after1 == "hyped"
    assert "[MOOD: hyped]" in r1
    s2, r2, m2, after2 = _split(sp, r1 + "First loud line here. Second loud line here. ", base=after1)
    assert m2 == ["hyped", "hyped"]
    assert r2 == ""


def test_mood_marker_mid_sentence_is_boundary():
    sp = _splitter()
    sents, rem, moods, _ = _split(sp, "And that is exactly why [MOOD: laughing] I invented Tuesdays. ", base="deadpan")
    assert sents == [("And that is exactly why", False), ("I invented Tuesdays.", False)]
    assert moods == ["deadpan", "laughing"]


def test_beat_gap_jitter_varies_but_stays_in_range():
    """A fixed pause every time becomes a tic; jitter must vary it without going out of bounds."""
    e = TTSEngine()
    e.ndi_buffer_enabled = False
    e.cfg.inter_sentence_gap_sec = 0.15
    e.cfg.tts_beat_gap_sec = 0.45
    e.cfg.tts_beat_gap_jitter = 0.25
    sr = e.sample_rate
    one = np.ones((sr, 2), dtype=np.float32) * 0.2

    gaps = []
    for _ in range(12):
        e.begin_utterance()
        e.push_audio(one)
        beat = e.push_audio(one, beat_before=True)
        gaps.append((len(beat) - sr) / sr)
        e.end_utterance()
        e.clear_audio_buffer()

    assert all(0.45 * 0.75 - 0.01 <= g <= 0.45 * 1.25 + 0.01 for g in gaps), gaps
    assert len(set(round(g, 3) for g in gaps)) > 1, "jitter produced identical gaps"

    # jitter=0 must be exact
    e.cfg.tts_beat_gap_jitter = 0.0
    e.begin_utterance()
    e.push_audio(one)
    beat = e.push_audio(one, beat_before=True)
    assert len(beat) == sr + int(sr * 0.45)


def test_beat_prompt_requires_a_reversal():
    """The beat must be described as earned, not as a default step."""
    src = (Path(__file__).resolve().parent.parent / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    assert "Put [BEAT] immediately before the closer (the last sentence)." not in src
    assert "REVERSES" in src
    assert "Most replies should contain no [BEAT]" in src
    assert "Most bits should have no [BEAT]" in src
