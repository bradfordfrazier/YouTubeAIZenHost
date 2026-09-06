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
    exec("import re\nfrom typing import List, Tuple\n" + body, ns)
    stub = types.SimpleNamespace(beat_pattern=re.compile(r"\[\s*BEAT\s*\]", re.IGNORECASE))
    stub._split_piece = types.MethodType(ns["_split_piece"], stub)
    stub._extract_completed_sentences = types.MethodType(ns["_extract_completed_sentences"], stub)
    return stub


def test_beat_before_punchline_sentence():
    sp = _splitter()
    sents, rem = sp._extract_completed_sentences("You asked the universe for a sign. [BEAT] It sent you a buffering icon. ")
    assert sents == [
        ("You asked the universe for a sign.", False),
        ("It sent you a buffering icon.", True),
    ]
    assert rem == ""


def test_mid_sentence_beat_flushes_fragment():
    sp = _splitter()
    sents, rem = sp._extract_completed_sentences("And that is exactly why [BEAT] I invented Tuesdays. ")
    assert sents == [("And that is exactly why", False), ("I invented Tuesdays.", True)]
    assert rem == ""


def test_trailing_beat_survives_streaming_boundary():
    sp = _splitter()
    # First stream chunk ends right after the marker
    sents1, rem1 = sp._extract_completed_sentences("Enlightenment is simple. [BEAT] ")
    assert sents1 == [("Enlightenment is simple.", False)]
    assert rem1.startswith("[BEAT]")
    # Next tokens arrive
    sents2, rem2 = sp._extract_completed_sentences(rem1 + "You just have to stop refreshing. ")
    assert sents2 == [("You just have to stop refreshing.", True)]
    assert rem2 == ""


def test_no_beat_is_unchanged():
    sp = _splitter()
    sents, rem = sp._extract_completed_sentences("First full sentence here. Second one arrives now. And a partial")
    assert sents == [("First full sentence here.", False), ("Second one arrives now.", False)]
    assert rem == "And a partial"


def test_push_audio_uses_beat_gap():
    e = TTSEngine()
    e.ndi_buffer_enabled = False
    e.cfg.inter_sentence_gap_sec = 0.15
    e.cfg.tts_beat_gap_sec = 0.55
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
