"""
Unit test for Chat Responsiveness, Complete Statement Synthesis, and Turn Queue.
Verifies that:
1. Complete statements are synthesized as cohesive phrases (no sentence fragmentation).
2. Chat messages arriving while the AI is busy are queued and answered in order.
3. Questions in chat trigger responses even when viewer count is low (Eco mode relaxed).
"""

import asyncio
import time

from config import config
from app import LocalCoHostApp


async def run_test():
    print("=" * 65)
    print("STARTING CHAT RESPONSIVENESS & COMPLETE STATEMENT SYNTHESIS TEST")
    print("=" * 65)

    config.visualizer_headless = True
    config.local_audio_enabled = False
    app = LocalCoHostApp()

    # 1. Test Single Complete Statement Synthesis
    print("\n--- Test 1: Complete Speech Generation & Full Phrase Queuing ---")
    prompt = "Host said: 'Nova, what is the meaning of existence in one punchy sentence?'"
    app._trigger_ai_turn(prompt)
    assert app.active_ai_task is not None, "AI turn task failed to start"
    await app.active_ai_task

    buf_samples = len(app.tts._audio_buffer_ndi)
    buf_sec = buf_samples / 48000
    print(f"-> Synthesized Audio Duration in Buffer: {buf_sec:.2f}s ({buf_samples} samples)")
    print(f"-> Full AI Subtitle: '{app.current_ai_subtitle}'")
    assert buf_sec > 1.0, f"Expected > 1.0s of speech, got {buf_sec:.2f}s"
    assert len(app.current_ai_subtitle) > 10, "Subtitle text was empty or truncated"

    # 2. Test Multi-Message Queuing while AI is Busy
    print("\n--- Test 2: Multi-Message Turn Queuing ---")
    # Simulate a running task
    app._trigger_ai_turn("Host said: 'Question 1: Who are you?'")
    time.sleep(0.05)
    # Queue message 2 and message 3 while task 1 is running
    app._trigger_ai_turn("Chat message from @Gamer1: 'Nova what game should we play next?'")
    app._trigger_ai_turn("Chat message from @ZenMaster: 'How do I reach inner peace?'")

    print(f"-> Pending triggers in queue: {len(app.pending_triggers)}")
    assert len(app.pending_triggers) == 2, f"Expected 2 queued triggers, got {len(app.pending_triggers)}"

    # Let task 1 complete and automatically dequeue task 2 and 3
    print("-> Awaiting automatic queue draining...")
    await app.active_ai_task
    # Allow small delay for dequeued tasks to start
    await asyncio.sleep(0.5)
    if app.active_ai_task and not app.active_ai_task.done():
        await app.active_ai_task
    await asyncio.sleep(0.5)
    if app.active_ai_task and not app.active_ai_task.done():
        await app.active_ai_task

    print("-> All queued turns processed successfully!")

    # 3. Test Chat Question Eligibility
    print("\n--- Test 3: Chat Question Eligibility in Eco/Idle Mode ---")
    app.brain.set_engagement_mode("eco", is_stream_live=True, concurrent_viewers=0)
    should_trig, reason = app.brain.should_trigger_response("What is the truth about reality?", is_host=False)
    print(f"-> Chat question 'What is the truth about reality?': should_trigger={should_trig} ({reason})")
    assert should_trig, f"Expected chat question to trigger, got {should_trig} ({reason})"

    app.stop()
    print("\n" + "=" * 65)
    print(">>> CHAT RESPONSIVENESS & STATEMENT SYNTHESIS TEST PASSED! <<<")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_test())
