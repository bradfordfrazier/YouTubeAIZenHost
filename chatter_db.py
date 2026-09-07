"""
Chatter Identity & Relationship Database (C3).
Maintains persistent profiles of human chatters and synthetic cast members across
stream sessions, tracking visits, message frequency, topics, notes, and relationship context.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import logging
from pathlib import Path
import re
import threading
import time
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("chatter_db")


@dataclass
class ChatterProfile:
    """Represents a persistent profile for a human chatter or cast member."""
    handle: str
    display_name: str
    first_seen_iso: str
    last_seen_iso: str
    visit_count: int = 1
    message_count: int = 1
    is_member: bool = False
    is_cast: bool = False
    topics_discussed: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    last_session_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatterProfile":
        return cls(
            handle=data.get("handle", ""),
            display_name=data.get("display_name", ""),
            first_seen_iso=data.get("first_seen_iso", datetime.now().isoformat()),
            last_seen_iso=data.get("last_seen_iso", datetime.now().isoformat()),
            visit_count=data.get("visit_count", 1),
            message_count=data.get("message_count", 1),
            is_member=data.get("is_member", False),
            is_cast=data.get("is_cast", False),
            topics_discussed=data.get("topics_discussed", []),
            notes=data.get("notes", []),
            last_session_id=data.get("last_session_id", ""),
        )

    def generate_context_snippet(self) -> str:
        """Generates a compact context tag for prompt injection."""
        parts = [f"@{self.handle}"]
        if self.is_cast:
            parts.append("Synthetic Cast Member (Recurring Fictional Cast Character)")
            if self.notes:
                parts.append(f"Persona: {self.notes[0]}")
            return f"[CAST CONTEXT: {' | '.join(parts)}]"
        elif self.is_member:
            parts.append("Channel Member")

        if self.visit_count > 1:
            parts.append(f"Visit #{self.visit_count} ({self.message_count} total messages)")
        else:
            parts.append(f"First session ({self.message_count} messages)")

        if self.topics_discussed:
            recent_topics = ", ".join(self.topics_discussed[-3:])
            parts.append(f"Topics: {recent_topics}")

        if self.notes:
            recent_note = self.notes[-1]
            parts.append(f"Note: {recent_note}")

        return f"[CHATTER CONTEXT: {' | '.join(parts)}]"


class ChatterDB:
    """Thread-safe persistent JSON database for chatter relationships."""

    _instance: Optional["ChatterDB"] = None
    _lock = threading.Lock()

    def __init__(self, db_path: str = "data/chatter_db.json"):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._save_lock = threading.Lock()
        self.profiles: Dict[str, ChatterProfile] = {}
        # Single source of truth: the live cast roster. Hardcoding this list let it drift out of
        # sync when personas were retired (SynergyLinda, BetaBot_7) or added (ConspiracyCarl,
        # ChefMarco), which would mis-flag a cast member as a real returning viewer.
        self._cast_handles: Set[str] = self._load_cast_handles()
        self._load()

    @classmethod
    def get_instance(cls, db_path: str = "data/chatter_db.json") -> "ChatterDB":
        with cls._lock:
            if cls._instance is None:
                cls._instance = ChatterDB(db_path=db_path)
            return cls._instance

    @staticmethod
    def _load_cast_handles() -> Set[str]:
        """Reads the current cast roster from cast_engine; falls back to a static list if absent."""
        try:
            from cast_engine import CastEngine
            handles = {
                p.handle.strip().lstrip("@").lower().replace(" ", "")
                for p in CastEngine().personas.values()
            }
            if handles:
                return handles
        except Exception as e:
            logger.warning(f"[ChatterDB] Could not read cast roster from cast_engine ({e}); using fallback list.")
        return {
            "existentialdave", "speedrunnerkyle", "astralbrenda", "trollchad", "heartfeltsarah",
            "curioustimmy", "grindsetgreg", "debraw1957", "gymsagebrody", "nocturnalnadia",
            "conspiracycarl", "chefmarco",
        }

    def _normalize_handle(self, handle: str) -> str:
        return handle.strip().lstrip("@").lower().replace(" ", "")

    def _load(self):
        """Loads persistent profiles from disk or pre-seeds defaults."""
        with self._lock:
            if self.db_path.exists():
                try:
                    with open(self.db_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        for k, v in data.items():
                            self.profiles[k] = ChatterProfile.from_dict(v)
                    logger.info(f"💾 [ChatterDB] Loaded {len(self.profiles)} chatter profiles from {self.db_path}")
                    loaded = True
                except Exception as e:
                    logger.warning(f"Error loading ChatterDB from {self.db_path}: {e}")
                    loaded = False
                if loaded:
                    # Seed personas added since this file was written, drop ones since retired.
                    # Both run under the lock we already hold, so use the unlocked variants.
                    self._preseed_cast()
                    self._prune_retired_cast_unlocked()
                    self._save_unlocked()
                    return

            # Pre-seed cast members
            self._preseed_cast()
            self._save_unlocked()

    def _preseed_cast(self):
        """Pre-seeds profiles for the current cast roster, read from cast_engine."""
        now_iso = datetime.now().isoformat()
        try:
            from cast_engine import CastEngine
            personas = list(CastEngine().personas.values())
        except Exception as e:
            logger.warning(f"[ChatterDB] Cast pre-seed skipped; cast_engine unavailable ({e}).")
            return

        for p in personas:
            norm = self._normalize_handle(p.handle)
            if norm in self.profiles:
                continue
            self.profiles[norm] = ChatterProfile(
                handle=p.handle,
                display_name=p.name,
                first_seen_iso=now_iso,
                last_seen_iso=now_iso,
                visit_count=1,
                message_count=1,
                is_member=False,
                is_cast=True,
                topics_discussed=[],
                notes=[f"Archetype: {p.archetype_title}. {p.bio}"],
            )
        logger.info(f"💾 [ChatterDB] Pre-seeded {len(personas)} cast profiles from the live roster.")

    def _prune_retired_cast_unlocked(self) -> int:
        """Caller must hold self._lock. Drops cast profiles no longer on the roster."""
        stale = [k for k, p in self.profiles.items() if p.is_cast and k not in self._cast_handles]
        for k in stale:
            del self.profiles[k]
        if stale:
            logger.info(f"💾 [ChatterDB] Pruned {len(stale)} retired cast profile(s): {', '.join(sorted(stale))}")
        return len(stale)

    def prune_retired_cast(self) -> int:
        """
        Drops profiles for cast members no longer on the roster (e.g. SynergyLinda, BetaBot_7).
        Real human profiles are never touched. Returns the number removed.
        """
        with self._lock:
            n = self._prune_retired_cast_unlocked()
            if n:
                self._save_unlocked()
        return n

    def _schedule_save(self):
        """Asynchronously writes an in-memory snapshot to disk without blocking the main event loop."""
        out_data = {k: v.to_dict() for k, v in self.profiles.items()}
        threading.Thread(target=self._write_snapshot_to_disk, args=(out_data,), daemon=True).start()

    def _write_snapshot_to_disk(self, snapshot: Dict[str, Any]):
        with self._save_lock:
            try:
                temp_path = self.db_path.with_suffix(".tmp")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(snapshot, f, indent=2, ensure_ascii=False)
                temp_path.replace(self.db_path)
            except Exception as e:
                logger.warning(f"Failed to persist ChatterDB to {self.db_path}: {e}")

    def _save_unlocked(self):
        """Synchronously writes in-memory profiles to disk atomically."""
        out_data = {k: v.to_dict() for k, v in self.profiles.items()}
        self._write_snapshot_to_disk(out_data)

    def get_returning_viewers(self) -> List[ChatterProfile]:
        """Returns profiles of real human returning viewers (strictly excludes cast members)."""
        with self._lock:
            return [
                p for p in self.profiles.values()
                if not p.is_cast and p.visit_count > 1
            ]

    def record_activity(
        self,
        handle: str,
        display_name: str,
        message: str,
        is_member: bool = False,
        is_cast: bool = False,
        session_id: str = "",
    ) -> ChatterProfile:
        """Records a chatter message, updating visit count, message count, and extracting topics."""
        norm = self._normalize_handle(handle)
        now_iso = datetime.now().isoformat()
        cast_flag = is_cast or (norm in self._cast_handles)

        with self._lock:
            if norm in self.profiles:
                p = self.profiles[norm]
                p.display_name = display_name or p.display_name
                p.last_seen_iso = now_iso
                p.message_count += 1
                if is_member:
                    p.is_member = True
                if cast_flag:
                    p.is_cast = True
                if not cast_flag and session_id and p.last_session_id != session_id:
                    p.visit_count += 1
                    p.last_session_id = session_id
            else:
                p = ChatterProfile(
                    handle=handle.strip().lstrip("@"),
                    display_name=display_name or handle,
                    first_seen_iso=now_iso,
                    last_seen_iso=now_iso,
                    visit_count=1,
                    message_count=1,
                    is_member=is_member,
                    is_cast=cast_flag,
                    last_session_id=session_id,
                )
                self.profiles[norm] = p
            # Extract basic significant topics/keywords
            self._extract_topics(p, message)
            self._schedule_save()
            return p

    def add_note(self, handle: str, note: str):
        """Adds a specific qualitative memory note to a chatter profile."""
        norm = self._normalize_handle(handle)
        with self._lock:
            if norm in self.profiles:
                p = self.profiles[norm]
                if note not in p.notes:
                    p.notes.append(note)
                    if len(p.notes) > 10:
                        p.notes.pop(0)
                    self._schedule_save()

    def get_profile(self, handle: str) -> Optional[ChatterProfile]:
        """Looks up a chatter profile by handle."""
        norm = self._normalize_handle(handle)
        with self._lock:
            return self.profiles.get(norm)

    def get_chatter_context(self, handle: str) -> Optional[str]:
        """Returns a formatted context snippet for prompt injection if profile exists."""
        p = self.get_profile(handle)
        if not p:
            return None
        return p.generate_context_snippet()

    def _extract_topics(self, profile: ChatterProfile, message: str):
        """Extracts notable topic keywords from incoming chatter text."""
        keywords = [
            "consciousness", "enlightenment", "simulation", "matrix", "meditation",
            "grief", "death", "love", "loneliness", "peace", "free will", "ego",
            "purpose", "meaning", "suffering", "universe", "time", "anxiety",
            "coding", "ai", "god", "zen", "crystals", "karma", "dreams"
        ]
        msg_lower = message.lower()
        for kw in keywords:
            if kw in msg_lower and kw not in profile.topics_discussed:
                profile.topics_discussed.append(kw)
                if len(profile.topics_discussed) > 12:
                    profile.topics_discussed.pop(0)
