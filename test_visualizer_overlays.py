"""
Verification script for the new 'Ask God' and 'Like & Subscribe' graphic overlays.
Renders and exports frames to verify layout, colors, typography, and animation stages.
"""

import os
import pygame
import numpy as np
from visualizer import Visualizer
from config import config

def test_visualizer_promo_overlays():
    print("Initializing Visualizer in headless test mode...")
    config.visualizer_headless = True
    config.promo_overlay_enabled = True

    vis = Visualizer()

    # Sample data
    audio_metrics = {
        "rms": 0.12,
        "spectrum": np.random.uniform(0.1, 0.8, 32).astype(np.float32),
        "is_speaking": False,
    }
    chat_messages = [
        {"author": "CyberGamer", "message": "Can you explain the nature of reality?", "is_superchat": True, "amount": "$5.00"},
        {"author": "NeonFan", "message": "Loving the stream today!", "is_superchat": False, "amount": ""},
    ]
    host_transcript = "Welcome everyone to the broadcast! Ask any questions you have in chat."
    ai_subtitle = "I am ready to illuminate your consciousness and answer your inquiries."

    os.makedirs("test_output", exist_ok=True)

    # 1. Test "Ask God Your Questions Now!" overlay
    print("\n1. Testing 'Ask God Your Questions Now!' overlay...")
    vis.trigger_promo("ask_god", duration=10.0)

    # Step forward 0.6s to reach full display
    for _ in range(36):
        vis.render_frame(
            audio_metrics, chat_messages, host_transcript, ai_subtitle,
            host_connected=True, obs_connected=True, engagement_mode="active",
            concurrent_viewers=42, is_stream_live=True
        )

    # Save frame
    pygame.image.save(vis.screen, "test_output/ask_god_overlay.png")
    print("-> Saved: test_output/ask_god_overlay.png")

    # 2. Test "Like & Subscribe!" overlay
    print("\n2. Testing 'Like & Subscribe!' overlay...")
    vis.trigger_promo("like_sub", duration=10.0)

    for _ in range(36):
        vis.render_frame(
            audio_metrics, chat_messages, host_transcript, ai_subtitle,
            host_connected=True, obs_connected=True, engagement_mode="active",
            concurrent_viewers=42, is_stream_live=True
        )

    # Save frame
    pygame.image.save(vis.screen, "test_output/like_sub_overlay.png")
    print("-> Saved: test_output/like_sub_overlay.png")

    # 3. Test full cycle transitions (60 FPS simulation over 120 frames)
    print("\n3. Testing 60 FPS rendering cycle performance...")
    start_time = pygame.time.get_ticks()
    total_frames = 120
    for f in range(total_frames):
        buf = vis.render_frame(
            audio_metrics, chat_messages, host_transcript, ai_subtitle,
            host_connected=True, obs_connected=True, engagement_mode="active",
            concurrent_viewers=42, is_stream_live=True
        )
        assert len(buf) == 1920 * 1080 * 4, f"Invalid buffer length: {len(buf)}"

    elapsed_ms = pygame.time.get_ticks() - start_time
    fps = (total_frames / (elapsed_ms / 1000.0)) if elapsed_ms > 0 else 999.0
    print(f"-> Rendered {total_frames} frames in {elapsed_ms}ms ({fps:.1f} FPS)")
    print("\nALL PROMO OVERLAY VISUALIZER TESTS PASSED!")

if __name__ == "__main__":
    test_visualizer_promo_overlays()
