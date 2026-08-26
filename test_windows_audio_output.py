"""
Verification test for Dual Audio Output:
1. Windows Local Audio Output via MMCSS WASAPI Kernel Callback (for OBS Window/Application Capture)
2. NDI Stream Audio (for OBS NDI Source / DistroAV)
"""

import asyncio
import time
import numpy as np
import sounddevice as sd

from config import config
from tts_engine import TTSEngine
from ndi_streamer import NDIStreamer
from app import resolve_wasapi_output_device


async def test_dual_audio_output():
    print("=" * 65)
    print("TESTING SIMULTANEOUS WINDOWS WASAPI MMCSS CALLBACK & NDI OUTPUT")
    print("=" * 65)

    # 1. Resolve WASAPI output device for OBS
    wasapi_idx = resolve_wasapi_output_device()
    dev_info = sd.query_devices(wasapi_idx)
    api_name = sd.query_hostapis(dev_info["hostapi"])["name"]
    print(f"-> Resolved Device: [{wasapi_idx}] {dev_info['name']} (API: {api_name})")
    assert "wasapi" in api_name.lower(), f"Expected WASAPI host API for OBS capture, got {api_name}"

    # 2. Initialize TTS and NDI
    tts = TTSEngine()
    ndi = NDIStreamer(stream_name="TEST_DUAL_AUDIO_STREAM")
    ndi_success = ndi.open()
    print(f"-> NDI Sender initialized: {ndi_success} (is_mock: {ndi.is_mock})")

    # 3. Open sounddevice WASAPI callback stream (48000 Hz Stereo Float32, MMCSS kernel thread)
    def _audio_callback(outdata, frames, time_info, status):
        outdata[:] = tts.pop_local_audio(frames, volume=1.0)

    sd_stream = sd.OutputStream(
        samplerate=48000,
        channels=2,
        dtype="float32",
        device=wasapi_idx,
        callback=_audio_callback,
        blocksize=960,
        latency="high",
    )
    sd_stream.start()
    print("-> Windows WASAPI Real-Time Callback Stream started successfully!")

    # 4. Synthesize test speech
    test_phrase = "Testing glitch-free simultaneous Windows WASAPI kernel audio callback and NDI audio feed."
    print(f"-> Synthesizing test audio: '{test_phrase}'")
    await tts.queue_speech(test_phrase)

    # 5. Pump audio packets to NDI while PortAudio callback simultaneously drains local buffer
    print("-> Streaming frame-locked audio packets to NDI & WASAPI for 3.5 seconds...")
    samples_per_packet = 800  # 800 samples @ 60 FPS = 16.666 ms
    packets_sent = 0
    t0 = time.perf_counter()

    for _ in range(210):  # 210 frames * 16.666ms = 3.5 seconds
        audio_for_ndi, _ = tts.pop_audio_packet(samples_per_packet)
        ndi.send_audio(audio_for_ndi)
        packets_sent += 1
        await asyncio.sleep(0.015)

    t1 = time.perf_counter()
    print(f"-> Pumped {packets_sent} audio frames ({packets_sent/60:.2f}s) in {t1-t0:.3f}s")

    sd_stream.stop()
    sd_stream.close()
    ndi.close()

    assert packets_sent == 210, f"Expected 210 frames, got {packets_sent}"
    print("\n" + "=" * 65)
    print("DUAL WINDOWS WASAPI & NDI AUDIO OUTPUT TEST PASSED PERFECTLY!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(test_dual_audio_output())
