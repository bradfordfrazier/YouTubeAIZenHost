"""
Pre-Computed Spontaneous Reflection Cache (D2).
Maintains a rotating queue of pre-computed aphoristic I AM reflections generated during
quiet stream intervals, enabling zero-latency (0.0s TTFT) spontaneous commentary.
"""

import asyncio
from dataclasses import dataclass
import logging
import re
import time
from typing import Dict, List, Optional

logger = logging.getLogger("reflection_cache")


@dataclass
class CachedReflection:
    """A pre-computed spontaneous reflection ready for immediate broadcast."""
    theme: str
    mood: str
    full_text: str
    created_at: float

    def to_dict(self) -> Dict[str, str]:
        return {
            "type": "complete",
            "mood": self.mood,
            "full_text": self.full_text,
            "theme": self.theme,
            "is_precomputed": True,
        }


class ReflectionCache:
    """Thread-safe queue of pre-computed spontaneous reflections."""

    _instance: Optional["ReflectionCache"] = None

    def __init__(self, max_size: int = 4):
        self.max_size = max_size
        self.queue: List[CachedReflection] = []
        self._lock = asyncio.Lock()
        self.total_served: int = 0
        self.total_generated: int = 0

    @classmethod
    def get_instance(cls, max_size: int = 4) -> "ReflectionCache":
        if cls._instance is None:
            cls._instance = ReflectionCache(max_size=max_size)
        return cls._instance

    def size(self) -> int:
        return len(self.queue)

    def has_reflection(self) -> bool:
        return len(self.queue) > 0

    async def pop_reflection(self) -> Optional[CachedReflection]:
        """Pops the next pre-computed reflection with zero latency."""
        async with self._lock:
            if not self.queue:
                return None
            item = self.queue.pop(0)
            self.total_served += 1
            logger.info(
                f"⚡ [Reflection Cache Hit] Popped instant reflection on '{item.theme}' "
                f"([{item.mood.upper()}]: '{item.full_text[:40]}...'). Remaining in cache: {len(self.queue)}"
            )
            return item

    async def add_reflection(self, reflection: CachedReflection) -> bool:
        """Adds a newly synthesized reflection to the cache if not full."""
        async with self._lock:
            if len(self.queue) >= self.max_size:
                return False
            self.queue.append(reflection)
            self.total_generated += 1
            logger.info(
                f"🧠 [Reflection Cache Primed] Pre-computed '{reflection.theme}' "
                f"([{reflection.mood.upper()}]: '{reflection.full_text[:40]}...'). Cache level: {len(self.queue)}/{self.max_size}"
            )
            return True

    async def replenish_worker(self, brain, poll_interval: float = 12.0):
        """
        Background worker that quietly generates spontaneous reflections
        during idle stream moments to keep the cache continuously primed.
        """
        logger.info(f"⚡ [Reflection Cache Worker] Background pre-computation worker active (Target: {self.max_size}).")
        # Stagger initial boot
        await asyncio.sleep(8.0)

        while True:
            try:
                await asyncio.sleep(poll_interval)
                if getattr(brain, "engagement_mode", "active") in ("standby", "eco"):
                    continue

                if self.size() >= self.max_size:
                    continue

                # Only pre-compute when AI Brain is completely idle
                if brain.is_generating:
                    continue

                theme = brain.get_next_spontaneous_theme()
                logger.debug(f"Pre-generating spontaneous reflection for theme '{theme}'...")

                full_text = ""
                active_mood = "thoughtful"
                async for chunk in brain.generate_response_stream("[SPONTANEOUS_REFLECTION]", bypass_cache=True):
                    ev_type = chunk.get("type", "")
                    if ev_type == "mood":
                        active_mood = chunk.get("mood", "thoughtful")
                    elif ev_type == "complete":
                        full_text = chunk.get("full_text", "").strip()
                        active_mood = chunk.get("mood", active_mood)

                if full_text and len(full_text) >= 15:
                    item = CachedReflection(
                        theme=theme,
                        mood=active_mood,
                        full_text=full_text,
                        created_at=time.time(),
                    )
                    await self.add_reflection(item)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Reflection cache replenishment cycle note: {e}")
                await asyncio.sleep(15.0)
