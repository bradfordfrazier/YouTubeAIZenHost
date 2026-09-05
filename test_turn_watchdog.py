"""
Turn timeout / recovery tests (Part B of VERIFY_tts_supply_fix.md).

Uses turn_guard.run_guarded_turn (the same helper the scheduler in app.py uses) with a
real TTSEngine so the recovery path is exercised against real state.
"""

from pathlib import Path
import asyncio
import sys
import time
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tts_engine import TTSEngine  # noqa: E402
from turn_guard import run_guarded_turn  # noqa: E402


class FakeApp:
    """Minimal stand-in for the turn-related state of AILiveStreamCoHost."""

    def __init__(self):
        self.tts = TTSEngine()
        self.tts.cfg.local_audio_enabled = False
        self.tts.ndi_buffer_enabled = False
        self.turn_phase = "idle"
        self.pinned = "some question"
        self.recovered = 0
        self.turns_completed = 0

    async def stuck_turn(self):
        """Mimics a turn whose lead gate never opens: acquires shared state then waits forever."""
        self.turn_phase = "start"
        self.tts.live_turn_active.set()
        try:
            self.tts.begin_utterance()
            self.tts.push_audio(np.zeros((48000, 2), dtype=np.float32))
            self.turn_phase = "lead_gate"
            async with self.tts.gpu_lock:
                await asyncio.sleep(3600)  # never returns
        finally:
            # same responsibilities as _execute_ai_turn's finally block
            # (turn_phase is intentionally left as-is so the timeout log can report it)
            self.tts.live_turn_active.clear()

    async def good_turn(self):
        self.turn_phase = "start"
        self.tts.live_turn_active.set()
        try:
            self.tts.begin_utterance()
            self.tts.push_audio(np.zeros((4800, 2), dtype=np.float32))
            self.tts.end_utterance()
            await asyncio.sleep(0.05)
            self.turns_completed += 1
        finally:
            self.tts.live_turn_active.clear()

    async def recover(self):
        """Mirrors AILiveStreamCoHost._recover_from_stuck_turn."""
        self.tts.clear_audio_buffer()
        self.tts.end_utterance()
        self.tts.live_turn_active.clear()
        self.tts.last_live_turn_end_time = time.time()
        self.pinned = None
        self.turn_phase = "idle"
        self.recovered += 1


def test_stuck_turn_times_out_and_next_turn_runs(caplog):
    async def _run():
        app = FakeApp()
        t0 = time.perf_counter()
        with caplog.at_level("ERROR"):
            ok = await run_guarded_turn(
                app.stuck_turn(), timeout_sec=1.0,
                phase_getter=lambda: app.turn_phase, on_timeout=app.recover, label="stuck",
            )
        elapsed = time.perf_counter() - t0

        # (a) returned promptly
        assert ok is False
        assert elapsed < 2.0, f"took {elapsed:.2f}s"
        # (b) live turn flag cleared, (c) lock released
        assert not app.tts.live_turn_active.is_set()
        assert not app.tts.gpu_lock.locked()
        # buffers flushed, utterance closed, pinned cleared, phase reported in the log
        assert app.tts.get_buffered_duration() == 0.0
        assert app.tts._utterance_open is False
        assert app.pinned is None
        assert app.recovered == 1
        assert any("TURN TIMEOUT" in r.message and "lead_gate" in r.message for r in caplog.records)

        # (d) a second turn completes normally afterwards
        ok2 = await run_guarded_turn(
            app.good_turn(), timeout_sec=5.0,
            phase_getter=lambda: app.turn_phase, on_timeout=app.recover, label="good",
        )
        assert ok2 is True
        assert app.turns_completed == 1
        assert app.recovered == 1

    asyncio.run(_run())


def test_turn_exception_does_not_kill_scheduler():
    async def _run():
        app = FakeApp()

        async def bad_turn():
            app.tts.live_turn_active.set()
            try:
                raise RuntimeError("boom")
            finally:
                app.tts.live_turn_active.clear()

        ok = await run_guarded_turn(bad_turn(), 5.0, lambda: app.turn_phase, app.recover, "bad")
        assert ok is False
        assert app.recovered == 0
        ok2 = await run_guarded_turn(app.good_turn(), 5.0, lambda: app.turn_phase, app.recover, "good")
        assert ok2 is True

    asyncio.run(_run())
