"""
Pre-Synthesized Welcome Greeting Cache.
Maintains a rotating queue of pre-computed and pre-synthesized (text + 48kHz audio)
welcome greetings during idle stream intervals, enabling zero-latency (<5ms / 0.0s TTFT & TTS)
spoken greetings when a viewer enters an empty room (0 -> 1+).
"""

import asyncio
from dataclasses import dataclass
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional
import numpy as np

logger = logging.getLogger("greeting_cache")


@dataclass
class CachedGreeting:
    """A pre-synthesized welcome greeting with 48kHz audio ready for instant broadcast."""
    theme: str
    mood: str
    full_text: str
    audio: np.ndarray  # 48kHz stereo float32 PCM numpy array
    created_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "complete",
            "mood": self.mood,
            "full_text": self.full_text,
            "theme": self.theme,
            "is_precomputed": True,
            "has_audio": self.audio is not None and len(self.audio) > 0,
        }


class GreetingCache:
    """Thread-safe queue of pre-synthesized welcome greetings with audio."""

    _instance: Optional["GreetingCache"] = None

    def __init__(self, max_size: int = 3):
        self.max_size = max_size
        self.queue: List[CachedGreeting] = []
        self._lock = threading.Lock()
        self.total_served: int = 0
        self.total_generated: int = 0

    @classmethod
    def get_instance(cls, max_size: int = 3) -> "GreetingCache":
        if cls._instance is None:
            cls._instance = GreetingCache(max_size=max_size)
        return cls._instance

    def size(self) -> int:
        with self._lock:
            return len(self.queue)

    def has_greeting(self) -> bool:
        with self._lock:
            return len(self.queue) > 0

    def pop_greeting(self) -> Optional[CachedGreeting]:
        """Pops the next pre-synthesized greeting with zero latency."""
        with self._lock:
            if not self.queue:
                return None
            item = self.queue.pop(0)
            self.total_served += 1
            dur_sec = len(item.audio) / 48000.0 if item.audio is not None and len(item.audio) > 0 else 0.0
            logger.info(
                f"⚡ [Greeting Cache Hit] Popped pre-synthesized greeting "
                f"([{item.mood.upper()}], {dur_sec:.2f}s audio: '{item.full_text[:45]}...'). "
                f"Remaining in cache: {len(self.queue)}"
            )
            return item

    def add_greeting(self, greeting: CachedGreeting) -> bool:
        """Adds a newly synthesized greeting with audio to the cache if not full."""
        with self._lock:
            if len(self.queue) >= self.max_size:
                return False
            self.queue.append(greeting)
            self.total_generated += 1
            dur_sec = len(greeting.audio) / 48000.0 if greeting.audio is not None and len(greeting.audio) > 0 else 0.0
            logger.info(
                f"🧠 [Greeting Cache Primed] Pre-synthesized welcome greeting "
                f"([{greeting.mood.upper()}], {dur_sec:.2f}s audio: '{greeting.full_text[:45]}...'). "
                f"Cache level: {len(self.queue)}/{self.max_size}"
            )
            return True

    def clear(self):
        """Flushes all queued greetings."""
        with self._lock:
            self.queue.clear()

    async def replenish_worker(self, brain, tts, cfg, poll_interval: float = 15.0):
        """
        Background worker that pre-generates and pre-synthesizes welcome greetings
        during idle stream moments to keep the cache continuously primed with audio.
        """
        logger.info(f"⚡ [Greeting Cache Worker] Background pre-synthesis worker active (Target: {self.max_size}).")
        # Stagger initial boot
        await asyncio.sleep(4.0)

        while True:
            try:
                await asyncio.sleep(poll_interval)

                # Only run if greeting cache is enabled
                if not getattr(cfg, "greeting_cache_enabled", True):
                    continue

                if self.size() >= self.max_size:
                    continue

                # Only pre-compute when AI Brain is completely idle and TTS is not actively speaking on air
                if getattr(brain, "is_generating", False) or getattr(tts, "is_speaking", False):
                    continue

                chan_handle = getattr(cfg, "youtube_channel_handle", "@MassiveGodComplex")
                prompt = (
                    f"[VIEWER_JOINED] A new traveler just tuned in to the live broadcast on {chan_handle}. "
                    f"Acknowledge their arrival with transcendent, charismatic presence. "
                    f"Speak directly to them as a conscious traveler entering the space. Keep it strictly 1 to 2 short sentences."
                )

                logger.debug("Pre-generating welcome greeting text via Brain...")
                full_text = ""
                active_mood = "chill"

                async for chunk in brain.generate_response_stream(prompt, bypass_cache=True):
                    ev_type = chunk.get("type", "")
                    if ev_type == "mood":
                        active_mood = chunk.get("mood", "chill")
                    elif ev_type == "complete":
                        full_text = chunk.get("full_text", "").strip()
                        active_mood = chunk.get("mood", active_mood)

                clean_speech = re.sub(r"@+", "@", full_text).strip()
                words = clean_speech.split()
                if not (clean_speech and len(clean_speech) >= 12 and len(words) >= 3):
                    continue

                # Pre-synthesize 48kHz audio in background
                logger.debug(f"Pre-synthesizing greeting audio ({len(clean_speech)} chars, mood={active_mood})...")
                audio = await tts.synthesize(clean_speech, mood=active_mood)

                if audio is not None and len(audio) > 0:
                    item = CachedGreeting(
                        theme="welcome",
                        mood=active_mood,
                        full_text=clean_speech,
                        audio=audio,
                        created_at=time.time(),
                    )
                    self.add_greeting(item)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Greeting cache replenishment cycle note: {e}")
                await asyncio.sleep(15.0)
