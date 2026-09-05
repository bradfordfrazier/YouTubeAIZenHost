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

    vis.close()
