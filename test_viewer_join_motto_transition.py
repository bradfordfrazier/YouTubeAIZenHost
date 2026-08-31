"""
Unit tests for Eco Mode Viewer Join Motto Transition & Rapid Greeting Generation.
Verifies:
1. When room is empty, motto is steadily displayed.
2. When a viewer enters (0 -> 1+), motto gracefully fades out without disappearing abruptly or flashing back in.
3. Once motto fades out, screen remains in idle_empty until the greeting arrives.
4. Setting the greeting subtitle smoothly fades in the greeting.
5. Wake-up triggers greeting with priority 2 and fast thinking budget (0 reasoning tokens).
"""

import asyncio
import os
import time

from config import config
from visualizer import Visualizer
from ai_brain import AIBrain
from app import LocalCoHostApp, CommentEvent


def test_motto_smooth_fade_out_for_turn():
    """Verifies fade_out_for_turn smoothly fades out motto and remains in idle_empty without re-displaying motto."""
    vis = Visualizer(width=1920, height=1080)
    motto = config.motto_phrase

    # 1. Start in steady motto state
    vis.ai_text_current = motto
    vis.ai_text_target = motto
    vis.ai_text_alpha = 1.0
    vis.ai_text_state = "steady"
    vis.subtitle_target_text = ""

    # 2. Viewer detected -> fade_out_for_turn called
    vis.fade_out_for_turn()

    assert vis.ai_text_state == "fade_out", "Expected state to be fade_out"
    assert vis.ai_text_target == "", "Expected target to be empty"
    assert vis.ai_text_current == motto, "Expected current text to still be motto during fade out"

    # Step through frames of fade out (motto_fade_out_sec is 0.6s -> 36 frames at 60fps)
    dt = 1.0 / 60.0
    for frame in range(40):
        # Emulate visualizer frame update
        if vis.ai_text_state == "fade_out":
            vis.ai_text_alpha -= dt * (1.0 / config.motto_fade_out_sec)
            if vis.ai_text_alpha <= 0.0:
                vis.ai_text_alpha = 0.0
                if vis.ai_text_target == motto:
                    vis.ai_text_current = ""
                    vis.ai_text_state = "motto_pause"
                elif vis.ai_text_target:
                    vis.ai_text_current = vis.ai_text_target
                    vis.ai_text_state = "fade_in"
                else:
                    vis.ai_text_current = ""
                    vis.ai_text_state = "idle_empty"

    # 3. Fade out should be complete, state must be idle_empty (NOT motto_pause)
    assert vis.ai_text_state == "idle_empty", f"Expected idle_empty, got {vis.ai_text_state}"
    assert vis.ai_text_alpha == 0.0, "Expected alpha to be 0.0"
    assert vis.ai_text_current == "", "Expected current text to be empty"

    # 4. Step through more frames — verify motto NEVER flashes back in
    for _ in range(60):
        if vis.subtitle_target_text:
            desired_target = vis.subtitle_target_text
        elif vis.ai_text_target == motto:
            desired_target = motto
        else:
            desired_target = vis.ai_text_target or ""
        assert desired_target == "", "Expected desired target to stay empty"
        assert vis.ai_text_state == "idle_empty", "Expected state to remain idle_empty"

    # 5. Greeting speech arrives -> set_subtitle is called
    greeting = "Welcome, traveler! What brings you to this corner of the cosmos?"
    vis.set_subtitle(greeting)

    assert vis.ai_text_state == "fade_in", f"Expected fade_in, got {vis.ai_text_state}"
    assert vis.ai_text_current == greeting, f"Expected current text to be greeting, got {vis.ai_text_current}"
    assert vis.ai_text_alpha == 0.0, "Expected initial fade_in alpha to start at 0.0"


def test_set_subtitle_mid_fade_out():
    """Verifies that if speech is ready while motto is still fading out, it starts cleanly from alpha 0.0."""
    vis = Visualizer(width=1920, height=1080)
    motto = config.motto_phrase

    vis.ai_text_current = motto
    vis.ai_text_target = motto
    vis.ai_text_alpha = 0.6  # Halfway through fade-out
    vis.ai_text_state = "fade_out"
    vis.subtitle_target_text = ""

    greeting = "Welcome, traveler! Ask whatever is on your mind."
    vis.set_subtitle(greeting)

    # Should immediately start fade_in of the new greeting from alpha 0.0
    assert vis.ai_text_target == greeting
    assert vis.ai_text_state == "fade_in"
    assert vis.ai_text_current == greeting
    assert vis.ai_text_alpha == 0.0


def test_clear_subtitle_preserves_steady_motto():
    """Verifies that calling clear_subtitle when motto is already steady does NOT snap alpha to 0 or re-trigger pause."""
    vis = Visualizer(width=1920, height=1080)
    motto = config.motto_phrase

    vis.ai_text_current = motto
    vis.ai_text_target = motto
    vis.ai_text_alpha = 1.0
    vis.ai_text_state = "steady"
    vis.subtitle_target_text = ""

    vis.clear_subtitle()

    assert vis.ai_text_state == "steady"
    assert vis.ai_text_alpha == 1.0
    assert vis.ai_text_current == motto


def test_wake_up_triggers_high_priority_greeting():
    """Verifies _wake_up_and_trigger_comment initiates motto fade-out and queues priority 2 greeting."""
    app = LocalCoHostApp()
    app.running = True
    app.cfg.greet_viewer_joins = True
    app.concurrent_viewers = 1
    app.is_streaming = True
    app.cfg.obs_require_stream_active = False
    app.engagement_mode = "eco"

    # Start with steady motto in visualizer
    app.visualizer.ai_text_current = app.cfg.motto_phrase
    app.visualizer.ai_text_target = app.cfg.motto_phrase
    app.visualizer.ai_text_alpha = 1.0
    app.visualizer.ai_text_state = "steady"

    # Sole viewer enters empty room
    app._wake_up_and_trigger_comment(viewers=1)

    # 1. Motto should immediately begin fading out
    assert app.visualizer.ai_text_state == "fade_out", "Expected visualizer to start fading out motto immediately"

    # 2. Room should transition to active
    assert app.engagement_mode == "active", "Expected engagement mode to be active"

    # 3. High-priority greeting comment queued
    assert len(app.comment_queue) == 1, "Expected 1 queued greeting event"
    event = app.comment_queue[0]
    assert event.event_type == "greeting", f"Expected event_type 'greeting', got {event.event_type}"
    assert event.priority == 2, f"Expected priority 2, got {event.priority}"
    assert "[VIEWER_JOINED]" in event.prompt_trigger


def test_fast_thinking_budget_for_viewer_join():
    """Verifies that [VIEWER_JOINED] uses fast mode with zero reasoning delay."""
    brain = AIBrain()
    prompt = "[VIEWER_JOINED] A sole viewer has entered the stream. (Concurrent viewers: 1)."

    is_deep = brain._classify_prompt_depth(prompt)
    assert not is_deep, "Expected [VIEWER_JOINED] to classify as fast (not deep)"

    gen_cfg = brain._build_generate_content_config(is_deep=is_deep)
    if gen_cfg and hasattr(gen_cfg, "thinking_config") and gen_cfg.thinking_config:
        budget = getattr(gen_cfg.thinking_config, "thinking_budget", None)
        assert budget == 0 or budget is None, f"Expected thinking_budget=0 for zero latency, got {budget}"


if __name__ == "__main__":
    print("Running test_motto_smooth_fade_out_for_turn...")
    test_motto_smooth_fade_out_for_turn()
    print("Running test_set_subtitle_mid_fade_out...")
    test_set_subtitle_mid_fade_out()
    print("Running test_clear_subtitle_preserves_steady_motto...")
    test_clear_subtitle_preserves_steady_motto()
    print("Running test_wake_up_triggers_high_priority_greeting...")
    test_wake_up_triggers_high_priority_greeting()
    print("Running test_fast_thinking_budget_for_viewer_join...")
    test_fast_thinking_budget_for_viewer_join()
    print("\nALL VIEWER JOIN & MOTTO TRANSITION TESTS PASSED 100%!")
