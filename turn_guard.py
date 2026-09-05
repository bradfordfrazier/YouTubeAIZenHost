"""
Turn guard: runs one AI speech turn under a hard timeout so a stuck turn can never
block the serialized scheduler. Kept dependency-free so it can be unit-tested without
importing app.py.
"""

import asyncio
import logging
from typing import Awaitable, Callable, Optional

logger = logging.getLogger("turn_guard")


async def run_guarded_turn(
    turn_coro: Awaitable,
    timeout_sec: float,
    phase_getter: Callable[[], str],
    on_timeout: Callable[[], Awaitable[None]],
    label: str = "turn",
) -> bool:
    """
    Awaits `turn_coro` with `asyncio.wait_for`. On timeout the coroutine is cancelled
    (its own finally-block runs), an ERROR is logged with the current phase, and
    `on_timeout` is awaited for state recovery. Returns True if the turn completed
    normally, False if it timed out. Any other exception from the turn is logged and
    swallowed so the scheduler keeps running.
    """
    try:
        await asyncio.wait_for(turn_coro, timeout=timeout_sec)
        return True
    except asyncio.TimeoutError:
        logger.error(
            f"[TURN TIMEOUT] {label} exceeded {timeout_sec:.0f}s in phase '{phase_getter()}'; "
            "recovering and continuing scheduler."
        )
        try:
            await on_timeout()
        except Exception as e:
            logger.error(f"[TURN TIMEOUT] recovery raised: {e}", exc_info=True)
        return False
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Error executing {label}: {e}", exc_info=True)
        return False
