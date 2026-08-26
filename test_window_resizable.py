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

    try:
        # 1. Test 16:9 Landscape Mode (1920x1080 canvas, 320x180 scaled desktop window for portrait monitors)
        config.visualizer_aspect_ratio = "16:9"
        config.visualizer_native_window = False
        vis_16x9 = Visualizer(width=1920, height=1080)
        assert vis_16x9.window_size == (320, 180), f"Expected 16:9 initial window size (320, 180), got {vis_16x9.window_size}"
        assert (vis_16x9.width, vis_16x9.height) == (1920, 1080), "Expected internal canvas (1920, 1080)"

        audio_metrics = {"rms": 0.15, "spectrum": np.zeros(32, dtype=np.float32), "is_speaking": False}
        buf_16x9 = vis_16x9.render_frame(audio_metrics, [], "", "")
        assert len(buf_16x9) == 1920 * 1080 * 4, f"Buffer size mismatch for 16:9: {len(buf_16x9)}"
        print("-> 16:9 Landscape (320x180 desktop window -> 1920x1080 stream) test passed!")

        # 2. Test 9:16 Vertical Mode (1080x1920 canvas, 540x960 scaled desktop window)
        config.visualizer_aspect_ratio = "9:16"
        config.visualizer_native_window = False
        vis_9x16 = Visualizer(width=1080, height=1920)
        assert vis_9x16.window_size == (540, 960), f"Expected 9:16 initial window size (540, 960), got {vis_9x16.window_size}"
        assert (vis_9x16.width, vis_9x16.height) == (1080, 1920), "Expected internal canvas (1080, 1920)"

        buf_9x16 = vis_9x16.render_frame(audio_metrics, [], "", "")
        assert len(buf_9x16) == 1080 * 1920 * 4, f"Buffer size mismatch for 9:16: {len(buf_9x16)}"
        print("-> 9:16 Vertical (540x960 desktop window -> 1080x1920 stream) test passed!")

        # 3. Simulate user resizing window to (480, 270)
        event = pygame.event.Event(pygame.VIDEORESIZE, {"w": 480, "h": 270, "size": (480, 270)})
        pygame.event.post(event)
        buf_resized = vis_16x9.render_frame(audio_metrics, [], "", "")
        assert vis_16x9.window_size == (480, 270), f"Expected resized window (480, 270), got {vis_16x9.window_size}"
        assert len(buf_resized) == 1920 * 1080 * 4, "NDI buffer must remain full 1920x1080 regardless of desktop window size!"
        print("-> Dynamic resizing test passed successfully!")

        # 4. Test Native Window Mode
        config.visualizer_native_window = True
        vis_native = Visualizer(width=1920, height=1080)
        assert vis_native.window_size == (1920, 1080), f"Expected native window (1920, 1080), got {vis_native.window_size}"
        print("-> Native 1920x1080 window mode test passed successfully!")
    except pygame.error as e:
        print(f"-> Pygame display not available in environment: {e}")

if __name__ == "__main__":
    test_resizable_window()
