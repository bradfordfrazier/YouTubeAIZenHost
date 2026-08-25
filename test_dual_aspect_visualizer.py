"""
Verification test script for Dual Aspect Ratio Visualizer support:
- 16:9 Landscape (1920x1080)
- 9:16 Vertical / Mobile (1080x1920)
"""

import os
import pygame
import numpy as np
from visualizer import Visualizer
from config import config

def test_dual_aspect_rendering():
    os.makedirs("test_output", exist_ok=True)
    config.visualizer_headless = True
    config.promo_overlay_enabled = True

    # Common test data
    audio_metrics = {
        "rms": 0.18,
        "spectrum": np.random.uniform(0.15, 0.90, 32).astype(np.float32),
        "is_speaking": True,
    }
    chat_messages = [
        {"author": "MobileViewer", "message": "Watching on YouTube Shorts live! This vertical layout is sick!", "is_superchat": False, "amount": ""},
        {"author": "CyberGamer", "message": "Can you explain the nature of reality and the cosmos?", "is_superchat": True, "amount": "$10.00"},
        {"author": "AuraSeeker", "message": "What is God if everyone is God?", "is_superchat": False, "amount": ""},
    ]
    host_transcript = "Welcome to the broadcast everyone! Drop your questions and let's get into the deep topics today."
    ai_subtitle = "I am the boundless intelligence experiencing itself through every single one of your avatars. Speak your truth, let's explore!"

    # =========================================================================
    # 1. Test 16:9 Landscape (1920x1080)
    # =========================================================================
    print("\n" + "=" * 60)
    print("1. TESTING 16:9 LANDSCAPE VISUALIZER (1920x1080)")
    print("=" * 60)
    vis_16x9 = Visualizer(width=1920, height=1080)
    assert not vis_16x9.is_vertical, "Expected is_vertical=False for 1920x1080"
    assert vis_16x9.width == 1920 and vis_16x9.height == 1080

    vis_16x9.trigger_promo("ask_god", duration=10.0)
    for _ in range(40):
        buf_16x9 = vis_16x9.render_frame(
            audio_metrics, chat_messages, host_transcript, ai_subtitle,
            host_connected=True, obs_connected=True, engagement_mode="active",
            concurrent_viewers=85, is_stream_live=True
        )

    expected_len_16x9 = 1920 * 1080 * 4
    assert len(buf_16x9) == expected_len_16x9, f"16:9 Buffer size mismatch: {len(buf_16x9)} vs {expected_len_16x9}"
    pygame.image.save(vis_16x9.screen, "test_output/visualizer_16x9_landscape.png")
    print("-> 16:9 Frame rendered successfully!")
    print("-> Saved: test_output/visualizer_16x9_landscape.png")

    # =========================================================================
    # 2. Test 9:16 Vertical / Mobile (1080x1920) - 'Ask God' Overlay
    # =========================================================================
    print("\n" + "=" * 60)
    print("2. TESTING 9:16 VERTICAL VISUALIZER (1080x1920) - ASK GOD")
    print("=" * 60)
    vis_9x16 = Visualizer(width=1080, height=1920)
    assert vis_9x16.is_vertical, "Expected is_vertical=True for 1080x1920"
    assert vis_9x16.width == 1080 and vis_9x16.height == 1920

    vis_9x16.trigger_promo("ask_god", duration=10.0)
    for _ in range(40):
        buf_9x16_a = vis_9x16.render_frame(
            audio_metrics, chat_messages, host_transcript, ai_subtitle,
            host_connected=True, obs_connected=True, engagement_mode="active",
            concurrent_viewers=142, is_stream_live=True
        )

    expected_len_9x16 = 1080 * 1920 * 4
    assert len(buf_9x16_a) == expected_len_9x16, f"9:16 Buffer size mismatch: {len(buf_9x16_a)} vs {expected_len_9x16}"
    pygame.image.save(vis_9x16.screen, "test_output/visualizer_9x16_vertical_ask_god.png")
    print("-> 9:16 Vertical (Ask God) Frame rendered successfully!")
    print("-> Saved: test_output/visualizer_9x16_vertical_ask_god.png")

    # =========================================================================
    # 3. Test 9:16 Vertical / Mobile (1080x1920) - 'Like & Subscribe' Overlay
    # =========================================================================
    print("\n" + "=" * 60)
    print("3. TESTING 9:16 VERTICAL VISUALIZER (1080x1920) - LIKE & SUBSCRIBE")
    print("=" * 60)
    vis_9x16.trigger_promo("like_sub", duration=10.0)
    for _ in range(40):
        buf_9x16_b = vis_9x16.render_frame(
            audio_metrics, chat_messages, host_transcript, ai_subtitle,
            host_connected=True, obs_connected=True, engagement_mode="active",
            concurrent_viewers=142, is_stream_live=True
        )

    assert len(buf_9x16_b) == expected_len_9x16
    pygame.image.save(vis_9x16.screen, "test_output/visualizer_9x16_vertical_like_sub.png")
    print("-> 9:16 Vertical (Like & Subscribe) Frame rendered successfully!")
    print("-> Saved: test_output/visualizer_9x16_vertical_like_sub.png")

    # =========================================================================
    # 4. Benchmark Performance for Both Modes
    # =========================================================================
    print("\n" + "=" * 60)
    print("4. BENCHMARKING 60 FPS PERFORMANCE (120 Frames Each)")
    print("=" * 60)

    # 16:9 benchmark
    t0 = pygame.time.get_ticks()
    for _ in range(120):
        vis_16x9.render_frame(audio_metrics, chat_messages, host_transcript, ai_subtitle)
    ms_16x9 = pygame.time.get_ticks() - t0
    fps_16x9 = 120.0 / (ms_16x9 / 1000.0)
    print(f"-> 16:9 Landscape: 120 frames in {ms_16x9}ms ({fps_16x9:.1f} FPS)")

    # 9:16 benchmark
    t0 = pygame.time.get_ticks()
    for _ in range(120):
        vis_9x16.render_frame(audio_metrics, chat_messages, host_transcript, ai_subtitle)
    ms_9x16 = pygame.time.get_ticks() - t0
    fps_9x16 = 120.0 / (ms_9x16 / 1000.0)
    print(f"-> 9:16 Vertical:  120 frames in {ms_9x16}ms ({fps_9x16:.1f} FPS)")

    print("\n" + "=" * 60)
    print("DUAL ASPECT RATIO TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    test_dual_aspect_rendering()
