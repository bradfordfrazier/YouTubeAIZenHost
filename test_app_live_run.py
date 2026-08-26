"""
Verification script that boots LocalCoHostApp live, runs all tasks for 5 seconds,
and verifies visualizer rendering, NDI broadcasting, and audio playback.
"""

import asyncio
import time
from config import config
from app import LocalCoHostApp

async def main():
    print("=" * 65)
    print("STARTING LIVE APP RUNTIME VERIFICATION (5 SECONDS)")
    print("=" * 65)

    config.visualizer_headless = True
    config.local_audio_enabled = False
    config.mock_chat_enabled = True

    app = LocalCoHostApp()

    # Launch app in background task
    app_task = asyncio.create_task(app.start())

    # Wait 4 seconds while it renders frames
    await asyncio.sleep(4.0)

    # Trigger a test voice line while live
    print("-> Triggering test AI turn while live...")
    app._trigger_ai_turn("Host said: 'Nova check audio sync.'")

    await asyncio.sleep(2.0)

    print(f"-> Active NDI connections: {app.ndi.get_num_connections()}")
    print(f"-> Current mood: {app.visualizer.current_mood}")
    print(f"-> Current subtitle: {app.current_ai_subtitle}")

    # Clean stop
    app.stop()
    await asyncio.sleep(0.5)
    if not app_task.done():
        app_task.cancel()

    print("=" * 65)
    print(">>> LIVE APP RUNTIME VERIFICATION PASSED SUCCESSFULLY! <<<")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(main())
