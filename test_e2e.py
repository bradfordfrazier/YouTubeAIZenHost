"""
End-to-End All-Local In-Memory Integration Test.
Runs LocalCoHostApp in-process on the OBS Host machine,
simulates live speech transcripts, YouTube chat, and OBS events,
and validates complete in-memory pipeline flow to TTS, Visualizer, and NDI broadcast.
"""

import asyncio
import time

from config import config
from app import LocalCoHostApp


async def run_e2e_test():
    print("\n" + "=" * 65)
    print("STARTING ALL-LOCAL SINGLE-PC END-TO-END SIMULATION TEST")
    print("=" * 65)

    config.visualizer_headless = True
    config.mock_chat_enabled = False

    app = LocalCoHostApp()
    app.running = True
    app.loop = asyncio.get_running_loop()

    # Open NDI Streamer
    app.ndi.open()

    # Start 60fps video task and audio pump thread
    import threading
    app.ndi_audio_running = True
    app.ndi_audio_thread = threading.Thread(
        target=app._ndi_audio_pump_worker,
        name="NDI_Audio_Pump_Thread",
        daemon=True,
    )
    app.ndi_audio_thread.start()

    video_task = asyncio.create_task(app.video_broadcast_task(), name="video_broadcaster")
    scheduler_task = asyncio.create_task(app.comment_queue_scheduler_task(), name="comment_scheduler")

    await asyncio.sleep(0.5)
    print("-> All-Local AI Co-Host running with 60 FPS Visualizer & NDI Broadcaster")

    # 1. Simulate initial stream state (Live with 0 Viewers -> ECO Mode)
    print("-> [Step 1: Broadcast Live with 0 Viewers -> Setting ECO Mode]")
    app.is_streaming = True
    app.current_scene = "Main"
    app._on_viewer_count_update(0, 0)
    await asyncio.sleep(0.5)
    assert app.engagement_mode == "eco", f"Expected eco mode on 0 viewers, got {app.engagement_mode}"
    print(f"   Mode: {app.engagement_mode.upper()} | Viewers: {app.concurrent_viewers}")

    # 2. Simulate viewer joining (0 -> 2 Viewers: transitions to ACTIVE mode)
    print("-> [Step 2: Audience Arrival -> 2 Viewers Connected -> Transition to ACTIVE Mode]")
    app._on_viewer_count_update(2, 1)
    await asyncio.sleep(0.5)
    assert app.engagement_mode == "active", f"Expected active mode, got {app.engagement_mode}"
    print(f"   Mode: {app.engagement_mode.upper()} | Viewers: {app.concurrent_viewers}")

    # 3. Simulate Host Speech Transcript
    print("-> [Step 3: Host Speech -> 'Nova, what do you think about our new single PC setup?']")
    host_text = "Nova, what do you think about our new single PC setup?"
    app.current_host_transcript = host_text
    app.brain.add_transcript("Host", host_text)
    should_trig, reason = app.brain.should_trigger_response(host_text, is_host=True)
    if should_trig:
        app._trigger_ai_turn(prompt_trigger=f"Host said: '{host_text}'")
    await asyncio.sleep(2.0)

    # 4. Simulate Live Chat Comment
    print("-> [Step 4: Viewer Chat -> @CyberGamer: 'Nova is crushing it!']")
    chat_msg = "Nova is crushing it!"
    app.chat_history.append({"author": "CyberGamer", "message": chat_msg, "is_superchat": False, "amount": "", "timestamp": time.time()})
    app.brain.add_chat_message("CyberGamer", chat_msg, False, "")
    should_trig, reason = app.brain.should_trigger_response(chat_msg, is_host=False)
    if should_trig:
        app._trigger_ai_turn(prompt_trigger=f"Chat message from @CyberGamer: '{chat_msg}'")
    await asyncio.sleep(2.0)

    # 5. Simulate Superchat
    print("-> [Step 5: Superchat -> @VIP_Supporter ($20.00): 'Hyped for tonight's broadcast!!']")
    sc_msg = "Hyped for tonight's broadcast!!"
    app.chat_history.append({"author": "VIP_Supporter", "message": sc_msg, "is_superchat": True, "amount": "$20.00", "timestamp": time.time()})
    app.brain.add_chat_message("VIP_Supporter", sc_msg, True, "$20.00")
    app._trigger_ai_turn(prompt_trigger=f"Chat message from @VIP_Supporter: '{sc_msg}'")
    await asyncio.sleep(2.0)

    # 6. Simulate Host Celebration Trigger
    print("-> [Step 6: Celebration Event -> 'Bradford: Celebrate!']")
    app.visualizer.trigger_celebration(duration=5.0)
    app._trigger_ai_turn(prompt_trigger="[CELEBRATION] Host Bradford called for a celebration: 'Celebrate!'. Hyped celebration response!")
    await asyncio.sleep(2.0)

    # 7. Simulate New Channel Member Event
    print("-> [Step 7: New Member Event -> @CosmicVoyager joined membership!]")
    app.visualizer.trigger_celebration(duration=6.0)
    app._trigger_ai_turn(prompt_trigger="[NEW_MEMBER] @CosmicVoyager just joined as a channel member! Enthusiastic shoutout!")
    await asyncio.sleep(3.0)

    # 8. Simulate Viewer Count Drop to 0 (Transition back to ECO Mode)
    print("-> [Step 8: Viewers Leave Stream -> Viewers: 0 -> Transition to ECO Mode]")
    app.last_chat_time = 0
    app._on_viewer_count_update(0, 0)
    await asyncio.sleep(0.5)

    # Validate state
    print("\n" + "-" * 50)
    print("PIPELINE STATE VERIFICATION:")
    print(f"-> Active Visualizer Mood: {app.visualizer.current_mood}")
    print(f"-> AI Subtitle Banner: '{app.current_ai_subtitle}'")
    print(f"-> Engagement Mode: {app.engagement_mode.upper()}")
    print(f"-> Concurrent Viewers: {app.concurrent_viewers}")
    print(f"-> Visualizer Celebration Active: {app.visualizer.celebration_timer > 0}")
    print(f"-> Total NDI Video Frames Broadcast: {app.ndi.frames_sent}")
    print("-" * 50)

    assert app.engagement_mode == "eco", f"Expected eco mode, got {app.engagement_mode}"
    assert app.ndi.frames_sent > 30, f"Expected at least 30 NDI frames, got {app.ndi.frames_sent}"
    assert len(app.current_ai_subtitle) > 0, "Expected active AI subtitles"

    # Stop app
    app.stop()
    video_task.cancel()
    scheduler_task.cancel()
    try:
        await asyncio.gather(video_task, scheduler_task, return_exceptions=True)
    except Exception:
        pass
    app.ndi.close()

    print("\n" + "=" * 65)
    print("ALL-LOCAL END-TO-END SIMULATION TEST COMPLETED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_e2e_test())
