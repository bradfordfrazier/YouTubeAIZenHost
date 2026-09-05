"""
Test script to verify the smooth transition between speaking (between-words) state and default state in Visualizer.
"""

import math
import numpy as np
from visualizer import Visualizer
from config import config

def test_speech_transition_smoothness():
    config.visualizer_headless = True
    vis = Visualizer()

    spectrum = np.zeros(32, dtype=np.float32)
    chat_messages = []
    ai_subtitle = ""

    flare_lens = []
    outer_radii = []
    singularity_radii = []
    speech_intensities = []

    # 1. Idle state for 30 frames
    for f in range(30):
        audio_metrics = {"rms": 0.0, "spectrum": spectrum, "is_speaking": False}
        vis.render_frame(audio_metrics, chat_messages, ai_subtitle)
        speech_intensities.append(vis.speech_intensity)

    assert vis.speech_intensity < 0.01, f"Expected idle speech_intensity ~0, got {vis.speech_intensity}"

    # 2. Speaking on words for 30 frames (rms = 0.15, is_speaking = True)
    for f in range(30):
        audio_metrics = {"rms": 0.15, "spectrum": spectrum, "is_speaking": True}
        vis.render_frame(audio_metrics, chat_messages, ai_subtitle)
        speech_intensities.append(vis.speech_intensity)

    assert vis.speech_intensity > 0.95, f"Expected active speech_intensity > 0.95, got {vis.speech_intensity}"

    # 3. Speaking in-between words for 20 frames (rms = 0.0, is_speaking = True)
    for f in range(20):
        audio_metrics = {"rms": 0.0, "spectrum": spectrum, "is_speaking": True}
        vis.render_frame(audio_metrics, chat_messages, ai_subtitle)
        speech_intensities.append(vis.speech_intensity)

    assert vis.speech_intensity > 0.95, f"Expected between-words speech_intensity to stay high, got {vis.speech_intensity}"

    # 4. Speech finished - transition back to default state (rms = 0.0, is_speaking = False)
    decay_intensities = []
    for f in range(60):
        audio_metrics = {"rms": 0.0, "spectrum": spectrum, "is_speaking": False}
        vis.render_frame(audio_metrics, chat_messages, ai_subtitle)
        speech_intensities.append(vis.speech_intensity)
        decay_intensities.append(vis.speech_intensity)

    # Verify smooth monotonic decay
    for i in range(1, len(decay_intensities)):
        diff = decay_intensities[i] - decay_intensities[i - 1]
        assert diff <= 0.001, f"Non-monotonic decay at frame {i}: {decay_intensities[i-1]} -> {decay_intensities[i]}"
        # Max drop per frame at 60fps should be smooth (less than 0.10)
        assert abs(diff) < 0.10, f"Discontinuous jump at frame {i}: step size {abs(diff)}"

    # After 60 frames (~1.0s), intensity should be back near 0
    final_intensity = decay_intensities[-1]
    assert final_intensity < 0.05, f"Expected near-zero intensity after 1s decay, got {final_intensity}"

    print(f"[OK] Smooth transition test passed successfully!")
    print(f"  - Peak speaking intensity: {speech_intensities[59]:.3f}")
    print(f"  - In-between words intensity: {speech_intensities[79]:.3f}")
    print(f"  - Post-speech 10 frames (166ms) decay: {decay_intensities[9]:.3f}")
    print(f"  - Post-speech 30 frames (500ms) decay: {decay_intensities[29]:.3f}")
    print(f"  - Post-speech 60 frames (1.0s) decay: {decay_intensities[59]:.3f}")

if __name__ == "__main__":
    test_speech_transition_smoothness()
