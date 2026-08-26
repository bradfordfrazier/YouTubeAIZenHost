"""
Test script verifying resizable desktop window and internal NDI resolution preservation.
"""
import os
import pygame
import numpy as np
from visualizer import Visualizer
from config import config

def test_resizable_window():
    # Set non-headless
    config.visualizer_headless = False
    config.visualizer_aspect_ratio = "9:16"

    # In non-headless mode, SDL requires video driver
    # Test on local desktop
    try:
        vis = Visualizer(width=1080, height=1920)
        assert vis.window_size == (540, 960), f"Expected initial window size (540, 960), got {vis.window_size}"

        audio_metrics = {"rms": 0.15, "spectrum": np.zeros(32, dtype=np.float32), "is_speaking": False}

        # Render initial frame
        buf = vis.render_frame(audio_metrics, [], "", "")
        assert len(buf) == 1080 * 1920 * 4, f"Buffer size mismatch: {len(buf)}"

        # Simulate user resizing window to (360, 640)
        event = pygame.event.Event(pygame.VIDEORESIZE, {"w": 360, "h": 640, "size": (360, 640)})
        pygame.event.post(event)

        # Render next frame
        buf_resized = vis.render_frame(audio_metrics, [], "", "")
        assert vis.window_size == (360, 640), f"Expected window size (360, 640), got {vis.window_size}"
        assert len(buf_resized) == 1080 * 1920 * 4, "NDI buffer must remain full 1080x1920 regardless of desktop window size!"

        print("-> Resizable desktop container test passed successfully!")

        # Test Native Window Mode
        config.visualizer_native_window = True
        vis_native = Visualizer(width=1080, height=1920)
        assert vis_native.window_size == (1080, 1920), f"Expected native window (1080, 1920), got {vis_native.window_size}"
        print("-> Native 1080x1920 window mode test passed successfully!")
    except pygame.error as e:
        print(f"-> Pygame display not available in environment: {e}")

if __name__ == "__main__":
    test_resizable_window()
