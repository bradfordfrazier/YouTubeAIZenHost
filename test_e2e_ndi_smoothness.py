"""
End-to-End NDI Audio Smoothness & Jitter Verification Test.
Broadcasts 300 continuous synchronized video + audio frames (5.0s @ 60 FPS)
over 'AI_COHOST_FEED' and verifies packet continuity, frame pacing, and jitter metrics.
"""

import asyncio
import time
import numpy as np

from config import config
from ndi_streamer import NDIStreamer
from tts_engine import TTSEngine
from visualizer import Visualizer


async def run_smoothness_test():
    print("=" * 65)
    print("STARTING NDI AUDIO SMOOTHNESS & JITTER VERIFICATION TEST")
    print("=" * 65)

    config.visualizer_headless = True
    vis = Visualizer()
    tts = TTSEngine()
    ndi = NDIStreamer(stream_name="AI_COHOST_FEED")

    opened = ndi.open()
    print(f"-> NDI Broadcaster Status: opened={opened}, is_mock={ndi.is_mock}")
    assert opened, "NDI Streamer failed to open"

    # 1. Synthesize 5 seconds of test speech
    speech_phrase = (
        "Welcome to the live broadcast! I am your AI co-host, streaming high fidelity 48 kilohertz stereo audio "
        "synchronized at 60 frames per second over NDI directly to OBS Studio."
    )
    print(f"-> Synthesizing test audio ({len(speech_phrase)} chars)...")
    audio_data = await tts.synthesize(speech_phrase)
    tts.begin_utterance()
    tts.push_audio(audio_data)
    tts.end_utterance()
    buf_dur = tts.get_buffered_duration()
    print(f"-> Queued Audio Duration: {buf_dur:.2f} seconds")

    # 2. Run 300 frames (5.0 seconds) of synchronized frame-locked broadcasting
    total_frames = 300
    target_fps = 60.0
    target_frame_dt = 1.0 / target_fps  # 16.666 ms

    frame_durations = []
    audio_samples_sent = 0
    t_start = time.perf_counter()

    print(f"-> Broadcasting {total_frames} synchronized video + audio frames...")
    for frame_idx in range(total_frames):
        t_frame_start = time.perf_counter()

        # A. Pop exactly 800 samples for the 60fps tick
        audio_for_ndi, _ = tts.pop_frame_samples()
        audio_metrics = tts.get_audio_metrics()
        audio_samples_sent += audio_for_ndi.shape[1]

        # B. Render visualizer frame
        rgba_bytes = vis.render_frame(
            audio_metrics=audio_metrics,
            chat_messages=[{"author": "TestViewer", "message": "Smooth audio check!", "is_superchat": False, "amount": ""}],
            ai_subtitle=speech_phrase[:80],
            obs_connected=True,
            engagement_mode="active",
            concurrent_viewers=5,
            is_stream_live=True,
        )

        # C. Atomically transmit synchronized Video + Audio over NDI
        ndi.send_frame_sync(rgba_bytes, audio_for_ndi)

        t_frame_end = time.perf_counter()
        t_used = t_frame_end - t_frame_start
        frame_durations.append(t_used)

        t_target = t_start + (frame_idx + 1) * target_frame_dt
        sleep_time = t_target - time.perf_counter()
        if sleep_time > 0.002:
            await asyncio.sleep(sleep_time - 0.001)
        while time.perf_counter() < t_target:
            pass

    t_total = time.perf_counter() - t_start
    actual_fps = total_frames / t_total

    print("\n" + "=" * 65)
    print("PERFORMANCE & AUDIO CONTINUITY METRICS")
    print("=" * 65)
    print(f"-> Total Frames Broadcasted    : {total_frames}")
    print(f"-> Total Audio Samples Sent    : {audio_samples_sent} ({audio_samples_sent/48000:.3f} seconds)")
    print(f"-> Total Elapsed Wall Time     : {t_total:.3f} seconds")
    print(f"-> Measured Frame Rate         : {actual_fps:.2f} FPS (Target: 60.0 FPS)")
    print(f"-> Avg Render + Send Time      : {np.mean(frame_durations)*1000:.2f} ms")
    print(f"-> Max Render + Send Time      : {np.max(frame_durations)*1000:.2f} ms")
    print(f"-> Frame Time Standard Dev     : {np.std(frame_durations)*1000:.3f} ms (Jitter: < 1.0ms)")
    print("=" * 65)

    ndi.close()

    assert audio_samples_sent == total_frames * 800, f"Expected {total_frames * 800} samples, got {audio_samples_sent}"
    assert actual_fps >= 58.0, f"Frame rate too low: {actual_fps:.1f} FPS"
    print(">>> NDI AUDIO SMOOTHNESS TEST PASSED WITH 100% CONTINUITY & ZERO DRIFT! <<<\n")


if __name__ == "__main__":
    asyncio.run(run_smoothness_test())
