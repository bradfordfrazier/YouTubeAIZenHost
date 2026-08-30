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
            parts.append("Synthetic Cast Member")
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
        self.profiles: Dict[str, ChatterProfile] = {}
        self._load()

    @classmethod
    def get_instance(cls, db_path: str = "data/chatter_db.json") -> "ChatterDB":
        with cls._lock:
            if cls._instance is None:
                cls._instance = ChatterDB(db_path=db_path)
            return cls._instance

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
                    return
                except Exception as e:
                    logger.warning(f"Error loading ChatterDB from {self.db_path}: {e}")

            # Pre-seed cast members
            self._preseed_cast()
            self._save_unlocked()

    def _preseed_cast(self):
        """Pre-seeds initial profiles for the 6 canonical cast archetypes."""
        now_iso = datetime.now().isoformat()
        cast_seeds = [
            ("ExistentialDave", "Existential Dave", "Overthinking IT Specialist", ["IT", "Jira", "free will", "server room crisis"], "Senior sysadmin having an ongoing non-dual crisis."),
            ("SpeedrunnerKyle", "Speedrunner Kyle", "Enlightenment Speedrunner", ["speedrunning", "samsara", "Any% route", "frame-perfect peace"], "Gamer attempting to glitch past dualistic suffering."),
            ("AstralBrenda", "Astral Brenda", "Esoteric Crystal Enthusiast", ["amethyst", "Mercury retrograde", "5G chakras", "tarot"], "Devoted crystal collector seeking esoteric shortcuts."),
            ("TrollChad", "Troll Chad", "Cosmic Provocateur", ["burrito microwave", "cereal soup", "meme dilemmas", "hot dog buns"], "Internet provocateur testing the machine with absurd questions."),
            ("HeartfeltSarah", "Heartfelt Sarah", "Earnest Seeker", ["grief", "loss", "loneliness", "healing", "unworthy feelings"], "Tender human seeking real comfort and existential presence."),
            ("CuriousTimmy", "Curious Timmy", "Childlike Inquirer", ["lamp darkness", "pre-birth self", "dream nature", "talking trees"], "Innocent child whose simple inquiries dismantle ego complexity."),
        ]
        for handle, name, title, topics, note in cast_seeds:
            norm = self._normalize_handle(handle)
            if norm not in self.profiles:
                self.profiles[norm] = ChatterProfile(
                    handle=handle,
                    display_name=name,
                    first_seen_iso=now_iso,
                    last_seen_iso=now_iso,
                    visit_count=1,
                    message_count=1,
                    is_member=False,
                    is_cast=True,
                    topics_discussed=topics,
                    notes=[f"Archetype: {title}. {note}"],
                )

    def _save_unlocked(self):
        """Writes in-memory profiles to disk atomically."""
        try:
            temp_path = self.db_path.with_suffix(".tmp")
            out_data = {k: v.to_dict() for k, v in self.profiles.items()}
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(out_data, f, indent=2, ensure_ascii=False)
            temp_path.replace(self.db_path)
        except Exception as e:
            logger.warning(f"Failed to persist ChatterDB to {self.db_path}: {e}")

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

        with self._lock:
            if norm in self.profiles:
                p = self.profiles[norm]
                p.display_name = display_name or p.display_name
                p.last_seen_iso = now_iso
                p.message_count += 1
                if is_member:
                    p.is_member = True
                if is_cast:
                    p.is_cast = True
                if session_id and p.last_session_id != session_id:
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
                    is_cast=is_cast,
                    last_session_id=session_id,
                )
                self.profiles[norm] = p

            # Extract basic significant topics/keywords
            self._extract_topics(p, message)
            self._save_unlocked()
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
                    self._save_unlocked()

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
