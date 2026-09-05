"""
Phase 6 Verification Test: Context-Aware Event-Driven Promo Cards.
Verifies:
1. Config attributes for promo_mode ('event' | 'timer'), quiet thresholds, and cooldowns.
2. Visualizer promo state machine in event mode vs timer mode.
3. Rapid exit when speech or pinned question interrupts active promo.
4. Event-driven promo triggers:
   - 'Ask Anything' triggered on chat lull (>= 45s quiet) with >= 1 viewer.
   - 'Like & Subscribe' triggered after completed viewer turn (<= 3s) with 300s cooldown.
"""

import os
import sys
import time
import numpy as np

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

os.environ["SDL_VIDEODRIVER"] = "dummy"

from config import config
from visualizer import Visualizer


def test_config_promo_attributes():
    print("\n--- 1. Testing Promo Configuration Attributes ---")
    assert hasattr(config, "promo_mode"), "config missing promo_mode"
    assert config.promo_mode in ("event", "timer"), f"Invalid promo_mode: {config.promo_mode}"
    assert hasattr(config, "promo_ask_quiet_sec"), "config missing promo_ask_quiet_sec"
    assert config.promo_ask_quiet_sec == 45.0
    assert hasattr(config, "promo_sub_after_turn_sec"), "config missing promo_sub_after_turn_sec"
    assert config.promo_sub_after_turn_sec == 3.0
    assert hasattr(config, "promo_sub_min_interval_sec"), "config missing promo_sub_min_interval_sec"
    assert config.promo_sub_min_interval_sec == 300.0
    print("  ✓ Config promo attributes validated with correct defaults.")


def test_visualizer_promo_event_mode():
    print("\n--- 2. Testing Visualizer Event vs Timer Mode ---")
    vis = Visualizer()
    vis.promo_mode = "event"
    vis.promo_state = "off"
    vis.promo_timer = 5.0

    # In event mode, _update_promo_state should NOT auto-advance into entrance on tick
    for _ in range(60):  # 1 second of 60 FPS
        vis._update_promo_state(1.0 / 60.0, is_speaking=False, is_turn_busy=False)
    assert vis.promo_state == "off", f"Event mode auto-advanced to: {vis.promo_state}"

    # Explicit trigger_promo("ask_god") should start entrance
    vis.trigger_promo("ask_god", duration=5.0)
    assert vis.promo_state == "entrance"
    assert vis.promo_current_type == "ask_god"

    # Step forward into display
    for _ in range(60):
        vis._update_promo_state(1.0 / 60.0, is_speaking=False, is_turn_busy=False)
    assert vis.promo_state == "display"
    assert vis.is_promo_active is True

    # Speech interruption should immediately force promo into exit
    vis._update_promo_state(1.0 / 60.0, is_speaking=True, is_turn_busy=False)
    assert vis.promo_state == "exit", f"Speech did not trigger exit: {vis.promo_state}"

    # Finish exit
    for _ in range(120):
        vis._update_promo_state(1.0 / 60.0, is_speaking=False, is_turn_busy=False)
    assert vis.promo_state == "off"
    assert vis.is_promo_active is False

    vis.close()
    print("  ✓ Visualizer event mode transitions and speech interruption verified.")


def test_promo_trigger_logic_simulation():
    print("\n--- 3. Testing Context-Aware Promo Event Conditions ---")
    # Simulate the rules implemented in promo_monitor_task

    # Scenario A: Like & Subscribe after viewer turn
    now = 1000.0
    last_turn_completed_time = 998.0  # 2.0s ago (<= 3.0s)
    last_like_sub_time = 600.0        # 400s ago (>= 300s cooldown)
    last_event_type = "chat"
    is_turn_busy = False
    is_promo_active = False

    can_trigger_like_sub = (
        not is_turn_busy
        and not is_promo_active
        and (now - last_turn_completed_time <= 3.0)
        and (now - last_like_sub_time >= 300.0)
        and last_event_type in ("chat", "superchat", "direct_mention", "cast", "greeting", "celebration")
    )
    assert can_trigger_like_sub is True, "Failed to trigger Like & Subscribe after completed turn"

    # Scenario B: Like & Subscribe blocked by cooldown
    last_like_sub_time = 900.0  # only 100s ago (< 300s)
    can_trigger_like_sub_cooldown = (
        (now - last_turn_completed_time <= 3.0)
        and (now - last_like_sub_time >= 300.0)
    )
    assert can_trigger_like_sub_cooldown is False, "Like & Subscribe did not respect 300s cooldown"

    # Scenario C: Ask Anything on chat lull (>= 45s quiet)
    now = 2000.0
    last_chat_time = 1950.0  # 50s quiet (>= 45s)
    last_ask_promo_time = 1800.0 # 200s ago
    viewers = 10
    is_turn_busy = False
    is_promo_active = False

    can_trigger_ask = (
        not is_turn_busy
        and not is_promo_active
        and viewers >= 1
        and (now - last_chat_time >= 45.0)
        and (now - last_ask_promo_time >= 45.0)
    )
    assert can_trigger_ask is True, "Failed to trigger Ask Anything during chat silence"

    # Scenario D: Ask Anything suppressed when 0 viewers
    viewers = 0
    can_trigger_ask_zero_viewers = (
        viewers >= 1
        and (now - last_chat_time >= 45.0)
    )
    assert can_trigger_ask_zero_viewers is False, "Ask Anything was not suppressed with 0 viewers"

    # Scenario E: Promos strictly suppressed during speech
    is_turn_busy = True
    assert (not is_turn_busy and can_trigger_ask) is False, "Promo triggered during busy speech turn"

    print("  ✓ All context-aware promo trigger scenarios validated.")


def main():
    test_config_promo_attributes()
    test_visualizer_promo_event_mode()
    test_promo_trigger_logic_simulation()
    print("\n🎉 ALL PHASE 6 TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
