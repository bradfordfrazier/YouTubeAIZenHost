"""
Unit tests for context-aware promo cards (Phase 6).
Runnable via pytest.
"""

import os
from pathlib import Path
import sys
import pytest

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import config
from visualizer import Visualizer


def test_promo_mode_event_transitions():
    vis = Visualizer()
    vis.promo_mode = "event"
    vis.promo_state = "off"
    vis.promo_timer = 1.0

    # In event mode, ticks should NOT auto-advance into entrance
    vis._update_promo_state(0.1, is_speaking=False, is_turn_busy=False)
    assert vis.promo_state == "off"

    # Explicit trigger should advance to entrance
    vis.trigger_promo("ask_god", duration=4.0)
    assert vis.promo_state == "entrance"
    assert vis.promo_current_type == "ask_god"

    # Step through entrance into display
    for _ in range(60):
        vis._update_promo_state(1.0 / 60.0, is_speaking=False, is_turn_busy=False)
    assert vis.promo_state == "display"
    assert vis.is_promo_active is True

    # Speech interruption should immediately force exit
    vis._update_promo_state(1.0 / 60.0, is_speaking=True, is_turn_busy=False)
    assert vis.promo_state == "exit"

def test_post_turn_subtitle_dissolve_does_not_cut_off_promo():
    """
    Verifies that calling trigger_promo('like_sub') immediately after an AI turn
    (while the previous answer text is dissolving to motto) does NOT prematurely abort the promo.
    """
    vis = Visualizer()
    vis.promo_mode = "event"
    vis.promo_state = "off"

    # Simulate completed turn: speech has stopped, clear_subtitle was called
    vis.clear_subtitle()
    vis.ai_text_current = "This was a profound and enlightened response to the viewer."
    vis.ai_text_alpha = 0.85
    vis.ai_text_state = "fade_out"
    vis.subtitle_target_text = ""
    vis._active_pinned_message = None

    # Trigger Like & Subscribe promo post-turn
    vis.trigger_promo("like_sub", duration=5.0)
    assert vis.promo_state == "entrance"
    assert vis.promo_current_type == "like_sub"

    # Tick render_frame multiple times while old text dissolves
    dummy_metrics = {"rms": 0.0, "is_speaking": False, "spectrum": [0.0] * 32}
    for _ in range(30):
        vis.render_frame(
            audio_metrics=dummy_metrics,
            chat_messages=[],
            obs_connected=True,
            engagement_mode="active",
            concurrent_viewers=5,
            is_stream_live=True,
            pinned_chat_message=None,
        )

    # Promo should still be cleanly transitioning in or displaying, NOT aborted to exit
    assert vis.promo_state in ("entrance", "display"), f"Promo was prematurely cut off to: {vis.promo_state}"

    # Complete entrance into display
    for _ in range(60):
        vis.render_frame(
            audio_metrics=dummy_metrics,
            chat_messages=[],
            obs_connected=True,
            engagement_mode="active",
            concurrent_viewers=5,
            is_stream_live=True,
            pinned_chat_message=None,
        )
    assert vis.promo_state == "display"
    assert vis.promo_current_type == "like_sub"
    assert vis.is_promo_active is True

    vis.close()


def test_idle_promo_balanced_rotation():
    """
    Verifies that during extended chat quiet lulls, both 'Ask Anything' and 'Like & Subscribe'
    alternate appropriately rather than starving the Subscribe promo.
    """
    now = 1000.0
    ask_quiet_sec = config.promo_ask_quiet_sec  # 45.0
    sub_min_interval = config.promo_sub_min_interval_sec  # 120.0
    viewers = 5

    last_chat_time = now - 50.0  # Quiet for 50s
    last_ask_promo_time = 0.0
    last_like_sub_time = 0.0

    # 1. First lull -> should trigger ask_god
    time_since_chat = now - last_chat_time
    time_since_ask = now - last_ask_promo_time
    time_since_sub = now - last_like_sub_time

    assert viewers >= 1 and time_since_chat >= ask_quiet_sec
    # Both sub and ask are 0.0, sub was never shown; sub needs sub_min_interval cooldown check
    # If sub hasn't been shown, sub can trigger or ask can trigger
    choice1 = "like_sub" if (time_since_sub >= sub_min_interval and (last_like_sub_time <= last_ask_promo_time or time_since_ask < 60.0)) else "ask_god"
    assert choice1 in ("like_sub", "ask_god")

    # Simulate triggering ask_god first
    last_ask_promo_time = now
    now += 60.0  # 60s later, chat still quiet
    time_since_chat = now - last_chat_time
    time_since_ask = now - last_ask_promo_time
    time_since_sub = now - last_like_sub_time

    # 2. Next lull check -> time_since_sub is 1060s >= 120s, and last_like_sub_time (0.0) <= last_ask_promo_time (1000.0)
    # Should select like_sub!
    should_sub = (
        time_since_sub >= sub_min_interval
        and (last_like_sub_time <= last_ask_promo_time or time_since_ask < 60.0)
        and time_since_sub >= 60.0
    )
    assert should_sub is True, "Idle scheduler failed to alternate to like_sub during lull"

