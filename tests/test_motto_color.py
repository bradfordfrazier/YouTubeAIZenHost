"""
The motto takes the colour of the mood that just played, latched so it never shifts mid-display.

Previously it was hard-coded celestial cyan, with a comment explaining why: c_primary lerps
continuously as moods blend, so using it live would make the motto drift colour while on screen.
Latching on appearance gives the mood colour without that drift.
"""
from pathlib import Path
import os
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent

pytest.importorskip("pygame")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")


def _vis():
    from visualizer import Visualizer
    return Visualizer()


def _draw(v):
    v.render_frame(audio_metrics={"rms": 0.0, "is_speaking": False, "spectrum": [0.0] * 32},
                   chat_messages=[], obs_connected=True, engagement_mode="active",
                   concurrent_viewers=1, is_stream_live=True, pinned_chat_message=None)


def _settle(v, mood, frames=120):
    """Plays a turn in `mood` with the motto hidden, so the palette finishes lerping."""
    v.ai_text_current = "The AI is speaking right now"
    v.set_mood(mood)
    for _ in range(frames):
        _draw(v)


def test_motto_takes_the_colour_of_the_mood_that_just_played():
    v = _vis()
    try:
        motto = v.cfg.motto_phrase
        seen = {}
        for mood in ("savage", "transcendent", "deadpan", "hyped"):
            _settle(v, mood)
            v.ai_text_current = motto
            v.ai_text_alpha = 1.0
            _draw(v)
            seen[mood] = v._motto_latched_color
            v.ai_text_current = ""      # release for the next round
            _draw(v)
        assert len(set(seen.values())) == len(seen), f"moods produced duplicate colours: {seen}"
        assert all(c is not None for c in seen.values())
    finally:
        v.close()


def test_colour_is_held_while_the_motto_is_displayed():
    """A mood change mid-display must not make the motto drift colour."""
    v = _vis()
    try:
        motto = v.cfg.motto_phrase
        _settle(v, "savage")
        v.ai_text_current = motto
        v.ai_text_alpha = 1.0
        _draw(v)
        latched = v._motto_latched_color

        v.set_mood("hyped")
        for _ in range(120):
            _draw(v)
        assert v._motto_latched_color == latched, "motto colour shifted while on screen"
    finally:
        v.close()


def test_latch_is_released_when_the_motto_leaves():
    v = _vis()
    try:
        motto = v.cfg.motto_phrase
        _settle(v, "savage")
        v.ai_text_current = motto
        _draw(v)
        assert v._motto_latched_color is not None

        v.ai_text_current = "An answer is on screen now"
        _draw(v)
        assert v._motto_latched_color is None, "latch must release so the next motto re-samples"
    finally:
        v.close()


def test_feature_can_be_switched_off():
    v = _vis()
    try:
        v.cfg.motto_uses_mood_color = False
        motto = v.cfg.motto_phrase
        _settle(v, "savage")
        v.ai_text_current = motto
        _draw(v)
        # With the feature off the fixed celestial colour is used and nothing is latched.
        assert v._motto_latched_color is None
    finally:
        v.cfg.motto_uses_mood_color = True
        v.close()


def test_fade_out_for_turn_releases_latch_when_dissolved():
    """Real live turn flow: motto fades out for speech, mood changes, motto re-emerges in new color."""
    v = _vis()
    try:
        motto = v.cfg.motto_phrase
        v.ai_text_current = motto
        v.ai_text_alpha = 1.0
        _draw(v)
        initial_latched = v._motto_latched_color
        assert initial_latched is not None

        # Turn begins: fade out for speech
        v.fade_out_for_turn()
        for _ in range(60):
            _draw(v)
        assert v.ai_text_alpha <= 0.005
        assert v._motto_latched_color is None, "latch must be released once motto fades below threshold"

        # AI speaks in savage mood
        v.set_mood("savage")
        for _ in range(120):
            _draw(v)

        # Speech finishes: motto returns via clear_subtitle
        v.clear_subtitle()
        # Fast-forward motto pause & fade-in
        for _ in range(250):
            _draw(v)

        assert v.ai_text_current == motto
        assert v.ai_text_alpha > 0.05
        new_latched = v._motto_latched_color
        assert new_latched is not None
        assert new_latched != initial_latched, f"motto remained old colour {initial_latched}"
        assert new_latched[0] > 200, f"expected savage reddish color, got {new_latched}"
    finally:
        v.close()
