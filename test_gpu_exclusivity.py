"""
GPU exclusivity tests for TTSEngine (Part A of VERIFY_tts_supply_fix.md).

Verifies:
1. synthesize_background does not deadlock (regression: asyncio.Lock is not re-entrant).
2. A live synthesize() call is never blocked behind a background call that is waiting
   on live_turn_active.
3. synthesize_background never holds gpu_lock while blocked on live_turn_active.
4. Background synthesis resumes only after the turn ends plus cache_refill_cooldown_sec.
"""

from pathlib import Path
import asyncio
import sys
import time
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tts_engine import TTSEngine  # noqa: E402


def _fake_backend(delay_sec: float):
    """Replaces the Chatterbox HTTP call with a sleep that returns 0.5 s of silence."""
    async def _fake(self_or_text, *args, **kwargs):
        await asyncio.sleep(delay_sec)
        return np.zeros((24000, 2), dtype=np.float32)
    return _fake


def _engine(cooldown: float = 0.3, backend_delay: float = 0.5) -> TTSEngine:
    e = TTSEngine()
    e.cfg.cache_refill_cooldown_sec = cooldown
    e.active_backend = "chatterbox"
    e._synthesize_chatterbox = _fake_backend(backend_delay)  # type: ignore[assignment]
    return e


def test_background_synthesis_does_not_deadlock():
    async def _run():
        e = _engine()
        audio = await asyncio.wait_for(e.synthesize_background("Hello there traveler.", "chill"), timeout=3.0)
        assert len(audio) > 0
        assert not e.gpu_lock.locked()

    asyncio.run(_run())


def test_live_turn_not_blocked_by_waiting_background():
    async def _run():
        e = _engine(cooldown=0.3, backend_delay=0.4)

        # Live turn is active before the background request is made
        e.live_turn_active.set()
        bg_task = asyncio.create_task(e.synthesize_background("Background greeting text.", "chill"))
        await asyncio.sleep(0.1)  # bg should now be waiting OUTSIDE the lock

        assert not e.gpu_lock.locked(), "background must not hold gpu_lock while a live turn is active"
        assert e._bg_inside_gpu_lock is False

        t0 = time.perf_counter()
        live = await e.synthesize("Live sentence one.", mood="hyped", is_live=True, _from_live_turn=True)
        live_wall = time.perf_counter() - t0
        assert len(live) > 0
        assert live_wall < 1.0, f"live synth took {live_wall:.2f}s; it was blocked by background work"
        assert not bg_task.done(), "background must not have run while live_turn_active was set"

        # End the turn: bg must wait the cooldown before running
        e.live_turn_active.clear()
        e.last_live_turn_end_time = time.time()
        t_end = time.perf_counter()
        await asyncio.wait_for(bg_task, timeout=3.0)
        bg_done_after = time.perf_counter() - t_end
        assert bg_done_after >= 0.3 + 0.4 - 0.05, f"background finished too early ({bg_done_after:.2f}s)"
        assert not e.gpu_lock.locked()

    asyncio.run(_run())


def test_background_yields_if_turn_starts_while_it_waits_for_lock():
    async def _run():
        e = _engine(cooldown=0.0, backend_delay=0.4)

        # Occupy the lock with a live sentence, start bg (it will queue on the lock)
        live1 = asyncio.create_task(e.synthesize("First live.", is_live=True, _from_live_turn=True))
        await asyncio.sleep(0.05)
        assert e.gpu_lock.locked()
        bg = asyncio.create_task(e.synthesize_background("Bg text here.", "chill"))
        await asyncio.sleep(0.05)

        # A turn becomes active before bg gets the lock; bg must release and re-wait
        e.live_turn_active.set()
        await live1
        await asyncio.sleep(0.15)
        assert e._bg_inside_gpu_lock is False
        assert not bg.done()

        # Live turn keeps going and is not blocked
        t0 = time.perf_counter()
        await e.synthesize("Second live.", is_live=True, _from_live_turn=True)
        assert time.perf_counter() - t0 < 0.7

        e.live_turn_active.clear()
        await asyncio.wait_for(bg, timeout=3.0)

    asyncio.run(_run())


def test_misuse_logs_but_still_synthesizes(caplog):
    async def _run():
        e = _engine()
        with caplog.at_level("ERROR"):
            audio = await e.synthesize("Misused call.", mood="chill")
        assert len(audio) > 0
        assert any("TTS MISUSE" in r.message for r in caplog.records)

    asyncio.run(_run())
