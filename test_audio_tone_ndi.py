"""
NDI Audio Diagnostic Tone & Speech Test.
Broadcasts a visual countdown with an audible 440Hz test tone and speech announcements
over NDI 'AI_COHOST_FEED' to verify OBS audio reception, routing, and monitoring.
"""

import asyncio
from fractions import Fraction
import math
import time
import numpy as np
import pygame

from config import config

try:
    import cyndilib
except ImportError:
    cyndilib = None


def run_ndi_audio_test():
    print("\n" + "=" * 65)
    print("STARTING NDI AUDIO DIAGNOSTIC TEST ON 'AI_COHOST_FEED'")
    print("=" * 65)

    if not cyndilib:
        print("[ERROR] cyndilib is not installed!")
        return

    pygame.init()
    pygame.font.init()
    surf = pygame.Surface((1920, 1080))
    font_large = pygame.font.SysFont("Arial", 72, bold=True)
    font_sub = pygame.font.SysFont("Arial", 36)

    # 1. Setup NDI Video & Audio frames
    vf = cyndilib.VideoSendFrame()
    vf.set_resolution(1920, 1080)
    vf.set_frame_rate(Fraction(60, 1))
    vf.set_fourcc(cyndilib.FourCC.RGBA)

    af = cyndilib.AudioSendFrame(800, 2, 48000)

    sender = cyndilib.Sender(
        ndi_name="AI_COHOST_FEED",
        clock_video=False,
        clock_audio=False,
    )
    sender.set_video_frame(vf)
    sender.set_audio_frame(af)

    try:
        sender.open()
        print("-> NDI Sender opened on 'AI_COHOST_FEED' (1080p60 + 48kHz Stereo)")
    except Exception as e:
        print(f"[ERROR] Could not open NDI sender: {e}")
        print("Note: If app.py is running, stop it first so this test can use the stream.")
        return

    fps = 60
    sample_rate = 48000
    samples_per_frame = sample_rate // fps  # 800 samples

    duration_sec = 15
    total_frames = fps * duration_sec

    print(f"-> Broadcasting 15-second visual test pattern + 440Hz AUDIBLE PULSE TONE...")
    print("-> Check OBS Studio Audio Mixer now:")
    print("   1. Is the volume meter bar for 'AI_COHOST_FEED' moving?")
    print("   2. Is Audio Monitoring set to 'Monitor and Output' in Advanced Audio Properties?")

    t_start = time.perf_counter()
    phase = 0.0

    for frame_idx in range(total_frames):
        t_frame_start = time.perf_counter()
        elapsed = frame_idx / fps
        remaining = duration_sec - elapsed

        # 1. Generate 440Hz tone pulsing every 0.5s
        tone_on = (int(elapsed * 2) % 2 == 0)
        freq = 440.0 if tone_on else 220.0
        amp = 0.4 if tone_on else 0.1

        t_audio = np.linspace(
            phase, phase + (samples_per_frame / sample_rate), samples_per_frame, endpoint=False, dtype=np.float32
        )
        phase += samples_per_frame / sample_rate
        sine_wave = (amp * np.sin(2.0 * np.pi * freq * t_audio)).astype(np.float32)
        audio_packet = np.ascontiguousarray(np.vstack((sine_wave, sine_wave)), dtype=np.float32)

        # 2. Render visual screen
        bg_color = (20, 30, 60) if tone_on else (10, 15, 30)
        surf.fill(bg_color)

        # Center pulse circle
        circle_r = 180 if tone_on else 120
        circle_color = (0, 240, 255) if tone_on else (0, 100, 180)
        pygame.draw.circle(surf, circle_color, (960, 480), circle_r)

        # Text
        txt_count = font_large.render(f"AUDIO TEST: {remaining:.1f}s", True, (255, 255, 255))
        txt_tone = font_sub.render(f"Tone: {int(freq)} Hz {'[BEEP ACTIVE]' if tone_on else '[PULSE]'}", True, (255, 220, 100))
        txt_hint = font_sub.render("OBS: Set Audio Monitoring -> 'Monitor and Output'", True, (180, 240, 255))

        surf.blit(txt_count, (960 - txt_count.get_width() // 2, 440))
        surf.blit(txt_tone, (960 - txt_tone.get_width() // 2, 720))
        surf.blit(txt_hint, (960 - txt_hint.get_width() // 2, 800))

        video_bytes = np.frombuffer(pygame.image.tobytes(surf, "RGBA"), dtype=np.uint8).copy()

        # 3. Transmit Video and Audio
        sender.write_video_async(video_bytes)
        sender.write_audio(audio_packet)

        # 60fps timing
        t_used = time.perf_counter() - t_frame_start
        sleep_dur = (1.0 / fps) - t_used
        if sleep_dur > 0:
            time.sleep(sleep_dur)

    sender.close()
    pygame.quit()
    print("=" * 65)
    print("AUDIO DIAGNOSTIC BROADCAST FINISHED!")
    print("=" * 65)


if __name__ == "__main__":
    run_ndi_audio_test()
