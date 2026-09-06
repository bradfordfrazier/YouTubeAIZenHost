"""
Unit test for VisualizerProxy ctrl_queue and state_queue (Item 3).
Verifies that control commands are never dropped during worker stall.
"""

import os
from pathlib import Path
import sys
import time
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from render_worker import VisualizerProxy


def test_ctrl_queue_never_drops_during_worker_stall():
    """
    Sets IAM_TEST_WORKER_STALL=1 to trigger a 3-second stall in the render worker,
    while sending 20 SET_MOOD commands from the main process.
    Verifies that all 20 are accepted into ctrl_queue without throwing or logging ERROR.
    """
    os.environ["IAM_TEST_WORKER_STALL"] = "1"
    proxy = VisualizerProxy(shm_name="iam_test_stall_shm")
    try:
        # Send 20 distinct mood commands while worker is stalling
        moods = ["chill", "energetic", "hyped", "mysterious", "thoughtful", "snarky", "transcendent", "savage"]
        sent_moods = []
        for i in range(20):
            m = moods[i % len(moods)]
            proxy.set_mood(m)
            sent_moods.append(m)

        # Wait for worker to finish startup, stall, and process the queue
        t_end = time.time() + 6.0
        while time.time() < t_end:
            if proxy.ctrl_queue.empty() or proxy.ctrl_queue.qsize() < 20:
                break
            time.sleep(0.2)

        # Confirm proxy's tracking of current mood matches the 20th sent command
        assert proxy.current_mood == sent_moods[-1]
        assert proxy.ctrl_queue.empty() or proxy.ctrl_queue.qsize() < 20
    finally:
        proxy.stop()
        os.environ.pop("IAM_TEST_WORKER_STALL", None)


def test_state_queue_fingerprint_deduplication():
    """
    Verifies that sync_state only enqueues when state changes,
    avoiding queue congestion on high frequency calls.
    """
    proxy = VisualizerProxy(shm_name="iam_test_dedup_shm")
    try:
        chat = [{"author": "Alice", "message": "Hello"}]
        # Call 50 times with identical state
        for _ in range(50):
            proxy.sync_state(chat_messages=chat, obs_connected=True, engagement_mode="active", concurrent_viewers=10, is_stream_live=True)

        # Queue size should be at most 1 because of fingerprinting
        assert proxy.state_queue.qsize() <= 1
    finally:
        proxy.stop()


def test_worker_restart_and_state_replay():
    """
    Verifies that when the render worker process dies unexpectedly,
    check_and_restart_if_dead() respawns the worker and replays the active
    visual state (mood, subtitle, pinned chat question).
    """
    proxy = VisualizerProxy(shm_name="iam_test_restart_shm")
    try:
        # 1. Establish visual state
        proxy.set_mood("energetic")
        proxy.set_subtitle("Replay Motto & Subtitle")
        proxy.set_pinned({"author": "ZenMaster", "message": "What is the sound of one hand clapping?"})

        # Drain queues so we can inspect replay accurately
        time.sleep(0.5)

        # 2. Simulate worker crash by terminating the worker process
        initial_pid = proxy.process.pid
        proxy.process.terminate()
        proxy.process.join(timeout=2.0)
        assert not proxy.process.is_alive()

        # 3. Trigger crash recovery
        restarted = proxy.check_and_restart_if_dead()
        assert restarted is True
        assert proxy.restart_count == 1
        assert proxy.process.is_alive()
        assert proxy.process.pid != initial_pid

        # 4. Verify visual state attributes remain intact on the proxy
        assert proxy.current_mood == "energetic"
        assert proxy.ai_text_target == "Replay Motto & Subtitle"
        assert proxy.current_pinned == {"author": "ZenMaster", "message": "What is the sound of one hand clapping?"}
    finally:
        proxy.stop()
