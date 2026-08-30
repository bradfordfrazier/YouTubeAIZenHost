"""
Session Logging Subsystem (C1).
Records every AI turn, chatter message, cast question, spontaneous reflection,
and viewer metric to structured JSONL session logs for auditing and continuity memory.
"""

from datetime import datetime
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("session_log")


class SessionLogger:
    """Thread-safe, non-blocking structured JSONL session logger."""

    _instance: Optional["SessionLogger"] = None
    _lock = threading.Lock()

    def __init__(self, log_dir: str = "logs/sessions", session_id: Optional[str] = None):
        self.log_dir = Path(log_dir).resolve()
        self.log_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now()
        self.session_id = session_id or f"session_{now.strftime('%Y%m%d_%H%M%S')}"
        self.log_file = self.log_dir / f"{self.session_id}.jsonl"

        self._file_lock = threading.Lock()
        self._recent_events: List[Dict[str, Any]] = []
        self._max_recent = 100
        self._start_time = time.time()
        self._turn_count = 0
        self._chat_count = 0
        self._cast_count = 0

        # Write session start header entry
        self.log_event(
            "session_start",
            {
                "session_id": self.session_id,
                "start_time_iso": now.isoformat(),
                "log_file": str(self.log_file),
            },
        )
        logger.info(f"📝 [Session Log] Initialized session log: {self.log_file}")

    @classmethod
    def get_instance(cls, log_dir: str = "logs/sessions") -> "SessionLogger":
        with cls._lock:
            if cls._instance is None:
                cls._instance = SessionLogger(log_dir=log_dir)
            return cls._instance

    def log_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Logs an event dict to JSONL session log file."""
        now_ts = time.time()
        now_iso = datetime.fromtimestamp(now_ts).isoformat()

        entry: Dict[str, Any] = {
            "timestamp": now_iso,
            "unix_timestamp": now_ts,
            "session_id": self.session_id,
            "event_type": event_type,
        }
        if data:
            entry.update(data)

        # Update in-memory rolling buffer
        with self._file_lock:
            self._recent_events.append(entry)
            if len(self._recent_events) > self._max_recent:
                self._recent_events.pop(0)

            # Append to disk
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    f.flush()
            except Exception as e:
                logger.warning(f"Failed to write to session log file {self.log_file}: {e}")

        return entry

    def log_ai_turn(
        self,
        trigger: str,
        event_type: str,
        full_text: str,
        mood: str,
        exaggeration: float = 0.5,
        tts_backend: str = "local",
        turn_latency_sec: float = 0.0,
        audio_duration_sec: float = 0.0,
        author: str = "",
        is_cast: bool = False,
        concurrent_viewers: int = 0,
    ) -> Dict[str, Any]:
        """Convenience method for logging an AI co-host speaking turn."""
        self._turn_count += 1
        return self.log_event(
            "ai_turn",
            {
                "turn_index": self._turn_count,
                "trigger": trigger,
                "turn_event_type": event_type,
                "author": author,
                "is_cast": is_cast,
                "full_text": full_text,
                "mood": mood,
                "exaggeration": exaggeration,
                "tts_backend": tts_backend,
                "turn_latency_sec": round(turn_latency_sec, 3),
                "audio_duration_sec": round(audio_duration_sec, 3),
                "concurrent_viewers": concurrent_viewers,
            },
        )

    def log_chat_message(
        self,
        author: str,
        author_type: str,
        message: str,
        is_superchat: bool = False,
        amount: str = "",
        is_cast: bool = False,
        cast_persona: str = "",
    ) -> Dict[str, Any]:
        """Convenience method for logging incoming chat messages."""
        self._chat_count += 1
        if is_cast:
            self._cast_count += 1

        return self.log_event(
            "chat_message",
            {
                "chat_index": self._chat_count,
                "author": author,
                "author_type": author_type,
                "message": message,
                "is_superchat": is_superchat,
                "amount": amount,
                "is_cast": is_cast,
                "cast_persona": cast_persona,
            },
        )

    def log_cast_question(
        self,
        persona_name: str,
        persona_handle: str,
        persona_type: str,
        question: str,
    ) -> Dict[str, Any]:
        """Convenience method for logging generated cast questions."""
        self._cast_count += 1
        return self.log_event(
            "cast_question",
            {
                "persona_name": persona_name,
                "persona_handle": persona_handle,
                "persona_type": persona_type,
                "question": question,
            },
        )

    def get_recent_history(self, limit: int = 20, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns recent events from in-memory cache for prompt continuity memory."""
        with self._file_lock:
            if event_type:
                filtered = [e for e in self._recent_events if e.get("event_type") == event_type]
                return filtered[-limit:]
            return self._recent_events[-limit:]

    def get_session_summary(self) -> Dict[str, Any]:
        """Returns statistical summary of the current session."""
        now = time.time()
        return {
            "session_id": self.session_id,
            "duration_sec": round(now - self._start_time, 1),
            "total_turns": self._turn_count,
            "total_chats": self._chat_count,
            "total_cast_questions": self._cast_count,
            "log_file": str(self.log_file),
        }

    def get_stream_health_metrics(self) -> Dict[str, Any]:
        """Returns structured health telemetry for the observability HUD (E4)."""
        summary = self.get_session_summary()
        with self._file_lock:
            turns = [e for e in self._recent_events if e.get("event_type") == "ai_turn"]
            latencies = [t.get("turn_latency_sec", 0.0) for t in turns[-10:] if t.get("turn_latency_sec")]
            avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
        return {
            **summary,
            "recent_turns_analyzed": len(latencies),
            "avg_latency_sec": avg_latency,
        }

    def close(self):
        """Finalizes session log with summary."""
        summary = self.get_session_summary()
        self.log_event("session_end", summary)
        logger.info(f"📝 [Session Log] Session finalized ({summary['total_turns']} turns, {summary['duration_sec']}s).")
