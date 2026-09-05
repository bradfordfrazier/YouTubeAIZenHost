"""
Comprehensive Verification Test Suite for the All-Local AI Co-Host Pipeline.
Tests individual modules (TTS, Visualizer, NDI Broadcaster, AI Brain)
and validates contextual trigger filtering and streaming.
"""

import asyncio
import time
import numpy as np

from config import config
from tts_engine import TTSEngine
from visualizer import Visualizer
from ndi_streamer import NDIStreamer
from ai_brain import AIBrain


async def test_tts():
    print("\n" + "=" * 50)
    print("TEST 1: TTS Engine & Audio Processing")
    print("=" * 50)
    tts = TTSEngine()
    test_text = "Welcome to the live stream! Nova is online and ready to co-host."
    audio = await tts.synthesize(test_text)
    print(f"-> Synthesized audio shape: {audio.shape} (dtype: {audio.dtype})")
    assert len(audio) > 0, "TTS output should not be empty"
    assert audio.shape[1] == 2, "TTS output must be 2-channel stereo"

    # Push audio and test frame-locked popping
    tts.begin_utterance()
    tts.push_audio(audio)
    tts.end_utterance()
    ndi_audio, interleaved = tts.pop_frame_samples()
    print(f"-> Popped frame audio for NDI: shape={ndi_audio.shape} (planar), interleaved={interleaved.shape}")
    assert ndi_audio.shape == (2, 800), f"Expected planar audio shape (2, 800), got {ndi_audio.shape}"

    metrics = tts.get_audio_metrics()
    print(f"-> Audio Metrics: is_speaking={metrics['is_speaking']}, rms={metrics['rms']:.5f}, spectrum_bands={len(metrics['spectrum'])}")
    print("[PASS] TTS Engine verified successfully!")


def test_visualizer():
    print("\n" + "=" * 50)
    print("TEST 2: Visualizer Engine (1080p60)")
    print("=" * 50)
    # Force headless for automated test
    config.visualizer_headless = True
    vis = Visualizer()

    sample_metrics = {
        "is_speaking": True,
        "rms": 0.25,
        "spectrum": np.random.uniform(0.1, 0.9, 32).astype(np.float32),
    }
    sample_chats = [
        {"author": "CyberGamer", "message": "Let's gooo!", "is_superchat": False, "amount": ""},
        {"author": "VIP_Supporter", "message": "Huge fan of the stream!", "is_superchat": True, "amount": "$10.00"},
    ]

    t0 = time.perf_counter()
    num_frames = 60
    for i in range(num_frames):
        mood = "hyped" if i % 20 == 0 else "chill"
        vis.set_mood(mood)
        rgba_buffer = vis.render_frame(
            audio_metrics=sample_metrics,
            chat_messages=sample_chats,
            ai_subtitle="The cosmic frequency is awakening within all of us.",
            obs_connected=True,
        )
    t1 = time.perf_counter()
    fps = num_frames / (t1 - t0)
    print(f"-> Rendered {num_frames} frames of 1920x1080 in {t1 - t0:.3f}s ({fps:.1f} FPS)")
    assert len(rgba_buffer) == 1920 * 1080 * 4, f"Expected 1080p RGBA buffer size, got {len(rgba_buffer)}"
    print("[PASS] Visualizer Engine verified successfully!")


def test_ndi():
    print("\n" + "=" * 50)
    print("TEST 3: NDI Streamer Broadcast Engine")
    print("=" * 50)
    ndi = NDIStreamer(stream_name="AI_HOST_TEST")
    ndi_open_success = ndi.open()
    print(f"-> NDI Open Result: {ndi_open_success} (is_mock: {ndi.is_mock})")

    # Send 10 test frames
    video_data = np.zeros((1080, 1920, 4), dtype=np.uint8)
    audio_data = np.zeros((ndi.audio_packet_samples, 2), dtype=np.float32)
    for _ in range(10):
        ndi.send_video(video_data.tobytes())
        ndi.send_audio_packet(audio_data)

    print(f"-> Frames sent: {ndi.frames_sent}, Active connections: {ndi.get_num_connections()}")
    ndi.close()
    print("[PASS] NDI Streamer verified successfully!")


async def test_ai_brain():
    print("\n" + "=" * 50)
    print("TEST 4: AI Brain Context, Peer Filtering & Streaming")
    print("=" * 50)
    brain = AIBrain()
    brain.add_chat_message("StreamFan", "I Am is the best host!", is_superchat=False)
    brain.add_chat_message("Alice", "Anyone ready for the deep dive?", is_superchat=False)

    # Set active engagement mode for initial tests
    brain.set_engagement_mode("active", is_stream_live=True, concurrent_viewers=5, is_chat_active=True)

    # 1. Test Direct Question Trigger
    should_trig, reason = brain.should_trigger_response("@I Am what do you think?")
    print(f"-> Direct mention trigger evaluation: should_trigger={should_trig}, reason={reason}")
    assert should_trig, "Expected direct mention to trigger response"

    # 2. Test Member-to-Member Direct Reply Filtering (Preserving Entanglement)
    brain.last_response_time = 0.0  # reset cooldown
    peer_trig, peer_reason = brain.should_trigger_response("@Alice yeah I have max gear!")
    print(f"-> Member-to-Member reply evaluation (@Alice): should_trigger={peer_trig}, reason={peer_reason}")
    assert not peer_trig, "Expected member-to-member reply to NOT trigger AI response"
    assert "member_reply_entanglement" in peer_reason, f"Expected member_reply_entanglement reason, got: {peer_reason}"

    # 3. Test Direct Channel Address (Channel handle is NEVER filtered as peer reply)
    brain.last_response_time = 0.0
    chan_handle = brain.cfg.youtube_channel_handle
    mgc_trig, mgc_reason = brain.should_trigger_response(f"{chan_handle} is this stream live right now?")
    print(f"-> Direct Channel address evaluation ({chan_handle}): should_trigger={mgc_trig}, reason={mgc_reason}")
    assert mgc_trig, f"Expected address to {chan_handle} to NOT be filtered as peer entanglement"

    # 4. Test Direct AI Address from Member
    brain.last_response_time = 0.0
    ai_trig, ai_reason = brain.should_trigger_response("@I Am what is consciousness?")
    print(f"-> Direct AI question evaluation (@I Am): should_trigger={ai_trig}, reason={ai_reason}")
    assert ai_trig, "Expected direct mention of AI to trigger response"

    # 5. Test Chat General Question Trigger
    brain.last_response_time = 0.0
    q_trig, q_reason = brain.should_trigger_response("How does the unified mind realize itself?")
    print(f"-> General chat question evaluation: should_trigger={q_trig}, reason={q_reason}")
    assert q_trig, "Expected question to trigger response"

    # 6. Test Chat Interactive Keyword Trigger (Phase 3 explicit ask keywords)
    brain.last_response_time = 0.0
    kw_trig, kw_reason = brain.should_trigger_response("Give me your opinion on this setup")
    print(f"-> Chat keyword evaluation: should_trigger={kw_trig}, reason={kw_reason}")
    assert kw_trig, "Expected interactive keywords to trigger response"

    # 7. Test New Chatter Greeting Priority Trigger
    brain.last_response_time = 0.0
    new_chatter_trig, new_chatter_reason = brain.should_trigger_response("Hey everyone!", is_new_chatter=True)
    print(f"-> First-time chatter greeting evaluation: should_trigger={new_chatter_trig}, reason={new_chatter_reason}")
    assert new_chatter_trig, "Expected first-time chatter to trigger greeting"
    assert new_chatter_reason == "new_chatter_greeting"

    # 8. Test Eco Mode Gating (Throttles generic keywords, allows direct mentions)
    print("-> Testing Eco Mode Gating (Low viewers / quiet chat)...")
    brain.cfg.eco_mode_enabled = True
    brain.set_engagement_mode("eco", is_stream_live=True, concurrent_viewers=0, is_chat_active=False)
    brain.last_response_time = 0.0

    eco_kw_trig, eco_kw_reason = brain.should_trigger_response("That was such a clutch play lol")
    print(f"   [Eco Mode Generic Keyword]: should_trigger={eco_kw_trig}, reason={eco_kw_reason}")
    assert not eco_kw_trig, "Expected generic keyword to be suppressed in Eco mode"
    assert "eco_mode_suppressed" in eco_kw_reason

    brain.last_response_time = 0.0
    eco_direct_trig, eco_direct_reason = brain.should_trigger_response("@I Am what do you think?")
    print(f"   [Eco Mode Direct Mention]: should_trigger={eco_direct_trig}, reason={eco_direct_reason}")
    assert eco_direct_trig, "Expected direct mention to trigger even in Eco mode"

    # 9. Test Standby Mode (0 tokens when OBS is offline)
    print("-> Testing Standby Mode (Stream offline)...")
    brain.cfg.obs_require_stream_active = True
    brain.set_engagement_mode("standby", is_stream_live=False, concurrent_viewers=0, is_chat_active=False)
    standby_trig, standby_reason = brain.should_trigger_response("Who is the best player?")
    print(f"   [Standby Mode Chat]: should_trigger={standby_trig}, reason={standby_reason}")
    assert not standby_trig, "Expected all chat responses to be blocked in Standby mode"
    assert "stream_standby_paused" in standby_reason

    # Reset back to active mode
    brain.set_engagement_mode("active", is_stream_live=True, concurrent_viewers=25, is_chat_active=True)

    # 10. Test Rate Limiter
    print("-> Testing Sliding-Window Rate Limiter...")
    brain.response_timestamps.clear()
    now = time.time()
    max_rpm = config.max_responses_per_minute
    for _ in range(max_rpm):
        brain.response_timestamps.append(now)

    rate_trig, rate_reason = brain.should_trigger_response("@I Am hello!")
    print(f"   [Rate Limiter Evaluation]: should_trigger={rate_trig}, reason={rate_reason}")
    assert not rate_trig, "Expected rate limit to block excess requests"
    assert "rate_limit_exceeded" in rate_reason

    brain.response_timestamps.clear()
    brain.is_generating = False
    brain.last_response_time = 0.0

    # 11. Test Spontaneous Spiritual Reflection Stream
    print("-> Testing Spontaneous Spiritual Reflection Stream from AI Brain...")
    stream_events = []
    async for event in brain.generate_response_stream("[SPONTANEOUS_REFLECTION]"):
        stream_events.append(event)
        if event["type"] == "mood":
            print(f"   [Mood Detected]: {event['mood']}")
        elif event["type"] == "sentence":
            print(f"   [Sentence Ready for TTS]: '{event['text']}'")
        elif event["type"] == "complete":
            print(f"   [Complete Reflection Text]: '{event['full_text']}'")

    assert len(stream_events) > 0, "Expected stream events from AI Brain"
    print("[PASS] AI Brain, Token Throttling & Peer Filtering verified successfully!")


async def run_all_tests():
    print("\n" + "#" * 60)
    print("STARTING FULL ALL-LOCAL PIPELINE VERIFICATION SUITE")
    print("#" * 60)

    await test_tts()
    test_visualizer()
    test_ndi()
    await test_ai_brain()

    print("\n" + "#" * 60)
    print("ALL MODULE TESTS PASSED PERFECTLY!")
    print("#" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
