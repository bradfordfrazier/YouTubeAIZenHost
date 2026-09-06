"""
All-Local Live Stream AI Host Pipeline ("I Am").
Consolidated application running solely on the OBS Host machine.
Integrates OBS Studio WebSocket, YouTube Live Chat, Google Gemini LLM,
neural 48kHz TTS synthesis, 1080p60 Pygame visualizer, and local NDI broadcasting.
"""

import asyncio
import collections
from dataclasses import dataclass, field
import heapq
import json
import logging
import os
import random
import re
import signal
import socket
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np

from ai_brain import AIBrain
from cast_engine import CastEngine
from config import config
from greeting_cache import GreetingCache
from ndi_streamer import NDIStreamer
from render_worker import VisualizerProxy
from session_log import SessionLogger
from tts_engine import TTSEngine
from turn_guard import run_guarded_turn
from visualizer import Visualizer

# Optional imports with graceful fallbacks
try:
    import pytchat
except ImportError:
    pytchat = None

try:
    from obswebsocket import obsws, requests as obs_requests, events as obs_events
except ImportError:
    obsws = None

try:
    import sounddevice as sd
except ImportError:
    sd = None


def resolve_wasapi_output_device(target_name_or_index=None) -> Optional[int]:
    """
    Resolves the best Windows WASAPI output device for OBS Window/Application Audio Capture.
    Prefers native WASAPI (hostapi 2) over legacy MME (hostapi 0) so OBS can capture process audio.
    """
    if sd is None:
        return None
    try:
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()

        # 1. If explicit integer index or string name provided
        if target_name_or_index is not None:
            raw = str(target_name_or_index).strip()
            if raw.isdigit():
                idx = int(raw)
                if 0 <= idx < len(devices) and devices[idx]["max_output_channels"] > 0:
                    return idx
            elif raw.lower() not in ("", "default", "auto"):
                # Search by substring match in WASAPI first
                for idx, dev in enumerate(devices):
                    if dev["max_output_channels"] > 0:
                        api_name = hostapis[dev["hostapi"]]["name"]
                        if "wasapi" in api_name.lower() and raw.lower() in dev["name"].lower():
                            return idx
                # Search in all devices
                for idx, dev in enumerate(devices):
                    if dev["max_output_channels"] > 0 and raw.lower() in dev["name"].lower():
                        return idx

        # 2. Find WASAPI default output device
        for api in hostapis:
            if "wasapi" in api["name"].lower():
                def_out = api.get("default_output_device", -1)
                if def_out >= 0 and devices[def_out]["max_output_channels"] > 0:
                    return def_out

        # 3. Fallback to DirectSound
        for api in hostapis:
            if "directsound" in api["name"].lower():
                def_out = api.get("default_output_device", -1)
                if def_out >= 0 and devices[def_out]["max_output_channels"] > 0:
                    return def_out

        # 4. Global default
        def_dev = sd.query_devices(kind="output")
        return def_dev["index"] if def_dev else None
    except Exception as e:
        logger.debug(f"Error resolving WASAPI device: {e}")
        return None


def print_audio_devices():
    """Prints all available audio output devices and their host APIs."""
    if sd is None:
        print("[ERROR] sounddevice is not installed. Install with: pip install sounddevice")
        return
    print("=" * 65)
    print("AVAILABLE WINDOWS AUDIO OUTPUT DEVICES")
    print("=" * 65)
    devices = sd.query_devices()
    hostapis = sd.query_hostapis()
    for idx, dev in enumerate(devices):
        if dev["max_output_channels"] > 0:
            api_name = hostapis[dev["hostapi"]]["name"]
            is_wasapi = "WASAPI" in api_name.upper()
            tag = " [RECOMMENDED FOR OBS]" if is_wasapi else ""
            print(f"  [{idx:2d}] {dev['name']:<42} | API: {api_name:<18}{tag}")
    print("=" * 65)
from logging_setup import configure_logging

logger = logging.getLogger("app")

# Enable 1ms high-resolution timer and elevated process priority on Windows for glitch-free streaming
if sys.platform == "win32":
    try:
        import ctypes
        from ctypes import wintypes
        ctypes.windll.winmm.timeBeginPeriod(1)

        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.SetPriorityClass.restype = wintypes.BOOL

        pri_str = config.process_priority.lower()
        pri_code = 0x00000080 if pri_str == "high" else 0x00008000
        kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), pri_code)
        logger.info(f"Enabled Windows 1ms timer and {pri_str.upper()} process priority for smooth audio.")
    except Exception as e:
        logger.debug(f"Could not set Windows timer/priority: {e}")


def probe_tcp_port(host: str, port: int, timeout: float = 0.15) -> bool:
    """Quickly probes if a target TCP host and port are actively listening without hanging the event loop."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
            return True
    except Exception:
        return False


def extract_youtube_video_id(url_or_id: str) -> str:
    """Extracts or resolves the 11-character YouTube video ID from various URL formats, channel links, or raw ID."""
    raw = url_or_id.strip()
    if not raw:
        return ""

    patterns = [
        r"(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]{11})",
        r"(?:https?:\/\/)?(?:www\.)?youtube\.com\/live\/([a-zA-Z0-9_-]{11})",
        r"(?:https?:\/\/)?youtu\.be\/([a-zA-Z0-9_-]{11})",
        r"(?:https?:\/\/)?(?:www\.)?youtube\.com\/embed\/([a-zA-Z0-9_-]{11})",
        r"(?:https?:\/\/)?studio\.youtube\.com\/video\/([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, raw)
        if m:
            return m.group(1)

    if re.match(r"^[a-zA-Z0-9_-]{11}$", raw):
        return raw

    # Channel handle or channel URL auto-resolution: e.g. @MyChannel or https://www.youtube.com/@MyChannel
    if "@" in raw or "youtube.com/channel/" in raw or "youtube.com/c/" in raw or "youtube.com/user/" in raw:
        live_url = raw
        if not live_url.startswith("http"):
            live_url = f"https://www.youtube.com/{live_url}"
        if not live_url.endswith("/live"):
            live_url = live_url.rstrip("/") + "/live"

        try:
            req = urllib.request.Request(
                live_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                final_url = resp.geturl()
                html = resp.read().decode("utf-8", errors="ignore")

            m_can = re.search(r'<link rel="canonical" href="https://www\.youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})"', html)
            if m_can:
                return m_can.group(1)

            m_og = re.search(r'<meta property="og:url" content="https://www\.youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})"', html)
            if m_og:
                return m_og.group(1)

            if "watch?v=" in final_url:
                vid = final_url.split("v=")[1].split("&")[0]
                if len(vid) == 11:
                    return vid

            if "/live/" in final_url and not final_url.endswith("/live"):
                vid = final_url.split("/live/")[1].split("?")[0]
                if len(vid) == 11:
                    return vid

            m_vid = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
            if m_vid:
                return m_vid.group(1)

        except Exception as e:
            logger.debug(f"Live channel query note for '{live_url}': {e}")

        return ""

    return ""


def fetch_youtube_live_viewers(video_id_or_url: str, api_key: str = "") -> Optional[int]:
    """
    Queries YouTube for real-time live concurrent viewer count.
    1. First attempts official YouTube Data API v3 videos.list endpoint.
    2. If API key is unavailable or quota exceeded, falls back to scraping live player metadata.
    """
    raw = video_id_or_url.strip()
    if not raw:
        return None

    vid = ""
    if len(raw) == 11 and not ("/" in raw or "@" in raw or "?" in raw):
        vid = raw
    elif "watch?v=" in raw:
        m = re.search(r"watch\?v=([a-zA-Z0-9_-]{11})", raw)
        if m:
            vid = m.group(1)
    elif "youtu.be/" in raw:
        m = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", raw)
        if m:
            vid = m.group(1)
    elif "/live/" in raw and not raw.endswith("/live"):
        m = re.search(r"/live/([a-zA-Z0-9_-]{11})", raw)
        if m:
            vid = m.group(1)

    if not vid and ("@" in raw or "youtube.com/" in raw):
        vid = extract_youtube_video_id(raw)

    if not vid:
        return None

    # 1. Primary: YouTube Data API v3
    if api_key:
        url = f"https://www.googleapis.com/youtube/v3/videos?part=liveStreamingDetails&id={vid}&key={api_key}"
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "YouTubeAIHost/1.0", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("items", [])
                if items:
                    live_details = items[0].get("liveStreamingDetails", {})
                    concurrent_str = live_details.get("concurrentViewers")
                    if concurrent_str is not None:
                        count = int(concurrent_str)
                        logger.info(f"🔑 [YouTube Data API] Concurrent Viewers detected: {count}")
                        return count
                    else:
                        logger.info("🔑 [YouTube Data API] Broadcast is LIVE with 0 viewers.")
                        return 0
        except Exception as e:
            logger.debug(f"[YouTube Data API] Query note for '{vid}': {e}. Falling back to web scraper...")

    # 2. Fallback: Public Live Stream Web Scraper
    try:
        watch_url = f"https://www.youtube.com/watch?v={vid}"
        scrape_req = urllib.request.Request(
            watch_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(scrape_req, timeout=5) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        m1 = re.search(r'"viewCount":\{"runs":\[\{"text":"([0-9,]+)"\},\{"text":"\s*watching', html)
        if m1:
            count = int(m1.group(1).replace(",", ""))
            logger.info(f"🌐 [YouTube Web Scraper] Concurrent Viewers detected: {count}")
            return count

        m2 = re.search(r'"viewCountText":\{"runs":\[\{"text":"([0-9,]+)"\},\{"text":"\s*watching', html)
        if m2:
            count = int(m2.group(1).replace(",", ""))
            logger.info(f"🌐 [YouTube Web Scraper] Concurrent Viewers detected: {count}")
            return count

        if '"isLive":true' in html or '"isLiveBroadcast":true' in html:
            logger.info("🌐 [YouTube Web Scraper] Broadcast is LIVE with 0 viewers.")
            return 0

        return 0
    except Exception as e:
        logger.warning(f"[YouTube Viewer Scraper] Could not poll viewer count for '{vid}': {e}")
        return None


def fetch_youtube_live_chat_backlog(video_id: str, api_key: str) -> List[Dict]:
    """
    Fetches recent historical messages from YouTube Live Chat via YouTube Data API v3.
    Enables instant chat restoration on startup/restart when pytchat has no backlog.
    """
    if not video_id or not api_key:
        return []
    try:
        vid_url = f"https://www.googleapis.com/youtube/v3/videos?id={video_id}&key={api_key}&part=liveStreamingDetails"
        req = urllib.request.Request(vid_url, headers={"User-Agent": "YouTubeAIHost/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("items", [])
        if not items:
            return []
        live_details = items[0].get("liveStreamingDetails", {})
        active_chat_id = live_details.get("activeLiveChatId")
        if not active_chat_id:
            return []

        chat_url = f"https://www.googleapis.com/youtube/v3/liveChat/messages?liveChatId={active_chat_id}&key={api_key}&part=id,snippet,authorDetails&maxResults=50"
        req = urllib.request.Request(chat_url, headers={"User-Agent": "YouTubeAIHost/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            chat_data = json.loads(resp.read().decode("utf-8"))

        messages = []
        for item in chat_data.get("items", []):
            author_details = item.get("authorDetails", {})
            snippet = item.get("snippet", {})
            author_name = author_details.get("displayName", "Viewer")
            msg_text = snippet.get("displayMessage", "")
            is_sc = snippet.get("type") == "superChatEvent"
            sc_amount = snippet.get("superChatDetails", {}).get("amountDisplayString", "") if is_sc else ""

            author_type = "viewer"
            if author_details.get("isChatOwner") or author_details.get("isChatBroadcaster"):
                author_type = "owner"
            elif author_details.get("isChatModerator"):
                author_type = "moderator"
            elif author_details.get("isChatSponsor"):
                author_type = "member"

            messages.append({
                "author": author_name,
                "author_type": author_type,
                "message": msg_text,
                "is_superchat": is_sc,
                "amount": sc_amount,
                "timestamp": time.time(),
            })
        return messages
    except Exception as e:
        logger.debug(f"[YouTube Live Chat Backlog] Could not fetch live chat messages: {e}")
        return []


_EVENT_COUNTER = 0


@dataclass
class CommentEvent:
    """Encapsulates an incoming comment trigger with priority and lifespan."""
    prompt_trigger: str
    event_type: str = "chat"  # "superchat", "direct_mention", "greeting", "chat", "cast", "spontaneous"
    priority: int = 4         # Lower number = higher priority (1: Superchat, 2: Mention, 3: Greeting, 4: Chat, 5: Cast, 6: Spontaneous)
    created_at: float = field(default_factory=time.time)
    seq_id: int = 0
    max_age_sec: float = 90.0
    force: bool = False
    chat_item: Optional[Dict[str, Any]] = None
    cached_greeting: Optional[Any] = None

    def __lt__(self, other: "CommentEvent") -> bool:
        if not isinstance(other, CommentEvent):
            return NotImplemented
        return (self.priority, self.created_at, self.seq_id) < (other.priority, other.created_at, other.seq_id)

    def __le__(self, other: "CommentEvent") -> bool:
        if not isinstance(other, CommentEvent):
            return NotImplemented
        return (self.priority, self.created_at, self.seq_id) <= (other.priority, other.created_at, other.seq_id)

    def __gt__(self, other: "CommentEvent") -> bool:
        if not isinstance(other, CommentEvent):
            return NotImplemented
        return (self.priority, self.created_at, self.seq_id) > (other.priority, other.created_at, other.seq_id)

    def __ge__(self, other: "CommentEvent") -> bool:
        if not isinstance(other, CommentEvent):
            return NotImplemented
        return (self.priority, self.created_at, self.seq_id) >= (other.priority, other.created_at, other.seq_id)


class LocalCoHostApp:
    """Consolidated All-Local AI Co-Host Pipeline running on the OBS Host machine."""

    CHAT_CACHE_FILE = Path(__file__).resolve().parent / "chat_cache.json"

    def __init__(self):
        self.cfg = config
        self.running = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        # Core Subsystems
        self.brain = AIBrain()
        self.tts = TTSEngine()
        self.visualizer = VisualizerProxy()
        if isinstance(self.visualizer, VisualizerProxy):
            self.tts.ndi_buffer_enabled = False
            self.tts.ndi_sink = self.visualizer.push_audio_samples
            self.tts.ndi_clear_sink = self.visualizer.clear_audio_buffer
            # Utterance open/closed is announced by the engine itself, AFTER the first chunk is
            # in the ring, so the render worker never sees "utterance open but ring empty".
            self.tts.utterance_state_sink = self.visualizer.set_utterance_state
        self.ndi = NDIStreamer()
        self.session_log = SessionLogger.get_instance(log_dir=self.cfg.session_log_dir) if self.cfg.session_logging_enabled else None
        self.cast = CastEngine()
        self.greeting_cache = GreetingCache.get_instance(max_size=self.cfg.greeting_cache_size)

        # OBS State
        self.obs_client = None
        self.obs_connected = False
        self.is_streaming = False
        self.is_recording = False
        self.current_scene = "Main"

        # Stream & Audience Telemetry
        self.concurrent_viewers = 0
        self.chat_velocity = 0
        self.active_video_id = ""
        self.chat_timestamps: list = []
        self.last_chat_received_time = 0.0
        self.engagement_mode = "eco"
        self.initial_viewer_sync_done = False

        # Activity & Commentary Timers
        self.last_activity_time = time.time()
        self.last_turn_completed_time = 0.0
        self.last_turn_event_type = ""
        self.last_chat_time = 0.0
        self.last_real_chat_time = 0.0
        self.last_spontaneous_time = time.time()
        self.last_chat_encouragement_time = 0.0
        self.last_viewer_join_welcome_time = 0.0
        self.spontaneous_idle_count = 0
        self.encouragement_idle_count = 0

        # Chat & Subtitle State
        self.current_ai_subtitle = ""
        self.current_pinned_chat: Optional[Dict[str, Any]] = None
        self.chat_history: Deque[Dict] = collections.deque(maxlen=50)
        self.seen_chat_handles: set = set()
        self.discovered_channel_handle: Optional[str] = None

        # Restore previous chat messages into visualizer without re-triggering AI commentary
        self._load_cached_chat()

        # Comment Event Priority Queue & Serialized Scheduling
        self.comment_queue: List[CommentEvent] = []
        self.active_turn_event: Optional[CommentEvent] = None
        self.active_turn_task: Optional[asyncio.Task] = None
        # Turn watchdog state: phase label + start time of the currently executing turn
        self.turn_phase: str = "idle"
        self.turn_started_at: float = 0.0
        self.new_comment_signal: Optional[asyncio.Event] = None
        self.ndi_audio_thread: Optional[threading.Thread] = None
        self.ndi_audio_running: bool = False


    def _load_cached_chat(self):
        """Restores recent chat history from disk so visualizer resumes seamlessly on restart without commenting."""
        if not self.CHAT_CACHE_FILE.exists():
            return
        try:
            with open(self.CHAT_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                restored_count = 0
                for item in data[-50:]:
                    if isinstance(item, dict) and "author" in item and "message" in item:
                        msg_text = str(item.get("message", "")).strip()
                        if msg_text.startswith("[") and any(tag in msg_text for tag in ["[VIEWER_JOINED]", "[SPONTANEOUS_REFLECTION]", "[CHAT_ENCOURAGEMENT]", "[NEW_SUBSCRIBER]", "[NEW_MEMBER]", "[CELEBRATION]"]):
                            continue
                        self.chat_history.append(item)
                        # Pre-seed author into seen_chat_handles so returning chatters aren't greeted as brand new
                        author_clean = str(item.get("author", "")).strip().lstrip("@").lower()
                        if author_clean:
                            self.seen_chat_handles.add(author_clean)
                        # Seed AI brain memory for conversational context without generating any speech
                        self.brain.add_chat_message(
                            item.get("author", "Viewer"),
                            item.get("message", ""),
                            item.get("is_superchat", False),
                            item.get("amount", ""),
                        )
                        restored_count += 1
                if restored_count > 0:
                    logger.info(f"📂 [Chat Restore] Restored {restored_count} chat messages from cache into visualizer (silent resume).")
        except Exception as e:
            logger.debug(f"Failed to load chat cache: {e}")

    def _save_cached_chat(self):
        """Persists recent chat history to disk for seamless recovery upon restart (non-blocking)."""
        try:
            items = list(self.chat_history)[-50:]
            def _write():
                try:
                    temp_file = self.CHAT_CACHE_FILE.with_suffix(".tmp")
                    with open(temp_file, "w", encoding="utf-8") as f:
                        json.dump(items, f, indent=2)
                    temp_file.replace(self.CHAT_CACHE_FILE)
                except Exception as e:
                    logger.debug(f"Failed to write chat cache: {e}")

            if self.loop and self.loop.is_running():
                self.loop.run_in_executor(None, _write)
            else:
                _write()
        except Exception as e:
            logger.debug(f"Failed to save chat cache: {e}")

    # --------------------------------------------------------------------------
    # 1. State & Engagement State Management
    # --------------------------------------------------------------------------
    def _wake_up_and_trigger_comment(self, viewers: int, prev_viewers: int = 0):
        """
        Wakes up the system when a viewer enters an empty room (strictly 0 -> 1+).
        Immediately triggers the next scripted comment event and establishes the active cadence.
        """
        if prev_viewers > 0:
            logger.debug(f"Room wake-up bypassed: viewers changed from {prev_viewers} to {viewers} (not an empty room 0 -> 1+ transition).")
            return

        now = time.time()
        cooldown = self.cfg.viewer_join_cooldown_sec
        if (now - self.last_viewer_join_welcome_time) < cooldown:
            logger.debug("Wake-up comment event suppressed by debounce cooldown.")
            return

        self.last_viewer_join_welcome_time = now
        self.last_activity_time = now
        self.last_spontaneous_time = now
        self.spontaneous_idle_count = 0
        self.encouragement_idle_count = 0

        # Transition engagement tier to ACTIVE
        self.engagement_mode = "active"
        self._update_engagement_state()
        should_greet = self.cfg.greet_viewer_joins
        if should_greet:
            chan_handle = self.cfg.youtube_channel_handle
            if viewers == 1:
                prompt = (
                    f"[VIEWER_JOINED] A sole viewer has entered the stream. (Concurrent viewers: 1). "
                    f"Acknowledge their presence directly ('you') with transcendent, charismatic presence on {chan_handle}. "
                    f"Speak to them directly as the sole conscious mind present. Do not ask for chat comments."
                )
            else:
                prompt = (
                    f"[VIEWER_JOINED] New viewer(s) arrived. (Concurrent viewers: {viewers}). "
                    f"Acknowledge the arrival on {chan_handle} with transcendent, charismatic presence. "
                    f"Do not ask for chat comments or plead for engagement."
                )

            cached_greeting = None
            if (
                self.cfg.greeting_cache_enabled
                and hasattr(self, "greeting_cache")
                and self.greeting_cache.has_greeting()
            ):
                cached_greeting = self.greeting_cache.pop_greeting()

            if cached_greeting:
                logger.info(
                    f"⚡ [Room Wake-Up] Viewer entered empty room (0 -> {viewers} active). "
                    f"Dispatched instant pre-synthesized greeting (<5ms latency): '[{cached_greeting.mood.upper()}]: {cached_greeting.full_text}'"
                )
                self.visualizer.fade_out_for_turn()
                self._trigger_ai_turn(
                    prompt_trigger=prompt,
                    event_type="greeting",
                    priority=2,
                    force=False,
                    cached_greeting=cached_greeting,
                )
            else:
                logger.info(f"⚡ [Room Wake-Up] Viewer entered empty room (0 -> {viewers} active). Immediately performing comment event: {prompt}...")
                self.visualizer.fade_out_for_turn()
                self._trigger_ai_turn(prompt_trigger=prompt, event_type="greeting", priority=2, force=False)
        else:
            logger.info(f"⚡ [Room Wake-Up] Viewer entered empty room (0 -> {viewers} active). Room transitioned to ACTIVE.")

    def _on_viewer_count_update(self, new_viewers: int, new_chat_velocity: int = 0):
        """Processes viewer count updates and manages active vs eco engagement transitions."""
        prev_viewers = self.concurrent_viewers
        self.concurrent_viewers = new_viewers
        self.chat_velocity = new_chat_velocity
        now = time.time()
        min_viewers = self.cfg.min_concurrent_viewers_active

        if not self.initial_viewer_sync_done:
            self.initial_viewer_sync_done = True
            logger.info(
                f"📊 [Initial Viewer Sync] Baseline established at {new_viewers} viewers "
                f"(Active threshold: >={min_viewers})."
            )
            self._update_engagement_state()
            return

        is_empty_to_active = (prev_viewers == 0 and new_viewers >= min_viewers)

        if is_empty_to_active:
            logger.info(
                f"⚡ [Wake Up] Viewer entered empty room! (Viewers rose from 0 to {new_viewers}). "
                "Resuming active cadence..."
            )
            self._wake_up_and_trigger_comment(new_viewers, prev_viewers=prev_viewers)

        elif prev_viewers >= min_viewers and new_viewers < min_viewers:
            logger.info(
                f"🌙 [Viewers Dropped to {new_viewers}] Stream below active threshold (<{min_viewers}). "
                "Transitioning to ECO/IDLE mode (preserving API tokens)."
            )
            self.visualizer.set_mood("chill")
            self.spontaneous_idle_count = 0
            self.current_ai_subtitle = ""
            self.visualizer.set_subtitle("")

        self._update_engagement_state()

    def _update_engagement_state(self):
        """
        Calculates current engagement tier:
        - STANDBY: Stream stopped/offline or resting scene (0 unprompted tokens).
        - ECO: Live with 0 viewers (tokens preserved).
        - ACTIVE: Live broadcast with active viewers (full interactive performance).
        """
        now = time.time()
        is_live = self.is_streaming

        scene_lower = self.current_scene.lower().strip()
        is_resting_scene = any(s in scene_lower for s in ["brb", "be right back", "offline", "starting soon", "stream ending", "break"])

        if (self.cfg.obs_require_stream_active and not is_live) or is_resting_scene:
            new_mode = "standby"
        else:
            is_chat_recently_active = (self.last_real_chat_time > 0 and (now - self.last_real_chat_time < self.cfg.chat_idle_timeout_sec))
            has_viewers = (self.concurrent_viewers >= self.cfg.min_concurrent_viewers_active) or is_chat_recently_active
            if has_viewers:
                new_mode = "active"
            else:
                new_mode = "eco" if self.cfg.eco_mode_enabled else "active"

        if new_mode != self.engagement_mode:
            logger.info(
                f"⚡ [Engagement State Transition] {self.engagement_mode.upper()} -> {new_mode.upper()} "
                f"(Live: {is_live}, Viewers: {self.concurrent_viewers}, ChatVelocity: {self.chat_velocity}/min)"
            )
            self.engagement_mode = new_mode

        self.brain.set_engagement_mode(
            mode=self.engagement_mode,
            is_stream_live=is_live,
            concurrent_viewers=self.concurrent_viewers,
            is_chat_active=(now - self.last_chat_time < self.cfg.chat_idle_timeout_sec),
        )

    # --------------------------------------------------------------------------
    # 2. AI Brain & Speech Generation Dispatcher (Priority Queue & Serialized Scheduling)
    # --------------------------------------------------------------------------
    def _trigger_ai_turn(
        self,
        prompt_trigger: Optional[str] = None,
        event_type: str = "chat",
        priority: Optional[int] = None,
        max_age_sec: Optional[float] = None,
        force: bool = False,
        chat_item: Optional[Dict] = None,
        cached_greeting: Optional[Any] = None,
    ):
        """Thread-safe and async-safe enqueueing of AI comment turns with priority and backpressure."""
        if not prompt_trigger or not self.running:
            return

        # Default priorities & TTLs based on event type:
        # Tier 1: Superchats / Memberships (Priority 1) -> Paid audience acknowledgment
        # Tier 2: Real Viewer Direct Mentions (Priority 2) -> High-priority viewer engagement
        # Tier 3: Greetings (Priority 3) -> Pre-synthesized or live greetings
        # Tier 4: Real Live Chat (Priority 4) -> Strict FIFO human chat feed
        # Tier 5: Synthetic Cast Ensembles (Priority 5) -> Idle ensemble filler (yields to humans)
        # Tier 6: Spontaneous Reflections / System (Priority 6) -> Idle background reflections
        priority_map = {
            "superchat": (1, 180.0),
            "direct_mention": (2, 90.0),
            "greeting": (3, 90.0),
            "chat": (4, 90.0),
            "cast": (5, 90.0),
            "spontaneous": (6, 30.0),
            "system": (6, 30.0),
        }
        def_pri, def_ttl = priority_map.get(event_type.lower(), (4, 90.0))
        prio = priority if priority is not None else def_pri
        ttl = max_age_sec if max_age_sec is not None else def_ttl

        # Spontaneous Gating: Never queue spontaneous reflections if AI is busy speaking, generating, or queue is active
        if event_type in ("spontaneous", "system"):
            is_busy = (
                self.brain.is_generating
                or self.tts.is_speaking
                or self.tts.remaining_speech_duration > 0.05
                or self.active_turn_event is not None
                or len(self.comment_queue) > 0
            )
            if is_busy:
                logger.debug("Suppressing spontaneous commentary: stream or AI queue is active.")
                return

        global _EVENT_COUNTER
        _EVENT_COUNTER += 1

        event = CommentEvent(
            prompt_trigger=prompt_trigger,
            event_type=event_type,
            priority=prio,
            created_at=time.time(),
            seq_id=_EVENT_COUNTER,
            max_age_sec=ttl,
            force=force,
            chat_item=chat_item,
            cached_greeting=cached_greeting,
        )

        if force:
            if self.active_turn_task and not self.active_turn_task.done():
                self.active_turn_task.cancel()
            self.tts.clear_audio_buffer()
            event.priority = 0
            heapq.heappush(self.comment_queue, event)
            if self.new_comment_signal:
                self.new_comment_signal.set()
            logger.info(f"⚡ [Forced AI Turn] Dispatched immediate interrupt for: '{prompt_trigger[:60]}...'")
            return

        # Backpressure & Queue Overflow Management (Max queue size)
        max_queue = int(self.cfg.max_comment_queue_size)
        if len(self.comment_queue) >= max_queue:
            # Find lowest-priority item (largest priority tuple)
            lowest_item = max(self.comment_queue)

            # Real human events (prio <= 4) always evict synthetic cast (prio >= 5) or idle reflections
            if event < lowest_item or (prio <= 4 and lowest_item.priority >= 5):
                self.comment_queue.remove(lowest_item)
                heapq.heapify(self.comment_queue)
                heapq.heappush(self.comment_queue, event)
                logger.info(f"⚠️ [Queue Eviction] Evicted lower-priority '{lowest_item.event_type}' request to prioritize incoming '{event_type}'.")
            else:
                logger.info(f"🛑 [Queue Full] Dropped '{event_type}' request ('{prompt_trigger[:45]}...') to prevent response latency backlog.")
                return
        else:
            heapq.heappush(self.comment_queue, event)

        if self.new_comment_signal:
            self.new_comment_signal.set()
        logger.info(f"📥 [Queued Comment] Added '{event_type}' (Pri: {prio}, Seq: {_EVENT_COUNTER}, Queue: {len(self.comment_queue)}): '{prompt_trigger[:60]}...'")

    async def comment_queue_scheduler_task(self):
        """
        Dedicated sequential comment scheduler task (Phase 3.3).
        Executes one AI speech turn at a time using a min-heap priority queue,
        strictly waiting for complete audio playback before proceeding to next event.
        """
        logger.info("🧠 [Comment Scheduler] Serialized AI turn scheduler active (Heap Priority Queue).")
        if self.new_comment_signal is None:
            self.new_comment_signal = asyncio.Event()

        while self.running:
            try:
                # Prune stale events from queue before taking the next one
                now = time.time()
                valid_queue = [ev for ev in self.comment_queue if now - ev.created_at <= ev.max_age_sec]
                if len(valid_queue) != len(self.comment_queue):
                    pruned_count = len(self.comment_queue) - len(valid_queue)
                    heapq.heapify(valid_queue)
                    self.comment_queue = valid_queue
                    logger.info(f"⏱️ [Stale Request Pruned] Pruned {pruned_count} stale queue event(s) to keep AI real-time.")

                if not self.comment_queue:
                    self.new_comment_signal.clear()
                    try:
                        await asyncio.wait_for(self.new_comment_signal.wait(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    continue

                # Pop highest priority event (lowest priority tuple)
                event = heapq.heappop(self.comment_queue)
                self.active_turn_event = event
                self.active_turn_task = asyncio.current_task()

                # Execute full sequential turn under a hard timeout so a stuck turn can never
                # block the scheduler (cast, reflections, chat replies) indefinitely.
                await run_guarded_turn(
                    self._execute_ai_turn(event),
                    timeout_sec=float(self.cfg.turn_max_sec),
                    phase_getter=lambda: self.turn_phase,
                    on_timeout=self._recover_from_stuck_turn,
                    label=f"Turn '{event.event_type}'",
                )
                self.turn_phase = "idle"

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in comment queue scheduler: {e}", exc_info=True)
                await asyncio.sleep(0.5)
            finally:
                self.active_turn_event = None

    async def _execute_ai_turn(self, event: CommentEvent):
        """Executes a single cohesive AI speech turn from start to full audio completion."""
        t_start = time.perf_counter()
        logger.info(f"🎙️ [Turn Started] Processing '{event.event_type}' comment: '{event.prompt_trigger[:60]}...'")
        self.turn_phase = "start"
        self.turn_started_at = time.time()
        consumer_task: Optional[asyncio.Task] = None

        # Mark live turn active for GPU exclusivity and reset underrun counters
        self.tts.live_turn_active.set()
        self.tts.underrun_count = 0
        self.tts.underrun_samples = 0

        # Set active pinned chat question during turn
        if getattr(event, "chat_item", None):
            self.current_pinned_chat = event.chat_item
        elif event.event_type in ("chat", "superchat", "direct_mention", "cast", "greeting"):
            # Internal bracketed system instructions must NEVER be treated as chat questions
            if event.prompt_trigger.strip().startswith("["):
                self.current_pinned_chat = None
            else:
                m_auth = re.search(r"@([a-zA-Z0-9_-]+)", event.prompt_trigger)
                author_name = m_auth.group(1) if m_auth else ""
                q_text = event.prompt_trigger
                if ": '" in event.prompt_trigger:
                    q_text = event.prompt_trigger.split(": '", 1)[1].rstrip("'\"").strip()
                elif ': "' in event.prompt_trigger:
                    q_text = event.prompt_trigger.split(': "', 1)[1].rstrip("'\"").strip()

                matched = None
                if author_name:
                    # First pass: match both author and message in chronological order (FIFO)
                    for ch in self.chat_history:
                        ch_auth = ch.get("author", "").strip().lower().lstrip("@")
                        if ch_auth == author_name.lower().lstrip("@"):
                            ch_msg = ch.get("message", "").strip()
                            if q_text and (q_text in ch_msg or ch_msg in q_text):
                                matched = ch
                                break
                    # Second pass fallback: match author in chronological order (FIFO)
                    if not matched:
                        for ch in self.chat_history:
                            ch_auth = ch.get("author", "").strip().lower().lstrip("@")
                            if ch_auth == author_name.lower().lstrip("@"):
                                matched = ch
                                break

                self.current_pinned_chat = matched
        else:
            self.current_pinned_chat = None

        if self.current_pinned_chat:
            self.visualizer.set_pinned(self.current_pinned_chat)
        else:
            self.visualizer.clear_pinned()

        # 1. Immediately fade out motto / previous comment to clear canvas for the upcoming turn
        self.visualizer.fade_out_for_turn()
        self.current_ai_subtitle = ""

        # Ensure active question is present in live chat feed (appended to bottom if not already present)
        # Only valid viewer/cast chat items (never internal bracketed system prompts) should be in feed
        if self.current_pinned_chat:
            p_author = self.current_pinned_chat.get("author", "").strip()
            p_msg = self.current_pinned_chat.get("message", "").strip()
            if p_author and p_msg and not p_msg.startswith("["):
                if not any(
                    e.get("author", "").strip().lower().lstrip("@") == p_author.lower().lstrip("@")
                    and (e.get("message", "").strip() == p_msg or p_msg in e.get("message", "").strip() or e.get("message", "").strip() in p_msg)
                    for e in self.chat_history
                ):
                    self.chat_history.append(dict(self.current_pinned_chat))
                    self._save_cached_chat()

        # Calculate minimum reading duration for the question (min display floor or word count * rate)
        question_text = self.current_pinned_chat.get("message", "") if self.current_pinned_chat else ""
        if question_text:
            word_count = len(question_text.split())
            min_display_sec = self.cfg.question_min_display_sec
            rate_sec = self.cfg.question_read_word_rate_sec
            min_display_hold_sec = max(min_display_sec, word_count * rate_sec)
            q_fade_in_sec = self.cfg.question_fade_in_sec
            q_fade_out_sec = self.cfg.question_fade_out_sec
            min_time_before_fade_out = q_fade_in_sec + min_display_hold_sec
        else:
            min_display_hold_sec = 0.0
            q_fade_in_sec = 0.0
            q_fade_out_sec = 0.0
            min_time_before_fade_out = 0.0

        t_question_shown = time.perf_counter()

        full_statement = ""
        is_completed = False
        active_mood = "energetic"
        cached_g = getattr(event, "cached_greeting", None)
        clean_speech = ""
        pushed_chunks = 0
        first_token_ts: Optional[float] = None
        first_sentence_ts: Optional[float] = None
        first_audio_ts: Optional[float] = None

        try:
            if cached_g and cached_g.audio is not None and len(cached_g.audio) > 0:
                # Instant Greeting Cache Hit: Zero-Latency pre-synthesized speech execution (<5ms / 0.0s TTFT & TTS)
                full_statement = cached_g.full_text
                clean_speech = cached_g.full_text
                active_mood = cached_g.mood
                self.visualizer.set_mood(active_mood)
                is_completed = True
                dur_sec = len(cached_g.audio) / 48000.0

                if question_text:
                    logger.info("🎙️ Keeping active chat question steadily displayed in center comment card during speech playback.")

                self.tts.begin_utterance()
                first_audio_ts = time.perf_counter()
                self.tts.push_audio(cached_g.audio)
                self.tts.end_utterance()
                pushed_chunks = 1

                logger.info(
                    f"⚡ [Instant AI Speech] Broadcasting pre-synthesized greeting audio "
                    f"([{active_mood.upper()}], {dur_sec:.2f}s audio, 0.0s TTFT & TTS): '{clean_speech}'..."
                )
                self.turn_phase = "wait_complete"
                await self.tts.wait_until_speech_completed()
            else:
                # 3. Stream from Gemini AI Brain with sentence pipelining & adaptive lead buffer (Phase 2.4 & Underrun Fix)
                sentence_queue: asyncio.Queue = asyncio.Queue()
                buffered_synthesized_chunks: List[Tuple[np.ndarray, bool]] = []  # (audio, beat_before)
                first_push_done = False
                pending_queue_chars = 0

                async def _tts_consumer():
                    nonlocal pushed_chunks, first_audio_ts, active_mood, first_push_done, pending_queue_chars
                    gate_deferred_by_hold = False  # lead satisfied but question hold not yet elapsed
                    while True:
                        if gate_deferred_by_hold:
                            # Wake up when the hold expires so playback is not delayed until the
                            # next sentence (or the sentinel) happens to arrive.
                            remaining_hold = max(0.0, min_time_before_fade_out - (time.perf_counter() - t_question_shown))
                            try:
                                item = await asyncio.wait_for(sentence_queue.get(), timeout=remaining_hold + 0.01)
                            except asyncio.TimeoutError:
                                item = "__HOLD_EXPIRED__"
                        else:
                            item = await sentence_queue.get()
                        if item == "__HOLD_EXPIRED__":
                            item = None  # evaluate the gate with no new audio; not a sentinel
                            hold_tick = True
                        else:
                            hold_tick = False
                        if item is not None:
                            sent_text, sent_mood, sent_beat = item
                            pending_queue_chars = max(0, pending_queue_chars - len(sent_text))
                            self.turn_phase = "synth"
                            s_audio = await self.tts.synthesize(
                                sent_text, mood=sent_mood, is_live=True, _from_live_turn=True
                            )

                            if s_audio is not None and len(s_audio) > 0:
                                if first_push_done:
                                    # Subsequent chunks push immediately as they finish
                                    self.tts.push_audio(s_audio, beat_before=sent_beat)
                                    pushed_chunks += 1
                                else:
                                    buffered_synthesized_chunks.append((s_audio, sent_beat))

                        # Check adaptive lead buffer start condition
                        if not first_push_done:
                            self.turn_phase = "lead_gate"
                            buffered_audio_sec = sum(len(c) for c, _ in buffered_synthesized_chunks) / self.tts.sample_rate

                            # Calculate pending characters in queue using producer-maintained counter
                            queue_chars = pending_queue_chars
                            # Sentences not yet received from Gemini count as one average sentence (capped at 3 pending sentences)
                            pending_unreceived = 1 if not is_completed else 0
                            pending_chars = queue_chars + (pending_unreceived * int(self.cfg.tts_avg_sentence_chars))

                            rtf_cons = self.tts.rtf_conservative
                            est_remaining_synth_sec = (pending_chars * float(self.cfg.tts_sec_per_char)) / max(0.5, rtf_cons)
                            lead_safety = float(self.cfg.lead_safety)
                            target_lead_sec = est_remaining_synth_sec * lead_safety

                            is_sentinel = (item is None) and not hold_tick
                            lead_satisfied = (buffered_audio_sec >= target_lead_sec) or is_sentinel

                            # Check question display hold
                            q_elapsed = time.perf_counter() - t_question_shown
                            display_hold_satisfied = (q_elapsed >= min_time_before_fade_out)
                            gate_deferred_by_hold = lead_satisfied and not display_hold_satisfied

                            if lead_satisfied and display_hold_satisfied and len(buffered_synthesized_chunks) > 0:
                                logger.info(
                                    f"[TTS LEAD] starting playback with {buffered_audio_sec:.1f}s buffered, "
                                    f"est. remaining synth {est_remaining_synth_sec:.1f}s (rtf {rtf_cons:.2f})"
                                )
                                self.tts.begin_utterance()
                                if first_audio_ts is None:
                                    first_audio_ts = time.perf_counter()
                                if question_text:
                                    logger.info("🎙️ Keeping active chat question steadily displayed in center comment card during speech playback.")

                                self.turn_phase = "push"
                                for chunk, chunk_beat in buffered_synthesized_chunks:
                                    self.tts.push_audio(chunk, beat_before=chunk_beat)
                                    pushed_chunks += 1
                                buffered_synthesized_chunks.clear()
                                first_push_done = True

                        if hold_tick:
                            continue
                        if item is None:
                            # Final drain check on sentinel
                            if not first_push_done and len(buffered_synthesized_chunks) > 0:
                                buffered_audio_sec = sum(len(c) for c, _ in buffered_synthesized_chunks) / self.tts.sample_rate
                                logger.info(f"[TTS LEAD] starting playback on turn completion with {buffered_audio_sec:.1f}s buffered")
                                self.tts.begin_utterance()
                                if first_audio_ts is None:
                                    first_audio_ts = time.perf_counter()
                                for chunk, chunk_beat in buffered_synthesized_chunks:
                                    self.tts.push_audio(chunk, beat_before=chunk_beat)
                                    pushed_chunks += 1
                                buffered_synthesized_chunks.clear()
                                first_push_done = True

                            sentence_queue.task_done()
                            break

                        sentence_queue.task_done()

                    self.tts.end_utterance()

                consumer_task = asyncio.create_task(_tts_consumer())

                # Optionally read the question aloud first. It goes on the queue BEFORE Gemini
                # produces anything, so it synthesizes in parallel with generation; the first
                # answer chunk then gets a beat so the question and the answer don't run together.
                force_beat_on_first_answer = False
                intro_text = self._question_read_aloud_text(event)
                if intro_text:
                    pending_queue_chars += len(intro_text)
                    await sentence_queue.put((intro_text, self.cfg.read_question_mood, False))
                    force_beat_on_first_answer = True
                    logger.info(f"🗣️ [Read Question] '{intro_text[:80]}'")

                self.turn_phase = "gemini"
                async for chunk_ev in self.brain.generate_response_stream(
                    event.prompt_trigger, name_already_spoken=bool(intro_text)
                ):
                    ev_type = chunk_ev.get("type", "")
                    if ev_type == "mood":
                        active_mood = chunk_ev.get("mood", "chill")
                        self.visualizer.set_mood(active_mood)
                    elif ev_type == "token":
                        if first_token_ts is None:
                            first_token_ts = time.perf_counter()
                    elif ev_type == "sentence":
                        if first_sentence_ts is None:
                            first_sentence_ts = time.perf_counter()
                        # Brain yields the sentence under "text" (older builds used "sentence").
                        sent = (chunk_ev.get("text") or chunk_ev.get("sentence") or "").strip()
                        sent_mood = chunk_ev.get("mood", active_mood)
                        sent_beat = bool(chunk_ev.get("beat_before", False)) or force_beat_on_first_answer
                        if sent:
                            force_beat_on_first_answer = False
                            clean_sent = re.sub(r"@+", "@", sent).strip()
                            pending_queue_chars += len(clean_sent)
                            await sentence_queue.put((clean_sent, sent_mood, sent_beat))
                    elif ev_type == "complete":
                        full_statement = chunk_ev.get("full_text", "").strip()
                        active_mood = chunk_ev.get("mood", active_mood)
                        is_completed = True

                await sentence_queue.put(None)
                self.turn_phase = "await_consumer"
                await consumer_task
                consumer_task = None

                clean_speech = re.sub(r"@+", "@", full_statement).strip()

                # Fallback: if no sentences were produced but full statement exists
                if pushed_chunks == 0 and is_completed and clean_speech:
                    self.turn_phase = "synth"
                    s_audio = await self.tts.synthesize(
                        clean_speech, mood=active_mood, is_live=True, _from_live_turn=True
                    )

                    if s_audio is not None and len(s_audio) > 0:
                        if first_audio_ts is None:
                            first_audio_ts = time.perf_counter()
                        self.tts.begin_utterance()
                        self.tts.push_audio(s_audio)
                        self.tts.end_utterance()
                        pushed_chunks = 1

                if pushed_chunks > 0:
                    self.turn_phase = "wait_complete"
                    await self.tts.wait_until_speech_completed()

            if pushed_chunks > 0 and clean_speech:
                t_total = time.perf_counter() - t_start
                ttft_ms = ((first_token_ts - t_start) * 1000) if first_token_ts else 0.0
                ttfs_ms = ((first_sentence_ts - t_start) * 1000) if first_sentence_ts else 0.0
                ttfa_ms = ((first_audio_ts - t_start) * 1000) if first_audio_ts else 0.0
                underrun_ms = (self.tts.underrun_samples / self.tts.sample_rate) * 1000.0
                logger.info(
                    f"⏱️ [Turn Timing] TTFT: {ttft_ms:.0f}ms | TTFS: {ttfs_ms:.0f}ms | TTFA: {ttfa_ms:.0f}ms | "
                    f"Total Turn Time: {t_total:.2f}s | underruns={self.tts.underrun_count} underrun_ms={underrun_ms:.1f}ms "
                    f"(Mood: [{active_mood.upper()}], Chunks: {pushed_chunks})"
                )
                logger.info(f"✅ [Turn Completed] Speech playback finished cleanly ({t_total:.2f}s total turn time).")

                # Record turn to in-session conversational thread memory (C2)
                m_auth = re.search(r"@([a-zA-Z0-9_-]+)", event.prompt_trigger)
                author_name = m_auth.group(1) if m_auth else ""
                self.brain.record_completed_turn(
                    trigger=event.prompt_trigger,
                    full_text=clean_speech,
                    mood=active_mood,
                    author=author_name,
                )

                # Structured Session Log
                if self.session_log:
                    exag_map = self.cfg.tts_mood_exaggeration_map
                    exaggeration = exag_map.get(active_mood.lower(), self.cfg.tts_exaggeration_default)
                    self.session_log.log_ai_turn(
                        trigger=event.prompt_trigger,
                        event_type=event.event_type,
                        full_text=clean_speech,
                        mood=active_mood,
                        exaggeration=exaggeration,
                        tts_backend=self.cfg.tts_backend,
                        turn_latency_sec=t_total,
                        audio_duration_sec=getattr(self.tts, "last_synthesized_duration", 0.0),
                        author=author_name or event.prompt_trigger[:40],
                        is_cast=(event.event_type == "cast"),
                        concurrent_viewers=self.concurrent_viewers,
                    )

                # Dynamic Queue-Aware Post-Speech Hold:
                is_spontaneous = (event.event_type == "spontaneous")

                if is_spontaneous:
                    # After a spontaneous reflection finishes speaking:
                    # Hold in serene silence/stillness for reflection_post_speech_chat_delay_sec (default 3.0s)
                    # before allowing ANY next sequence (chat question or motto) to emerge.
                    refl_delay = float(self.cfg.reflection_post_speech_chat_delay_sec)
                    logger.info(f"⏳ [Post-Reflection Hold] Holding peaceful stillness for {refl_delay:.1f}s after reflection (Queue: {len(self.comment_queue)})...")
                    t_hold_start = time.perf_counter()
                    try:
                        while time.perf_counter() - t_hold_start < refl_delay:
                            await asyncio.sleep(0.05)
                    except asyncio.CancelledError:
                        pass

                    has_queued_next = len(self.comment_queue) > 0
                    if has_queued_next:
                        logger.info(f"✨ [Direct Turn Transition] Proceeding directly to next queued comment ({len(self.comment_queue)} pending) without motto.")
                    else:
                        logger.info(f"✨ [Motto Transition] {refl_delay:.1f}s post-reflection pause finished with empty queue. Transitioning to motto.")
                        self.current_pinned_chat = None
                        self.current_ai_subtitle = ""
                        self.visualizer.clear_pinned()
                        self.visualizer.clear_subtitle()

                else:
                    # For regular chat answers:
                    # - If more comments are waiting in queue, hold briefly for reading (comment_active_queue_hold_sec, default 2.5s)
                    # - If queue is empty, hold for comment_post_speech_hold_sec (default 15.0s) before dissolving to motto,
                    #   waking up early if a new comment arrives.
                    has_queued_next = len(self.comment_queue) > 0
                    if has_queued_next:
                        max_hold = float(self.cfg.comment_active_queue_hold_sec)
                    else:
                        max_hold = float(self.cfg.comment_post_speech_hold_sec)

                    t_hold_start = time.perf_counter()
                    logger.info(
                        f"⏳ [Post-Speech Hold] Holding Oracle comment & pinned question (Hold target: {max_hold:.1f}s, Queue: {len(self.comment_queue)})..."
                    )

                    try:
                        while time.perf_counter() - t_hold_start < max_hold:
                            await asyncio.sleep(0.1)
                            if len(self.comment_queue) > 0:
                                min_active_hold = float(self.cfg.comment_active_queue_hold_sec)
                                elapsed = time.perf_counter() - t_hold_start
                                if elapsed >= min_active_hold:
                                    logger.info(
                                        f"⚡ [Live Chat Wakeup] Viewer comment detected in queue "
                                        f"({len(self.comment_queue)} pending, {elapsed:.1f}s elapsed >= {min_active_hold:.1f}s target). "
                                        "Transitioning to next turn."
                                    )
                                    has_queued_next = True
                                    break
                    except asyncio.CancelledError:
                        pass

                    # If there are more comments in queue, do NOT transition to motto!
                    # Transition directly to the next comment cleanly without any motto flicker.
                    if len(self.comment_queue) > 0 or has_queued_next:
                        logger.info("✨ [Direct Turn Transition] Proceeding directly to next queued comment without motto.")
                    else:
                        logger.info(f"✨ [Motto Transition] {max_hold:.1f}s post-speech hold finished with empty queue. Unpinning question and transitioning to motto.")
                        self.current_pinned_chat = None
                        self.current_ai_subtitle = ""
                        self.visualizer.clear_pinned()
                        self.visualizer.clear_subtitle()

        except asyncio.CancelledError:
            logger.debug("Active AI turn was cancelled.")
            self.tts.clear_audio_buffer()
        except Exception as e:
            logger.error(f"Error executing AI turn: {e}", exc_info=True)
        finally:
            if consumer_task is not None and not consumer_task.done():
                consumer_task.cancel()
                try:
                    await consumer_task
                except (asyncio.CancelledError, Exception):
                    pass
            self.tts.live_turn_active.clear()
            self.tts.last_live_turn_end_time = time.time()
            # NOTE: turn_phase is deliberately NOT reset here so a timeout log can report the
            # phase the turn was stuck in; the scheduler resets it after the guarded call.
            self.turn_started_at = 0.0
            if hasattr(self.visualizer, "set_utterance_state"):
                self.visualizer.set_utterance_state(False)
            self.last_activity_time = time.time()
            self.last_turn_completed_time = time.time()
            self.last_turn_event_type = event.event_type
            if event.event_type == "spontaneous":
                self.last_spontaneous_time = time.time()
            if not self.comment_queue:
                self.current_pinned_chat = None
                self.current_ai_subtitle = ""
                self.visualizer.clear_pinned()
                self.visualizer.clear_subtitle()

    # ------------------------------------------------------------------
    # Read-the-question-aloud helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _speakable_handle(handle: str) -> str:
        """'MillCreekExchange' -> 'Mill Creek Exchange'; 'DebraW1957' -> 'Debra W'; underscores -> spaces."""
        h = (handle or "").strip().lstrip("@").replace("_", " ").replace("-", " ")
        h = re.sub(r"\d+", " ", h)                                  # drop digit runs
        h = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", h)                  # camelCase -> camel Case
        h = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", h)             # ABCDef -> ABC Def
        # Drop decorative fragments like the 'Xx' / 'xX' in XxDarkLordxX (1-2 letter tokens at the ends)
        toks = [t for t in h.split() if t]
        while len(toks) > 1 and len(toks[0]) <= 2 and toks[0].lower() in ("xx", "x", "xo", "ox"):
            toks.pop(0)
        while len(toks) > 1 and len(toks[-1]) <= 2 and toks[-1].lower() in ("xx", "x", "xo", "ox"):
            toks.pop()
        return " ".join(toks).strip() or "A viewer"

    def _speakable_question(self, text: str) -> str:
        """Cleans a chat message for reading aloud: no handles, sane case, bounded length."""
        q = re.sub(r"@\S+", "", text or "").strip()
        q = re.sub(r"\s{2,}", " ", q)
        letters = [ch for ch in q if ch.isalpha()]
        if letters and sum(ch.isupper() for ch in letters) / len(letters) > 0.6:
            # Caps-lock cast characters (DebraW1957) should not be shouted by the TTS.
            # Sentence-case each segment while keeping its own terminal punctuation.
            segs = re.split(r"(?<=[.!?])\s+", q.lower())
            q = " ".join(seg.strip()[:1].upper() + seg.strip()[1:] for seg in segs if seg.strip())
        words = q.split()
        max_w = int(self.cfg.read_question_max_words)
        if len(words) > max_w:
            q = " ".join(words[:max_w]).rstrip(",;:") + "..."
        if q and q[-1] not in ".!?":
            q += "."
        return q

    # Openers that begin a question even without a '?' ("how do i...", "why is it that...")
    _QUESTION_OPENERS = (
        "who", "what", "why", "how", "when", "where", "which", "whose",
        "is", "are", "was", "were", "am", "do", "does", "did", "can", "could",
        "should", "would", "will", "shall", "may", "might", "have", "has", "had",
        "if", "any", "anyone", "anybody", "tell me", "explain",
    )

    @classmethod
    def _looks_like_question(cls, text: str) -> bool:
        """True when the message reads as a question, so the intro verb can be 'asks' not 'says'."""
        t = (text or "").strip().lower()
        if not t:
            return False
        if "?" in t:
            return True
        first_two = " ".join(t.split()[:2])
        first = t.split()[0] if t.split() else ""
        return first in cls._QUESTION_OPENERS or first_two in cls._QUESTION_OPENERS

    def _pick_read_template(self, is_question: bool) -> str:
        """Rotates through the pipe-separated alternatives without repeating the last one used."""
        raw = self.cfg.read_question_template if is_question else self.cfg.read_statement_template
        options = [o.strip() for o in str(raw).split("|") if o.strip()]
        if not options:
            return "{author}: {question}"
        last = getattr(self, "_last_read_template", None)
        pool = [o for o in options if o != last] or options
        choice = random.choice(pool)
        self._last_read_template = choice
        return choice

    def _question_read_aloud_text(self, event: "CommentEvent") -> str:
        """Returns the spoken intro for this turn, or '' when the mode/turn doesn't call for one."""
        mode = self.cfg.read_question_aloud
        if mode in ("", "off", "false", "0"):
            return ""
        is_cast = event.event_type == "cast"
        is_viewer = event.event_type in ("chat", "superchat", "direct_mention", "greeting")
        if mode == "cast" and not is_cast:
            return ""
        if mode == "viewers" and not is_viewer:
            return ""
        if mode == "all" and not (is_cast or is_viewer):
            return ""
        pinned = self.current_pinned_chat or {}
        author = self._speakable_handle(pinned.get("author", ""))
        question = self._speakable_question(pinned.get("message", ""))
        if not question:
            return ""
        template = self._pick_read_template(self._looks_like_question(pinned.get("message", "")))
        return template.format(author=author, question=question).strip()

    async def _recover_from_stuck_turn(self):
        """
        Cleanup after a turn was cancelled by the scheduler timeout. asyncio.wait_for has already
        cancelled _execute_ai_turn (its finally-block ran), so this only has to reset shared state
        that could otherwise wedge the next turn.
        """
        try:
            self.tts.clear_audio_buffer()
        except Exception as e:
            logger.debug(f"recover: clear_audio_buffer: {e}")
        try:
            self.tts.end_utterance()
        except Exception as e:
            logger.debug(f"recover: end_utterance: {e}")
        self.tts.live_turn_active.clear()
        self.tts.last_live_turn_end_time = time.time()
        if self.tts.gpu_lock.locked():
            # Lock is released by the `async with` in the cancelled coroutine; if it is still held
            # here something else (a background synth) owns it, which is legitimate. Just report.
            logger.warning("[TURN TIMEOUT] gpu_lock still held after recovery (background synthesis in progress).")
        self.current_pinned_chat = None
        self.current_ai_subtitle = ""
        try:
            self.visualizer.clear_pinned()
            self.visualizer.clear_subtitle()
            if hasattr(self.visualizer, "set_utterance_state"):
                self.visualizer.set_utterance_state(False)
        except Exception as e:
            logger.debug(f"recover: visualizer reset: {e}")
        self.turn_phase = "idle"
        self.turn_started_at = 0.0

    async def turn_watchdog_task(self):
        """Logs a WARNING every 15 s while a turn has been running for more than 60 s."""
        while self.running:
            try:
                await asyncio.sleep(15.0)
                if self.turn_started_at > 0:
                    active_sec = time.time() - self.turn_started_at
                    if active_sec > 60.0:
                        ev = self.active_turn_event
                        ev_type = ev.event_type if ev else "?"
                        logger.warning(
                            f"[TURN WATCHDOG] Turn '{ev_type}' active for {active_sec:.0f}s, phase='{self.turn_phase}', "
                            f"buffered={self.tts.get_buffered_duration():.1f}s, "
                            f"live_turn_active={self.tts.live_turn_active.is_set()}, gpu_lock={self.tts.gpu_lock.locked()}"
                        )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"turn watchdog note: {e}")

    # --------------------------------------------------------------------------
    # 3. Local OBS Studio Integration (Direct WebSocket on localhost)
    # --------------------------------------------------------------------------
    async def trigger_obs_fx(
        self,
        source_name: Optional[str] = None,
        duration_sec: Optional[float] = None,
        filter_name: Optional[str] = None,
    ):
        """Directly activates visual/media celebration FX in local OBS Studio."""
        src = source_name or self.cfg.obs_celebrate_source_name or "Celebration FX"
        dur = duration_sec if duration_sec is not None else self.cfg.obs_celebrate_duration_sec
        flt = filter_name if filter_name is not None else self.cfg.obs_celebrate_filter_name

        if not self.obs_client or not self.obs_connected or not obsws:
            logger.info(
                f"🎉 [OBS FX] Celebration FX triggered! (OBS not connected — add a Source/Media named '{src}' in OBS to view on stream)"
            )
            return

        loop = asyncio.get_running_loop()

        def _do_obs_fx_sync():
            try:
                res_scene = self.obs_client.call(obs_requests.GetCurrentProgramScene())
                scene_name = ""
                if hasattr(res_scene, "getCurrentProgramSceneName"):
                    scene_name = res_scene.getCurrentProgramSceneName()
                elif hasattr(res_scene, "getSettings"):
                    scene_name = res_scene.getSettings().get("currentProgramSceneName", "")

                if not scene_name:
                    scene_name = self.current_scene or "Main"

                item_id = None
                try:
                    res_item = self.obs_client.call(obs_requests.GetSceneItemId(sceneName=scene_name, sourceName=src))
                    if hasattr(res_item, "getSceneItemId"):
                        item_id = res_item.getSceneItemId()
                    elif hasattr(res_item, "getSettings"):
                        item_id = res_item.getSettings().get("sceneItemId", None)
                except Exception as e:
                    logger.debug(f"Scene item query for '{src}' note: {e}")

                if item_id is not None:
                    self.obs_client.call(
                        obs_requests.SetSceneItemEnabled(sceneName=scene_name, sceneItemId=item_id, sceneItemEnabled=True)
                    )
                    logger.info(f"🎉 [OBS FX] Enabled scene item '{src}' (ID {item_id}) in scene '{scene_name}'")

                    try:
                        self.obs_client.call(
                            obs_requests.TriggerMediaInputAction(inputName=src, mediaAction="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART")
                        )
                    except Exception:
                        pass

                if flt:
                    try:
                        self.obs_client.call(obs_requests.SetSourceFilterEnabled(sourceName=src, filterName=flt, filterEnabled=True))
                    except Exception as e:
                        logger.debug(f"Filter toggle note: {e}")

                return scene_name, item_id
            except Exception as e:
                logger.warning(f"Error executing OBS FX sync calls: {e}")
                return None, None

        try:
            logger.info(f"🎉 [OBS FX] Activating OBS celebration FX on source '{src}' for {dur}s...")
            scene_name, item_id = await loop.run_in_executor(None, _do_obs_fx_sync)

            if item_id is not None:
                async def _disable_later():
                    await asyncio.sleep(dur)
                    def _disable_sync():
                        try:
                            if self.obs_client and self.obs_connected:
                                self.obs_client.call(
                                    obs_requests.SetSceneItemEnabled(sceneName=scene_name, sceneItemId=item_id, sceneItemEnabled=False)
                                )
                                if flt:
                                    self.obs_client.call(obs_requests.SetSourceFilterEnabled(sourceName=src, filterName=flt, filterEnabled=False))
                                logger.info(f"🎉 [OBS FX] Disabled celebration scene item '{src}' after {dur}s")
                        except Exception as e:
                            logger.debug(f"Error disabling celebration source: {e}")
                    await loop.run_in_executor(None, _disable_sync)

                asyncio.create_task(_disable_later())
            elif scene_name:
                logger.info(f"🎉 [OBS FX] Source '{src}' not found in active scene '{scene_name}'.")

        except Exception as e:
            logger.warning(f"Error triggering OBS FX for '{src}': {e}")

    async def obs_monitor_task(self):
        """Monitors local OBS Studio for broadcast status and scenes."""
        if not obsws:
            logger.warning("obs-websocket-py not installed. OBS polling disabled.")
            return

        loop = asyncio.get_running_loop()
        ws_client = None
        notified_unavailable = False

        while self.running:
            try:
                # 1. Fast pre-flight TCP probe (0.15s) in thread pool to prevent hanging the asyncio event loop
                is_open = await loop.run_in_executor(
                    None,
                    probe_tcp_port,
                    self.cfg.obs_ws_host,
                    self.cfg.obs_ws_port,
                    self.cfg.obs_connect_timeout,
                )

                if not is_open:
                    if self.obs_connected:
                        self.obs_connected = False
                        self.obs_client = None
                        logger.info("OBS Studio disconnected or closed.")
                    elif not notified_unavailable:
                        notified_unavailable = True
                        logger.info(
                            f"OBS Studio WebSocket ({self.cfg.obs_ws_host}:{self.cfg.obs_ws_port}) not listening. "
                            "Visualizer running standalone (will auto-connect when OBS starts)."
                        )
                    await asyncio.sleep(self.cfg.obs_retry_interval_sec)
                    continue

                # 2. Port is open: execute connection in thread pool
                logger.info(f"Connecting to OBS WebSocket on {self.cfg.obs_ws_host}:{self.cfg.obs_ws_port}...")

                def _connect_client_sync():
                    client = obsws(
                        self.cfg.obs_ws_host,
                        self.cfg.obs_ws_port,
                        self.cfg.obs_ws_password,
                    )
                    client.connect()
                    return client

                ws_client = await loop.run_in_executor(None, _connect_client_sync)
                self.obs_client = ws_client
                self.obs_connected = True
                notified_unavailable = False
                logger.info("Connected to OBS Studio WebSocket locally!")

                def on_event(event):
                    event_name = event.name if hasattr(event, "name") else type(event).__name__
                    if "StreamStateChanged" in event_name or "Stream" in event_name:
                        output_active = getattr(event, "outputActive", None)
                        if output_active is not None:
                            self.is_streaming = bool(output_active)
                            self._update_engagement_state()
                    if "CurrentProgramSceneChanged" in event_name or "Scene" in event_name:
                        scene_n = getattr(event, "sceneName", "")
                        if scene_n:
                            self.current_scene = scene_n
                            self._update_engagement_state()

                ws_client.register(on_event)

                last_stream_check = 0.0
                stream_poll_interval = self.cfg.obs_stream_status_poll_interval

                while self.running:
                    now = time.time()
                    check_stream = (now - last_stream_check >= stream_poll_interval)
                    if check_stream:
                        last_stream_check = now

                    # 3. Offload all synchronous OBS request-responses to thread pool
                    def _poll_obs_sync():
                        res_st = ws_client.call(obs_requests.GetStreamStatus()) if check_stream else None
                        res_sc = ws_client.call(obs_requests.GetCurrentProgramScene()) if check_stream else None
                        return res_st, res_sc

                    try:
                        res_stream, res_scene = await loop.run_in_executor(None, _poll_obs_sync)
                    except Exception as e:
                        logger.warning(f"OBS WebSocket connection lost: {e}. Reconnecting...")
                        break

                    # Process stream status
                    if res_stream is not None:
                        active = (
                            res_stream.getOutputActive()
                            if hasattr(res_stream, "getOutputActive")
                            else res_stream.getSettings().get("outputActive", False)
                            if hasattr(res_stream, "getSettings")
                            else getattr(res_stream, "outputActive", False)
                        )
                        is_streaming_now = bool(active)

                        scene_now = ""
                        if res_scene is not None:
                            if hasattr(res_scene, "getCurrentProgramSceneName"):
                                scene_now = res_scene.getCurrentProgramSceneName()
                            elif hasattr(res_scene, "getSettings"):
                                scene_now = res_scene.getSettings().get("currentProgramSceneName", "")
                        if not scene_now:
                            scene_now = self.current_scene

                        state_changed = (is_streaming_now != self.is_streaming) or (scene_now != self.current_scene)
                        self.is_streaming = is_streaming_now
                        self.current_scene = scene_now

                        if state_changed:
                            logger.info(
                                f"🎬 [OBS State Changed] Live Stream: {'🔴 ON AIR' if self.is_streaming else '⚪ OFFLINE'} | "
                                f"Active Scene: '{self.current_scene}'"
                            )
                            self._update_engagement_state()

                    await asyncio.sleep(0.4)

            except Exception as e:
                self.obs_connected = False
                self.obs_client = None
                if not notified_unavailable:
                    logger.warning(f"OBS WebSocket notice: {e}. Retrying in 5s...")
                    notified_unavailable = True
                if ws_client:
                    try:
                        await loop.run_in_executor(None, ws_client.disconnect)
                    except Exception:
                        pass
                await asyncio.sleep(self.cfg.obs_retry_interval_sec)
    # --------------------------------------------------------------------------
    # 5. YouTube Live Chat Poller
    # --------------------------------------------------------------------------
    async def youtube_chat_task(self):
        """Polls YouTube Live Chat via pytchat or runs simulated stream chat."""
        raw_input = (
            self.cfg.youtube_video_id.strip()
            or self.cfg.youtube_channel_handle.strip()
        )

        if not raw_input:
            logger.warning(
                "YouTube Chat Poller IDLE: No YOUTUBE_VIDEO_ID or YOUTUBE_CHANNEL_HANDLE configured in .env.\n"
                "  -> Set YOUTUBE_VIDEO_ID or YOUTUBE_CHANNEL_HANDLE in .env\n"
                "  -> Or type chat comments directly into this console!"
            )
            while self.running:
                await asyncio.sleep(5.0)
            return

        if not pytchat:
            logger.error("pytchat is not installed in this Python environment. Run: pip install pytchat")
            while self.running:
                await asyncio.sleep(5.0)
            return

        loop = asyncio.get_running_loop()
        is_channel_mode = ("@" in raw_input or "youtube.com/" in raw_input) and not any(
            x in raw_input for x in ("watch?v=", "/live/", "youtu.be/", "embed/")
        )

        while self.running:
            video_id = await loop.run_in_executor(None, extract_youtube_video_id, raw_input)

            if not video_id:
                if is_channel_mode:
                    logger.info(
                        f"[YT Chat] Channel '{raw_input}' is currently offline. "
                        "Waiting for live broadcast to start (checking every 15s)..."
                    )
                else:
                    logger.warning(f"[YT Chat] Could not resolve live stream for '{raw_input}'. Checking in 15s...")
                await asyncio.sleep(15.0)
                continue

            logger.info(f"Connecting to YouTube Live Chat for Video ID: '{video_id}'...")
            chat = None
            try:
                loop = asyncio.get_running_loop()
                chat = pytchat.create(video_id=video_id)
                self.active_video_id = video_id
                logger.info(f"🎉 Connected to YouTube Live Chat for Video '{video_id}'!")


                api_key = self.cfg.youtube_api_key

                # Restore live stream chat backlog via YouTube Data API v3 (silent restore into visualizer)
                if api_key:
                    backlog_msgs = await loop.run_in_executor(None, fetch_youtube_live_chat_backlog, video_id, api_key)
                    if backlog_msgs:
                        restored_api = 0
                        for bm in backlog_msgs:
                            a_name = bm.get("author", "Viewer")
                            m_text = bm.get("message", "")
                            if not any(e.get("author") == a_name and e.get("message") == m_text for e in self.chat_history):
                                self.chat_history.append(bm)
                                restored_api += 1
                            a_clean = a_name.lower().strip().lstrip("@")
                            if a_clean:
                                self.seen_chat_handles.add(a_clean)
                            self.brain.add_chat_message(a_name, m_text, bm.get("is_superchat", False), bm.get("amount", ""))
                        if restored_api > 0:
                            self._save_cached_chat()
                            logger.info(f"📂 [Live Chat Sync] Restored {restored_api} YouTube live chat messages into visualizer without re-triggering.")

                init_viewers = await loop.run_in_executor(None, fetch_youtube_live_viewers, video_id, api_key)
                self._on_viewer_count_update(init_viewers if init_viewers is not None else 0)

                first_chat_sync = True
                while self.running and chat.is_alive():
                    sync_items = await loop.run_in_executor(None, lambda: list(chat.get().sync_items()))

                    if first_chat_sync:
                        first_chat_sync = False
                        if sync_items:
                            restored_count = 0
                            for item in sync_items:
                                a_name = getattr(item.author, "name", "Viewer")
                                a_type = str(getattr(item.author, "type", "viewer")).lower()
                                m_text = getattr(item, "message", "")
                                is_sc = bool(getattr(item, "amountValue", 0) and item.amountValue > 0)
                                sc_amt = getattr(item, "amountString", "") if is_sc else ""
                                now_ts = time.time()
                                if not any(e.get("author") == a_name and e.get("message") == m_text for e in self.chat_history):
                                    chat_entry = {
                                        "author": a_name,
                                        "author_type": a_type,
                                        "message": m_text,
                                        "is_superchat": is_sc,
                                        "amount": sc_amt,
                                        "timestamp": now_ts,
                                    }
                                    self.chat_history.append(chat_entry)
                                    restored_count += 1
                                a_clean = a_name.lower().strip().lstrip("@")
                                if a_clean:
                                    self.seen_chat_handles.add(a_clean)
                                self.brain.add_chat_message(a_name, m_text, is_sc, sc_amt)
                            self._save_cached_chat()
                            logger.info(f"📂 [Chat Restore] Loaded {len(sync_items)} historical YouTube chat messages into visualizer without re-triggering.")
                        continue

                    for item in sync_items:
                        is_superchat = bool(item.amountValue and item.amountValue > 0)
                        author_name = item.author.name
                        author_type = str(getattr(item.author, "type", "viewer")).lower()
                        msg = item.message
                        msg_lower = msg.lower().strip()

                        author_clean = author_name.lower().strip().lstrip("@")
                        author_compact = author_clean.replace(" ", "").replace("_", "").replace("-", "")

                        # Comprehensive set of channel and AI host handles to prevent self-triggering
                        own_identifiers = {
                            "host",
                            "owner",
                            "broadcaster",
                        }
                        for val in [
                            self.cfg.youtube_channel_handle,
                            self.cfg.ai_host_name,
                            self.discovered_channel_handle,
                        ]:
                            if val:
                                v_clean = val.lower().strip().lstrip("@")
                                own_identifiers.add(v_clean)
                                own_identifiers.add(v_clean.replace(" ", "").replace("_", "").replace("-", ""))

                        for ch in self.cfg.channel_handles:
                            if ch:
                                ch_clean = ch.lower().strip().lstrip("@")
                                own_identifiers.add(ch_clean)
                                own_identifiers.add(ch_clean.replace(" ", "").replace("_", "").replace("-", ""))

                        is_channel_owner = (
                            getattr(item.author, "isChatOwner", False)
                            or getattr(item.author, "isChatBroadcaster", False)
                            or author_type in ("owner", "broadcaster")
                            or author_clean in own_identifiers
                            or author_compact in own_identifiers
                        )
                        is_own_handle = is_channel_owner or (author_clean in own_identifiers) or (author_compact in own_identifiers)
                        if is_channel_owner:
                            author_type = "owner"

                        if getattr(item.author, "isChatOwner", False) or getattr(item.author, "isChatBroadcaster", False):
                            if author_name and self.discovered_channel_handle != author_name:
                                self.discovered_channel_handle = author_name
                                clean_handle = f"@{author_name.lstrip('@')}"
                                self.brain.update_channel_identity(clean_handle, author_name)

                        # Record chat entry immediately
                        now_ts = time.time()
                        self.chat_timestamps.append(now_ts)
                        if not is_channel_owner:
                            self.last_chat_received_time = now_ts
                            # Inform CastEngine that real chat arrived so synthetic cast pauses
                            self.cast.last_cast_time = now_ts
                            # Prune any pending synthetic cast / spontaneous idle items from queue so real human is answered immediately
                            self.comment_queue = [ev for ev in self.comment_queue if ev.event_type not in ("cast", "spontaneous", "system")]
                        if len(self.chat_timestamps) > 300:
                            self.chat_timestamps = self.chat_timestamps[-200:]

                        chat_entry = {
                            "author": author_name,
                            "author_type": author_type,
                            "message": msg,
                            "is_superchat": is_superchat,
                            "amount": item.amountString if is_superchat else "",
                            "timestamp": now_ts,
                        }
                        self.chat_history.append(chat_entry)
                        self._save_cached_chat()
                        self.brain.add_chat_message(author_name, msg, is_superchat, item.amountString if is_superchat else "")
                        sess_id = self.session_log.session_id if self.session_log else ""
                        self.brain.chatter_db.record_activity(
                            handle=author_name,
                            display_name=author_name,
                            message=msg,
                            is_member=(author_type == "member"),
                            is_cast=False,
                            session_id=sess_id,
                        )
                        if self.session_log:
                            self.session_log.log_chat_message(
                                author=author_name,
                                author_type=author_type,
                                message=msg,
                                is_superchat=is_superchat,
                                amount=item.amountString if is_superchat else "",
                                is_cast=False,
                            )
                        self.last_activity_time = now_ts
                        self.last_chat_time = now_ts
                        self.last_real_chat_time = now_ts
                        self.spontaneous_idle_count = 0
                        self.encouragement_idle_count = 0

                        if not is_channel_owner and self.concurrent_viewers < 1:
                            self.concurrent_viewers = 1

                        self._update_engagement_state()

                        # 1. Membership / Subscription events
                        is_member_event = (
                            author_type in ("sponsor", "member", "new_sponsor")
                            or "welcome to membership" in msg_lower
                            or "became a member" in msg_lower
                            or "joined as a member" in msg_lower
                            or "subscribed" in msg_lower
                        )
                        if is_member_event:
                            logger.info(f"🌟 [YT Event] Membership / Subscription: @{author_name} ({msg})")
                            self.visualizer.trigger_celebration(duration=6.0)
                            await self.trigger_obs_fx(duration_sec=6.0)
                            if self.cfg.thank_subscribers:
                                ev_kind = "membership" if ("member" in msg_lower or "sponsor" in author_type) else "subscription"
                                msg_ctx = f" Message: '{msg}'." if msg else ""
                                prompt = (
                                    f"[NEW_MEMBER] @{author_name} just became a channel member!{msg_ctx} "
                                    f"Give @{author_name} an enthusiastic shoutout and welcome them to the cosmic family!"
                                    if ev_kind == "membership"
                                    else f"[NEW_SUBSCRIBER] @{author_name} just subscribed!{msg_ctx} Shout out and thank @{author_name}!"
                                )
                                self._trigger_ai_turn(prompt_trigger=prompt, event_type="superchat", priority=2, chat_item=chat_entry)

                        # 2. Celebration trigger in live chat
                        is_celebrate_cmd = (
                            msg_lower in ("celebrate!", "celebrate", "!celebrate", "party!", "let's celebrate", "lets celebrate")
                            or msg_lower.startswith("celebrate!")
                        )
                        if is_celebrate_cmd:
                            logger.info(f"🎉 [Chat Celebration Command] from @{author_name}: '{msg}'")
                            self.visualizer.trigger_celebration(duration=5.0)
                            await self.trigger_obs_fx(duration_sec=5.0)
                            self._trigger_ai_turn(
                                prompt_trigger=f"[CELEBRATION] Host @{author_name} called for a celebration: '{msg}'. Hyped celebration response!",
                                event_type="superchat",
                                priority=2,
                                chat_item=chat_entry,
                            )

                        # First-time chatter tracking (never greet own handle / channel as a new chatter)
                        is_new_chatter = False
                        if not is_own_handle and author_clean:
                            if author_clean not in self.seen_chat_handles:
                                self.seen_chat_handles.add(author_clean)
                                is_new_chatter = True
                                logger.info(f"👋 [New Chatter] @{author_name} is chatting for the first time!")

                        logger.info(f"💬 [YT Live Chat] @{author_name}: {msg} {f'({item.amountString})' if is_superchat else ''}")

                        if is_celebrate_cmd:
                            pass
                        elif is_own_handle:
                            # The AI co-host recognizes its own handle (@MassiveGodComplex / channel owner) and skips responding to itself
                            logger.info(f"🛡️ [Own Handle Recognized] Chat message from own channel/host handle @{author_name}: '{msg}'. Skipping AI self-response.")
                        elif self.cfg.chat_reader_mode:
                            spoken_text = f"Superchat from @{author_name.lstrip('@')} for {item.amountString}! {msg}" if is_superchat else f"@{author_name.lstrip('@')} says, {msg}"
                            mood = "hyped" if is_superchat else "energetic"
                            self.visualizer.set_mood(mood)
                            self.current_ai_subtitle = f"@{author_name.lstrip('@')}: {msg}"
                            self.visualizer.set_subtitle(self.current_ai_subtitle)
                            asyncio.create_task(self.tts.queue_speech(spoken_text))
                        elif is_new_chatter and self.cfg.greet_new_chatters:
                            should_trigger, reason = self.brain.should_trigger_response(msg, is_new_chatter=True)
                            if not (is_superchat or should_trigger):
                                logger.info(f"⏭️ [Greeting Skipped] @{author_name}: '{msg[:60]}' -> {reason}")
                            if is_superchat or should_trigger:
                                prompt = (
                                    f"[NEW_CHATTER_GREETING] @{author_name.lstrip('@')} just sent their very first message: '{msg}'. "
                                    f"Greet @{author_name.lstrip('@')} warmly and wittily by name while responding to their comment!"
                                )
                                self._trigger_ai_turn(prompt_trigger=prompt, event_type="greeting", priority=3, chat_item=chat_entry)
                        else:
                            should_trigger, reason = self.brain.should_trigger_response(msg)
                            if is_superchat or should_trigger:
                                prefix = f"Chat message from @{author_name.lstrip('@')}"
                                prio = 1 if is_superchat else (2 if "direct_mention" in reason else 4)
                                ev_type = "superchat" if is_superchat else ("direct_mention" if "direct_mention" in reason else "chat")
                                self._trigger_ai_turn(prompt_trigger=f"{prefix}: '{msg}'", event_type=ev_type, priority=prio, chat_item=chat_entry)
                            else:
                                if "member_reply_entanglement" in reason:
                                    logger.info(f"⏸️ [Chat Filtered] Not triggering AI ({reason}). Preserving member entanglement.")
                                elif "eco_mode_suppressed" in reason:
                                    logger.info(f"🌙 [Eco Mode Throttled] Not triggering AI ({reason}).")
                                else:
                                    # Every skipped viewer message must be visible in the log with its reason.
                                    logger.info(f"⏭️ [Chat Skipped] @{author_name}: '{msg[:60]}' -> {reason}")

                    await asyncio.sleep(self.cfg.chat_poll_interval)

                if chat and not chat.is_alive():
                    logger.warning(f"YouTube live stream '{video_id}' ended or went offline. Re-checking channel in 15s...")
                    await asyncio.sleep(15.0)

            except Exception as e:
                logger.warning(f"YouTube chat connection note for '{video_id}': {e}. Reconnecting in 5s...")
                await asyncio.sleep(5.0)
            finally:
                if chat and hasattr(chat, "terminate"):
                    try:
                        chat.terminate()
                    except Exception:
                        pass

    async def youtube_viewer_poller_task(self):
        """Periodically polls active YouTube concurrent viewer count and calculates chat velocity."""
        if not self.cfg.auto_track_live_viewers:
            return

        logger.info(
            f"Starting YouTube Live Concurrent Viewer Poller "
            f"(Active: every {self.cfg.viewer_count_poll_interval}s, 0-Viewers: every {self.cfg.viewer_0_poll_interval}s)..."
        )
        while self.running:
            try:
                now = time.time()
                cutoff = now - 60.0
                self.chat_timestamps = [t for t in self.chat_timestamps if t >= cutoff]
                chat_velocity = len(self.chat_timestamps)

                target_vid = (
                    self.active_video_id
                    or self.cfg.youtube_video_id.strip()
                )

                if target_vid:
                    loop = asyncio.get_running_loop()
                    api_key = self.cfg.youtube_api_key
                    api_viewers = await loop.run_in_executor(None, fetch_youtube_live_viewers, target_vid, api_key)
                    if api_viewers is not None:
                        self._on_viewer_count_update(api_viewers, chat_velocity)
                    else:
                        logger.debug("YouTube viewer poller: API response unavailable; retaining current viewer count.")

            except Exception as e:
                logger.debug(f"Viewer poller cycle note: {e}")

            # Polling cadence: use viewer_0_poll_interval when in empty room (0 viewers), otherwise standard viewer_count_poll_interval
            current_interval = (
                self.cfg.viewer_0_poll_interval
                if self.concurrent_viewers == 0
                else self.cfg.viewer_count_poll_interval
            )
            await asyncio.sleep(current_interval)

    async def _async_get_console_line(self) -> Optional[str]:
        """Non-blocking Windows console line reader that never blocks Ctrl+C or locks mouse."""
        if sys.platform == "win32":
            try:
                import msvcrt
                chars = []
                while self.running:
                    while msvcrt.kbhit():
                        c = msvcrt.getwch()
                        if c == "\r" or c == "\n":
                            print()  # Echo newline
                            return "".join(chars)
                        elif c == "\x08" or c == "\x7f":  # Backspace
                            if chars:
                                chars.pop()
                                msvcrt.putwch("\b")
                                msvcrt.putwch(" ")
                                msvcrt.putwch("\b")
                        elif c == "\x03":  # Ctrl+C
                            raise KeyboardInterrupt
                        elif c >= " ":
                            chars.append(c)
                            msvcrt.putwch(c)
                    await asyncio.sleep(0.05)
                return None
            except ImportError:
                pass

        # Non-Windows or fallback
        loop = asyncio.get_running_loop()
        line = await loop.run_in_executor(None, sys.stdin.readline)
        return line.strip() if line else None

    async def console_chat_task(self):
        """Allows direct typing of test comments or commands into the host terminal."""
        logger.info(
            f"Console Chat Input active: Type comments in terminal (e.g. 'Alice: Hello!' "
            "or 'viewers: 5' / 'sub: Alice')"
        )

        while self.running:
            try:
                line = await self._async_get_console_line()
                if not line:
                    await asyncio.sleep(0.1)
                    continue

                line = line.strip()
                if not line:
                    continue

                self.chat_timestamps.append(time.time())

                if ":" in line:
                    author, message = line.split(":", 1)
                    author = author.strip().lstrip("@")
                    message = message.strip()
                else:
                    author = "Viewer"
                    message = line

                msg_lower = message.lower().strip()

                # Manual viewer count override
                if author.lower() in ("viewers", "viewer", "count", "viewercount", "setviewers"):
                    try:
                        val = int(message.strip())
                        logger.info(f"👥 [Console Override] Concurrent Viewers set to {val}")
                        self._on_viewer_count_update(val, len(self.chat_timestamps))
                        continue
                    except ValueError:
                        pass

                # Test subscription / membership simulation
                if author.lower() in ("sub", "subscriber", "newsub"):
                    logger.info(f"🌟 [Console Event] Test Subscription: @{message}")
                    self.visualizer.trigger_celebration(duration=6.0)
                    await self.trigger_obs_fx(duration_sec=6.0)
                    if self.cfg.thank_subscribers:
                        prompt = (
                            f"[NEW_SUBSCRIBER] @{message.lstrip('@')} just subscribed! "
                            f"Enthusiastically thank @{message.lstrip('@')} for subscribing to {self.cfg.youtube_channel_handle}!"
                        )
                        self._trigger_ai_turn(prompt_trigger=prompt, event_type="superchat", priority=1)
                    continue
                elif author.lower() in ("member", "membership", "join"):
                    logger.info(f"🌟 [Console Event] Test Membership: @{message}")
                    self.visualizer.trigger_celebration(duration=6.0)
                    await self.trigger_obs_fx(duration_sec=6.0)
                    if self.cfg.thank_subscribers:
                        prompt = (
                            f"[NEW_MEMBER] @{message.lstrip('@')} just joined as a channel member! "
                            f"Enthusiastically welcome @{message.lstrip('@')} into the cosmic family!"
                        )
                        self._trigger_ai_turn(prompt_trigger=prompt, event_type="superchat", priority=1)
                    continue

                # Favourite command: save the last spontaneous bit that played as a few-shot exemplar
                if msg_lower in ("/fav", "fav", "!fav", "/favorite", "/favourite"):
                    saved = self.brain.add_favorite()
                    if saved:
                        logger.info(f"⭐ [Console] Favourite saved: [{saved.get('form','bit')}] '{saved.get('text','')[:80]}'")
                    else:
                        logger.info("⭐ [Console] No bit has played yet; nothing to save.")
                    continue
                if msg_lower in ("/favs", "/favorites", "/favourites"):
                    logger.info(f"⭐ [Console] {len(self.brain.favorites)} favourite bits in {self.brain.favorites_path}")
                    for f in self.brain.favorites[-5:]:
                        logger.info(f"   - [{f.get('form','bit')}] {f.get('text','')[:90]}")
                    continue

                # Celebration command
                if msg_lower in ("celebrate!", "celebrate", "!celebrate", "party!", "let's celebrate", "lets celebrate") or msg_lower.startswith("celebrate!"):
                    logger.info(f"🎉 [Console Event] Celebration trigger from {author}: '{message}'")
                    self.visualizer.trigger_celebration(duration=5.0)
                    await self.trigger_obs_fx(duration_sec=5.0)
                    self._trigger_ai_turn(
                        prompt_trigger=f"[CELEBRATION] @{author} called for a celebration: '{message}'. Hyped celebration response!",
                        event_type="superchat",
                        priority=1,
                    )
                    continue

                author_type = "viewer"

                logger.info(f"💬 [Console Chat] @{author}: {message}")
                chat_entry = {
                    "author": author,
                    "author_type": author_type,
                    "message": message,
                    "is_superchat": False,
                    "amount": "",
                    "timestamp": time.time(),
                }
                self.chat_history.append(chat_entry)
                self._save_cached_chat()
                self.brain.add_chat_message(author, message, False, "")
                sess_id = self.session_log.session_id if self.session_log else ""
                self.brain.chatter_db.record_activity(
                    handle=author,
                    display_name=author,
                    message=message,
                    is_member=(author_type == "member"),
                    is_cast=False,
                    session_id=sess_id,
                )
                if self.session_log:
                    self.session_log.log_chat_message(
                        author=author,
                        author_type=author_type,
                        message=message,
                        is_superchat=False,
                        amount="",
                        is_cast=False,
                    )
                self.last_activity_time = time.time()
                self.last_chat_time = time.time()
                self.last_real_chat_time = time.time()
                self.spontaneous_idle_count = 0
                self.encouragement_idle_count = 0

                should_trigger, reason = self.brain.should_trigger_response(message)
                if should_trigger:
                    prefix = f"Chat message from @{author}"
                    prio = 2 if "direct_mention" in reason else 4
                    ev_type = "direct_mention" if "direct_mention" in reason else "chat"
                    self._trigger_ai_turn(prompt_trigger=f"{prefix}: '{message}'", event_type=ev_type, priority=prio, chat_item=chat_entry)

            except (KeyboardInterrupt, asyncio.CancelledError):
                self.stop()
                break
            except Exception as e:
                logger.debug(f"Console input error: {e}")
                await asyncio.sleep(0.5)

    async def cast_scheduler_task(self):
        """
        The Cast Subsystem Pacing Task (B1-B4).
        During quiet stream intervals with an active audience, injects structured questions
        from the openly-fictional cast ensemble (@ExistentialDave, @SpeedrunnerKyle, @AstralBrenda,
        @TrollChad, @HeartfeltSarah, @CuriousTimmy).
        Yields immediately whenever real human chatters or host speech is detected.
        Pauses in ECO MODE (0 viewers) when cast_require_viewers is enabled.
        """
        if not self.cfg.cast_enabled:
            return

        logger.info(
            f"🎭 [Cast Scheduler] Synthetic Cast ensemble active (Interval: {self.cfg.cast_min_interval_sec}-{self.cfg.cast_max_interval_sec}s, "
            f"Quiet threshold: {self.cfg.cast_quiet_chat_threshold_sec}s, Require Viewers: {self.cfg.cast_require_viewers})"
        )
        # Stagger initial start
        await asyncio.sleep(15.0)

        while self.running:
            try:
                await asyncio.sleep(5.0)
                if not self.cfg.cast_enabled:
                    continue

                self._update_engagement_state()

                # In Standby or ECO mode (0 viewers), suppress synthetic cast questions if require_viewers is enabled
                if self.cfg.cast_require_viewers and self.engagement_mode in ("standby", "eco"):
                    continue

                if (
                    self.brain.is_generating
                    or self.tts.is_speaking
                    or self.tts.remaining_speech_duration > 0.05
                    or self.active_turn_event is not None
                    or len(self.comment_queue) > 0
                    or getattr(self.visualizer, "is_promo_active", False)
                ):
                    continue

                now = time.time()
                time_since_last_chat = now - self.last_chat_time
                time_since_last_cast = now - self.cast.last_cast_time
                time_since_last_activity = now - self.last_activity_time
                time_since_last_spontaneous = now - self.last_spontaneous_time

                # Cast triggers when chat has been quiet for cast_quiet_chat_threshold_sec,
                # at least min_interval_sec since last cast question,
                # and at least 5s of stillness after any recent activity/reflection.
                if (
                    time_since_last_activity >= 5.0
                    and time_since_last_spontaneous >= 5.0
                    and self.cast.should_trigger_cast(
                        time_since_last_chat=time_since_last_chat,
                        time_since_last_cast=time_since_last_cast,
                        quiet_threshold_sec=self.cfg.cast_quiet_chat_threshold_sec,
                        min_interval_sec=self.cfg.cast_min_interval_sec,
                        is_ai_busy=(len(self.comment_queue) > 0),
                    )
                ):
                    persona, question = self.cast.next_cast_question()

                    now_ts = time.time()
                    self.chat_timestamps.append(now_ts)

                    chat_entry = {
                        "author": persona.handle,
                        "author_type": "cast",
                        "is_cast": True,
                        "cast_persona": persona.persona_type,
                        "message": question,
                        "is_superchat": False,
                        "amount": "",
                        "timestamp": now_ts,
                    }
                    self.chat_history.append(chat_entry)
                    self._save_cached_chat()
                    self.brain.add_chat_message(
                        author=persona.handle,
                        message=question,
                        is_superchat=False,
                        amount="",
                        is_cast=True,
                        cast_persona=persona.persona_type,
                    )
                    sess_id = self.session_log.session_id if self.session_log else ""
                    self.brain.chatter_db.record_activity(
                        handle=persona.handle,
                        display_name=persona.handle,
                        message=question,
                        is_member=False,
                        is_cast=True,
                        session_id=sess_id,
                    )
                    self.last_activity_time = now_ts
                    self.last_chat_time = now_ts
                    self.spontaneous_idle_count = 0
                    self.encouragement_idle_count = 0

                    if self.session_log:
                        self.session_log.log_cast_question(
                            persona_name=persona.handle,
                            persona_handle=persona.handle,
                            persona_type=persona.persona_type,
                            question=question,
                        )
                        self.session_log.log_chat_message(
                            author=persona.handle,
                            author_type="cast",
                            message=question,
                            is_cast=True,
                            cast_persona=persona.persona_type,
                        )

                    prompt = f"Cast member @{persona.handle} ({persona.archetype_title}) asks: '{question}'"
                    self._trigger_ai_turn(prompt_trigger=prompt, event_type="cast", priority=6, chat_item=chat_entry)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cast scheduler task: {e}", exc_info=True)
                await asyncio.sleep(5.0)

    # --------------------------------------------------------------------------
    # 6. Idle Reflection & Chat Encouragement Monitor
    # --------------------------------------------------------------------------
    async def idle_reflection_monitor_task(self):
        """Periodically evaluates stream/chat lulls and generates spontaneous commentary during live broadcasts."""
        logger.info(
            f"Spontaneous Commentary Engine active (Silence trigger: {self.cfg.idle_silence_threshold_sec}s, "
            f"Base Interval: {self.cfg.spontaneous_min_interval_sec}s, Max Backoff: {self.cfg.spontaneous_max_backoff_sec}s)"
        )
        while self.running:
            try:
                await asyncio.sleep(5.0)
                if not self.cfg.spontaneous_commentary_enabled or self.cfg.chat_reader_mode:
                    continue

                self._update_engagement_state()

                # In Standby or ECO mode (0 viewers), suppress spontaneous reflections if require_viewers is enabled
                if self.cfg.spontaneous_require_viewers and self.engagement_mode in ("standby", "eco"):
                    continue

                now = time.time()
                if (
                    self.brain.is_generating
                    or self.tts.is_speaking
                    or self.tts.remaining_speech_duration > 0.05
                    or self.active_turn_event is not None
                    or len(self.comment_queue) > 0
                    or getattr(self.visualizer, "is_promo_active", False)
                ):
                    continue

                silence_dur = now - self.last_activity_time
                time_since_last_spontaneous = now - self.last_spontaneous_time
                time_since_last_chat = now - self.last_chat_time
                time_since_last_encouragement = now - self.last_chat_encouragement_time
                encouragement_enabled = self.cfg.chat_encouragement_enabled
                encouragement_base_interval = self.cfg.chat_encouragement_interval_sec
                encouragement_backoff = min(600.0, encouragement_base_interval * (1.5 ** self.encouragement_idle_count))

                # 1. Chat Encouragement: Viewers watching, but chat silent (only if enabled)
                if (encouragement_enabled and
                    encouragement_base_interval > 0 and
                    time_since_last_chat >= encouragement_backoff and
                    time_since_last_encouragement >= encouragement_backoff and
                    silence_dur >= 30.0):

                    logger.info(
                        f"📣 [Chat Encouragement] {self.concurrent_viewers} viewers watching, chat silent for {time_since_last_chat:.0f}s. "
                        "Triggering AI host call-to-action..."
                    )
                    self.last_chat_encouragement_time = now
                    self.last_activity_time = now
                    self.last_spontaneous_time = now
                    self.encouragement_idle_count += 1
                    self.visualizer.set_mood("hyped")
                    chan_handle = self.cfg.youtube_channel_handle
                    prompt = (
                        f"[CHAT_ENCOURAGEMENT] There are currently {self.concurrent_viewers} viewers watching on {chan_handle}, "
                        f"but chat has been quiet. "
                        f"Deliver a witty, engaging, transcendent call-to-action to wake up the chat and invite questions!"
                    )
                    self._trigger_ai_turn(prompt_trigger=prompt, event_type="spontaneous", priority=6)

                # 2. General Spontaneous Reflection with Adaptive Backoff
                spontaneous_base = self.cfg.spontaneous_min_interval_sec
                spontaneous_max = self.cfg.spontaneous_max_backoff_sec
                spontaneous_backoff = min(
                    spontaneous_max,
                    spontaneous_base * (1.5 ** self.spontaneous_idle_count),
                )

                if (silence_dur >= self.cfg.idle_silence_threshold_sec and
                    time_since_last_spontaneous >= spontaneous_backoff):

                    logger.info(
                        f"🌌 [Spontaneous Reflection] Stream quiet for {silence_dur:.0f}s (Mode: {self.engagement_mode.upper()}, "
                        f"Viewers: {self.concurrent_viewers}). Generating commentary..."
                    )
                    self.last_spontaneous_time = now
                    self.last_activity_time = now
                    self.spontaneous_idle_count += 1
                    self.visualizer.fade_out_for_turn()
                    self._trigger_ai_turn(prompt_trigger="[SPONTANEOUS_REFLECTION]", event_type="spontaneous", priority=10)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in idle reflection monitor: {e}")

    async def promo_monitor_task(self):
        """
        Context-aware promotional callout scheduler (Phase 6).
        Event-driven rules:
        - 'Ask Anything' (ask_god):
          Shows when chat has been silent for >= promo_ask_quiet_sec (default 45s),
          concurrent_viewers >= 1, no turn active, and no pinned question active.
        - 'Like & Subscribe' (like_sub):
          Shows within promo_sub_after_turn_sec (default 3s) after a completed non-spontaneous
          turn or celebration, at most once per promo_sub_min_interval_sec (default 300s).
        - Existing rule: Promos NEVER overlap speech or a pinned question.
        """
        if self.cfg.promo_mode != "event" or not self.cfg.promo_overlay_enabled:
            return

        logger.info(
            f"📣 [Promo Monitor] Event-driven promo engine active "
            f"(min gap between any promos: {self.cfg.promo_overlay_interval_sec}s, "
            f"Ask Quiet: {self.cfg.promo_ask_quiet_sec}s, "
            f"Like/Sub Cooldown: {self.cfg.promo_sub_min_interval_sec}s, "
            f"Like/Sub idle fallback: {self.cfg.promo_sub_idle_fallback_sec}s)"
        )

        last_ask_promo_time = 0.0
        last_like_sub_trigger_time = 0.0
        last_any_promo_time = 0.0  # global spacing: no two promos closer than promo_overlay_interval_sec
        min_gap = float(self.cfg.promo_overlay_interval_sec)
        idle_sub_fallback = float(self.cfg.promo_sub_idle_fallback_sec)

        while self.running:
            try:
                await asyncio.sleep(1.0)
                if not self.running:
                    break

                now = time.time()
                # Global spacing applies to every promo type. This is what PROMO_OVERLAY_INTERVAL_SEC means
                # in event mode: the minimum quiet time between any two callouts.
                if now - last_any_promo_time < min_gap:
                    continue

                is_turn_busy = (
                    self.brain.is_generating
                    or self.tts.is_speaking
                    or self.tts.remaining_speech_duration > 0.05
                    or self.active_turn_event is not None
                    or len(self.comment_queue) > 0
                    or self.current_pinned_chat is not None
                )
                is_promo_active = getattr(self.visualizer, "is_promo_active", False)

                if is_turn_busy or is_promo_active:
                    continue

                # 1. Check "Like & Subscribe" promo:
                # Trigger within promo_sub_after_turn_sec after completed non-spontaneous turn or celebration
                time_since_turn_done = now - getattr(self, "last_turn_completed_time", 0.0)
                last_like_sub_completed = self.visualizer.last_promo_completed("like_sub") if hasattr(self.visualizer, "last_promo_completed") else 0.0
                time_since_last_like_sub = now - last_like_sub_completed
                time_since_last_like_sub_trigger = now - last_like_sub_trigger_time
                sub_after_turn_sec = self.cfg.promo_sub_after_turn_sec
                sub_min_interval = self.cfg.promo_sub_min_interval_sec
                last_event_type = getattr(self, "last_turn_event_type", "")

                if (
                    time_since_turn_done <= sub_after_turn_sec
                    and time_since_last_like_sub >= sub_min_interval
                    and time_since_last_like_sub_trigger >= 10.0
                    and last_event_type in ("chat", "superchat", "direct_mention", "cast", "greeting", "celebration")
                ):
                    if len(self.comment_queue) > 0:
                        logger.debug("📣 Post-turn 'like_sub' promo skipped: comment queue has pending items.")
                        continue
                    logger.info("📣 [Promo Trigger] Showing 'Like & Subscribe' callout after completed viewer interaction.")
                    self.visualizer.trigger_promo("like_sub")
                    last_like_sub_trigger_time = now
                    last_any_promo_time = now
                    # Reset turn completed time to avoid double triggering
                    self.last_turn_completed_time = 0.0
                    continue

                # 2. Check Idle Callouts ("Ask Anything" & "Like & Subscribe"):
                # Shows when chat has been silent for >= promo_ask_quiet_sec, viewers >= 1, no active turn
                ask_quiet_sec = self.cfg.promo_ask_quiet_sec
                time_since_last_chat = now - self.last_chat_time
                time_since_last_ask = now - last_ask_promo_time
                viewers = self.concurrent_viewers

                if (
                    viewers >= 1
                    and time_since_last_chat >= ask_quiet_sec
                ):
                    # Idle slot is for 'Ask Anything'. 'Like & Subscribe' belongs after a viewer interaction
                    # (when people are primed to act); during a lull it only appears as a long-absence
                    # fallback so a stream with zero chat still shows it occasionally.
                    if (
                        idle_sub_fallback > 0
                        and time_since_last_like_sub >= idle_sub_fallback
                        and time_since_last_like_sub_trigger >= idle_sub_fallback
                    ):
                        logger.info(f"📣 [Promo Trigger] Showing 'Like & Subscribe' fallback (none completed for {time_since_last_like_sub:.0f}s >= {idle_sub_fallback:.0f}s).")
                        self.visualizer.trigger_promo("like_sub")
                        last_like_sub_trigger_time = now
                        last_any_promo_time = now
                    elif time_since_last_ask >= max(ask_quiet_sec, min_gap):
                        logger.info(f"📣 [Promo Trigger] Showing 'Ask Anything' callout (Chat quiet for {time_since_last_chat:.1f}s >= {ask_quiet_sec:.1f}s).")
                        self.visualizer.trigger_promo("ask_god")
                        last_ask_promo_time = now
                        last_any_promo_time = now

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Promo monitor note: {e}")

    # --------------------------------------------------------------------------
    # 7. High-Precision Audio & 60 FPS Visualizer Video Loop (Synchronized NDI)
    # --------------------------------------------------------------------------
    def _sd_audio_callback(self, outdata, frames, time_info, status):
        """High-priority PortAudio real-time audio callback running on kernel MMCSS thread."""
        if status:
            logger.debug(f"Audio Callback status: {status}")
        outdata[:] = self.tts.pop_local_audio(frames, volume=self.cfg.local_audio_volume)

    async def stream_observability_task(self):
        """
        Periodically logs stream health telemetry HUD to the console (E4).
        """
        logger.info("📊 [Observability HUD] Stream health and telemetry monitor active.")
        await asyncio.sleep(30.0)
        while self.running:
            try:
                await asyncio.sleep(60.0)
                if not self.running:
                    break

                uptime_sec = time.time() - getattr(self, "start_time", time.time())
                hrs, rem = divmod(int(uptime_sec), 3600)
                mins, secs = divmod(rem, 60)
                uptime_str = f"{hrs:02d}:{mins:02d}:{secs:02d}"

                metrics = self.session_log.get_stream_health_metrics() if self.session_log else {}
                cb_status = "TRIPPED (Cooldown)" if getattr(self.brain, "circuit_breaker_tripped", False) else "HEALTHY"
                cache_lvl = self.brain.reflection_cache.size() if hasattr(self.brain, "reflection_cache") else 0
                greet_lvl = self.greeting_cache.size() if hasattr(self, "greeting_cache") else 0
                max_refl = self.cfg.reflection_cache_size
                max_greet = self.cfg.greeting_cache_size

                hud = (
                    f"\n{'='*65}\n"
                    f"📡 [STREAM TELEMETRY HUD] Uptime: {uptime_str} | Mode: {self.engagement_mode.upper()} | Viewers: {self.concurrent_viewers}\n"
                    f"🗣️ AI Turns: {metrics.get('total_turns', 0)} | Cast: {metrics.get('total_cast_questions', 0)} | Chats: {metrics.get('total_chats', 0)} | Avg Latency: {metrics.get('avg_latency_sec', 0.0)}s\n"
                    f"🧠 Caches: Reflection {cache_lvl}/{max_refl}, Greeting {greet_lvl}/{max_greet} | Mood: {self.brain.current_mood.upper()} | TTS: {self.cfg.tts_backend.upper()} | Circuit Breaker: {cb_status}\n"
                    f"{'='*65}"
                )
                logger.info(hud)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Observability HUD note: {e}")

    def _ndi_audio_pump_worker(self):
        """
        Fallback high-priority isochronous audio pump thread for standalone NDI.
        When VisualizerProxy is active, NDI video + audio are broadcast atomically
        inside render_worker.py, so this worker is bypassed to eliminate sender conflicts.
        """
        if isinstance(self.visualizer, VisualizerProxy):
            return

        packet_samples = int(self.ndi.audio_packet_samples) if self.ndi else 2400
        target_interval = packet_samples / 48000.0
        t_next = time.perf_counter()

        while self.running and self.ndi_audio_running:
            try:
                audio_for_ndi, _ = self.tts.pop_audio_packet(packet_samples)
                if self.ndi and self.ndi.is_open:
                    self.ndi.send_audio_packet(audio_for_ndi)
            except Exception as e:
                logger.debug(f"NDI audio pump note: {e}")

            t_next += target_interval
            sleep_sec = t_next - time.perf_counter()
            if sleep_sec > 0.001:
                time.sleep(sleep_sec)
            while time.perf_counter() < t_next:
                pass

    async def video_broadcast_task(self):
        """
        Visualizer state synchronization & event loop lag heartbeat task (20 Hz).
        The 60 FPS Pygame GPU rendering and NDI video broadcasting run decoupled
        inside the dedicated render worker process (Phase 5).
        """
        logger.info(f"🎨 [Visualizer Sync] State synchronizer active ({self.visualizer.width}x{self.visualizer.height} @ 60 FPS in dedicated process).")
        sync_interval = 0.050  # 20 Hz sync rate (50 ms)
        t_last_log = time.time()
        max_loop_lag = 0.0
        sync_count = 0

        try:
            while self.running:
                t_loop_start = time.perf_counter()

                # 0. Check worker health and restart if dead
                if hasattr(self.visualizer, "check_and_restart_if_dead"):
                    self.visualizer.check_and_restart_if_dead()

                # 1. Synchronize orchestrator state with dedicated render worker
                self.visualizer.sync_state(
                    chat_messages=list(self.chat_history)[-50:],
                    obs_connected=self.obs_connected,
                    engagement_mode=self.engagement_mode,
                    concurrent_viewers=self.concurrent_viewers,
                    is_stream_live=self.is_streaming,
                )

                # 2. Check if Pygame preview window was closed
                if getattr(self.visualizer, "should_quit", False):
                    logger.info("Visualizer window closed by user (QUIT event). Shutting down...")
                    self.stop()
                    break

                sync_count += 1
                if sync_count % 40 == 0:  # Every 2 seconds
                    self._update_engagement_state()

                # 3. Heartbeat drift logging every 10 seconds
                if time.time() - t_last_log >= 10.0:
                    elapsed = time.time() - t_last_log
                    logger.info(
                        f"📡 [Event Loop Health] Max Drift: {max_loop_lag * 1000.0:.1f}ms | "
                        f"Mode: {self.engagement_mode.upper()} ({self.concurrent_viewers} viewers) | "
                        f"Mood: {self.visualizer.current_mood.upper()}"
                    )
                    max_loop_lag = 0.0
                    t_last_log = time.time()

                # 4. Measure loop lag and sleep
                t_work = time.perf_counter() - t_loop_start
                sleep_time = max(0.001, sync_interval - t_work)
                t_before_sleep = time.perf_counter()
                await asyncio.sleep(sleep_time)
                actual_sleep = time.perf_counter() - t_before_sleep
                lag = max(0.0, actual_sleep - sleep_time)
                if lag > max_loop_lag:
                    max_loop_lag = lag

        except asyncio.CancelledError:
            logger.debug("video_broadcast_task cancelled.")
        except Exception as e:
            logger.error(f"Fatal error in video_broadcast_task: {e}", exc_info=True)

    # --------------------------------------------------------------------------
    # 8. Main Lifecycle
    # --------------------------------------------------------------------------
    async def start(self):
        """Starts all local subsystems, collector tasks, and render loops."""
        self.running = True
        self.loop = asyncio.get_running_loop()

        logger.info("=" * 65)
        logger.info("ALL-LOCAL AI LIVE STREAM CO-HOST INITIALIZING (OBS HOST PC)")
        logger.info(f"NDI Broadcast Feed: '{self.cfg.ndi_stream_name}' ({self.visualizer.width}x{self.visualizer.height} @ 60fps)")
        tts_backend_name = self.cfg.tts_backend
        logger.info(f"TTS Backend: {tts_backend_name} ({self.cfg.tts_voice}) @ 48kHz Stereo")
        logger.info(f"LLM Brain: {self.cfg.ai_cohost_name} ({self.cfg.gemini_model})")
        logger.info(f"Local OBS WebSocket: {self.cfg.obs_ws_host}:{self.cfg.obs_ws_port}")
        logger.info("=" * 65)

        # Open in-process NDI Streamer only if visualizer is NOT running via dedicated render worker proxy
        if not isinstance(self.visualizer, VisualizerProxy):
            self.ndi.open()
        else:
            logger.info("🎬 [Dedicated Render Worker] NDI Video + Audio broadcasting managed atomically in dedicated render process.")

        # Perform startup health check on primary TTS backend (e.g. remote Chatterbox server)
        try:
            await self.tts.check_health()
        except Exception as e:
            logger.warning(f"Error during initial TTS health check: {e}")

        # Start high-priority dedicated NDI audio pump thread only in fallback in-process mode
        if not isinstance(self.visualizer, VisualizerProxy) and self.cfg.ndi_audio_enabled and not self.ndi.is_mock:
            self.ndi_audio_running = True
            self.ndi_audio_thread = threading.Thread(
                target=self._ndi_audio_pump_worker,
                name="ndi_audio_pump",
                daemon=True,
            )
            self.ndi_audio_thread.start()
            logger.info("🎵 Dedicated Isochronous NDI Audio Pump active (48kHz @ 10ms isochronous packets, zero-jitter).")

        # Initialize local Windows WASAPI / DirectSound / WDM-KS real-time audio callback stream
        self.sd_stream = None
        if self.cfg.local_audio_enabled and sd is not None:
            try:
                target_dev_idx = resolve_wasapi_output_device(self.cfg.local_audio_device)
                dev_info = sd.query_devices(target_dev_idx) if target_dev_idx is not None else None
                dev_name = dev_info["name"] if dev_info else "Default"
                api_name = sd.query_hostapis(dev_info["hostapi"])["name"] if dev_info else "WASAPI"
                latency_setting = self.cfg.local_audio_latency

                self.sd_stream = sd.OutputStream(
                    samplerate=self.cfg.tts_sample_rate,
                    channels=2,
                    dtype="float32",
                    device=target_dev_idx,
                    callback=self._sd_audio_callback,
                    blocksize=0,  # Native hardware blocksize for glitch-free playback
                    latency=latency_setting,
                )
                self.sd_stream.start()
                logger.info(
                    f"🔊 Windows Native Audio active on [{target_dev_idx}] '{dev_name}' "
                    f"(API: {api_name}, Latency: {latency_setting}). "
                    "Glitch-free callback streaming enabled for OBS Window/Application Audio Capture!"
                )
            except Exception as e:
                logger.warning(
                    f"Could not open Windows audio output device: {e}. Audio will continue streaming over NDI."
                )
                self.sd_stream = None
        elif not self.cfg.local_audio_enabled:
            logger.info("Windows Local Audio Output is disabled in configuration.")
        else:
            logger.warning("sounddevice module not available. Install sounddevice for OBS Window audio capture.")

        # Launch concurrent async tasks
        self.tasks = [
            asyncio.create_task(self.video_broadcast_task(), name="video_broadcaster"),
            asyncio.create_task(self.comment_queue_scheduler_task(), name="comment_scheduler"),
            asyncio.create_task(self.obs_monitor_task(), name="obs_monitor"),
            asyncio.create_task(self.youtube_chat_task(), name="youtube_chat"),
            asyncio.create_task(self.youtube_viewer_poller_task(), name="viewer_poller"),
            asyncio.create_task(self.console_chat_task(), name="console_input"),
            asyncio.create_task(self.idle_reflection_monitor_task(), name="idle_reflection"),
            asyncio.create_task(self.stream_observability_task(), name="observability_hud"),
            asyncio.create_task(self.turn_watchdog_task(), name="turn_watchdog"),
        ]

        if self.cfg.cast_enabled:
            self.tasks.append(asyncio.create_task(self.cast_scheduler_task(), name="cast_scheduler"))

        if self.cfg.promo_mode == "event" and self.cfg.promo_overlay_enabled:
            self.tasks.append(asyncio.create_task(self.promo_monitor_task(), name="promo_monitor"))

        if self.cfg.reflection_cache_enabled and hasattr(self.brain, "reflection_cache"):
            self.tasks.append(asyncio.create_task(self.brain.reflection_cache.replenish_worker(self.brain), name="reflection_cache_worker"))

        if self.cfg.greeting_cache_enabled and hasattr(self, "greeting_cache"):
            self.tasks.append(asyncio.create_task(self.greeting_cache.replenish_worker(self.brain, self.tts, self.cfg, poll_interval=self.cfg.greeting_cache_poll_interval_sec), name="greeting_cache_worker"))

        try:
            results = await asyncio.gather(*self.tasks, return_exceptions=True)
            for task, res in zip(self.tasks, results):
                if isinstance(res, Exception) and not isinstance(res, asyncio.CancelledError):
                    logger.error(f"Task '{task.get_name()}' crashed with exception: {res}", exc_info=res)
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            self.stop()

    def _cancel_all_tasks(self):
        """Cancels all active asyncio tasks immediately."""
        tasks = getattr(self, "tasks", [])
        for task in tasks:
            if not task.done():
                task.cancel()

    def stop(self):
        """Cleanly stops all threads, streams, display windows, and background tasks."""
        if getattr(self, "_stopped", False):
            return
        self._stopped = True
        self.running = False

        # 1. Cancel all asyncio tasks on the loop
        if hasattr(self, "loop") and self.loop and self.loop.is_running():
            try:
                self.loop.call_soon_threadsafe(self._cancel_all_tasks)
            except Exception:
                pass

        # Shut down default executor immediately to prevent thread hangs on exit
        if hasattr(self, "loop") and self.loop:
            try:
                if hasattr(self.loop, "_default_executor") and self.loop._default_executor:
                    self.loop._default_executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass

        # Disconnect OBS client if active
        if hasattr(self, "obs_client") and self.obs_client is not None:
            try:
                self.obs_client.disconnect()
                self.obs_client = None
            except Exception:
                pass

        # 2. Stop WASAPI audio output stream
        if hasattr(self, "sd_stream") and self.sd_stream is not None:
            try:
                self.sd_stream.stop()
                self.sd_stream.close()
                self.sd_stream = None
            except Exception:
                pass

        # 3. Destroy visualizer window immediately
        if hasattr(self, "visualizer") and self.visualizer is not None:
            try:
                self.visualizer.close()
            except Exception:
                pass

        # 4. Stop and join NDI audio pump thread
        self.ndi_audio_running = False
        if hasattr(self, "ndi_audio_thread") and self.ndi_audio_thread and self.ndi_audio_thread.is_alive():
            try:
                self.ndi_audio_thread.join(timeout=0.3)
            except Exception:
                pass

        # 5. Close NDI sender
        if hasattr(self, "ndi") and self.ndi is not None:
            try:
                self.ndi.close()
            except Exception:
                pass

        # 6. Finalize session log and record summary in MemoryManager (C4)
        if hasattr(self, "session_log") and self.session_log is not None:
            try:
                summary = self.session_log.get_session_summary()
                self.session_log.close()
                if hasattr(self, "brain") and hasattr(self.brain, "memory_mgr"):
                    self.brain.memory_mgr.record_session_summary(self.session_log.session_id, summary)
            except Exception:
                pass


def main():
    from logging_setup import configure_logging
    configure_logging("MAIN")

    import argparse
    parser = argparse.ArgumentParser(description="All-Local AI Live Stream Co-Host Pipeline (OBS Host)")
    parser.add_argument("--vertical", "-v", action="store_true", help="Launch in 9:16 vertical mode (1080x1920)")
    parser.add_argument("--landscape", "-l", action="store_true", help="Launch in 16:9 landscape mode (1920x1080)")
    parser.add_argument("--aspect-ratio", "-ar", choices=["16:9", "9:16", "vertical", "landscape", "shorts"], default=None)
    parser.add_argument("--native-window", action="store_true", help="Launch visualizer desktop window at full native resolution (1080x1920 or 1920x1080) for 1:1 OBS Window Capture")
    parser.add_argument("--window-size", type=int, nargs=2, metavar=("WIDTH", "HEIGHT"), default=None, help="Explicit visualizer desktop window dimensions (e.g. --window-size 320 180)")
    parser.add_argument("--window-pos", type=int, nargs=2, metavar=("X", "Y"), default=None, help="Explicit visualizer desktop window screen position (e.g. --window-pos 40 40)")
    parser.add_argument("--borderless", action="store_true", help="Launch visualizer in borderless window mode without titlebar/borders")
    parser.add_argument("--headless", action="store_true", help="Run visualizer in offscreen headless mode")
    parser.add_argument("--no-local-audio", action="store_true", help="Disable local Windows audio output (NDI audio only)")
    parser.add_argument("--audio-device", "-ad", type=str, default=None, help="Target Windows audio output device (name substring or index)")
    parser.add_argument("--no-ndi-audio", action="store_true", help="Disable NDI audio stream (video only)")
    parser.add_argument("--local-audio-volume", type=float, default=1.0, help="Local Windows audio volume multiplier (0.0 - 2.0)")
    parser.add_argument("--low-spec", action="store_true", help="Optimize for lower-spec PCs / Intel UHD Graphics (i5-10600)")
    parser.add_argument("--performance-mode", choices=["ultra", "balanced", "eco_low_spec"], default=None, help="Hardware performance tuning mode")
    parser.add_argument("--list-audio-devices", action="store_true", help="List all available Windows audio output devices and exit")
    args = parser.parse_args()

    if args.list_audio_devices:
        print_audio_devices()
        return

    if args.vertical or args.aspect_ratio in ("9:16", "vertical", "shorts"):
        config.visualizer_aspect_ratio = "9:16"
        config.visualizer_width = 1080
        config.visualizer_height = 1920
        if not args.window_size and not args.native_window:
            config.visualizer_window_width = 540
            config.visualizer_window_height = 960
    elif args.landscape or args.aspect_ratio in ("16:9", "landscape"):
        config.visualizer_aspect_ratio = "16:9"
        config.visualizer_width = 1920
        config.visualizer_height = 1080
        if not args.window_size and not args.native_window:
            config.visualizer_window_width = 320
            config.visualizer_window_height = 180

    if args.native_window:
        config.visualizer_native_window = True
        config.visualizer_window_width = config.visualizer_width
        config.visualizer_window_height = config.visualizer_height
    elif args.window_size:
        config.visualizer_window_width = args.window_size[0]
        config.visualizer_window_height = args.window_size[1]

    if args.window_pos:
        config.visualizer_window_x = args.window_pos[0]
        config.visualizer_window_y = args.window_pos[1]

    if args.borderless:
        config.visualizer_borderless = True
    if args.headless:
        config.visualizer_headless = True
    if args.no_local_audio:
        config.local_audio_enabled = False
    if args.audio_device is not None:
        config.local_audio_device = args.audio_device
    if args.no_ndi_audio:
        config.ndi_audio_enabled = False
    if args.local_audio_volume != 1.0:
        config.local_audio_volume = args.local_audio_volume
    if args.low_spec:
        config.low_spec_mode = True
        config.performance_mode = "eco_low_spec"
        config.visualizer_particle_count = 40
    if args.performance_mode:
        config.performance_mode = args.performance_mode
        if args.performance_mode == "eco_low_spec":
            config.visualizer_particle_count = 40

    # Optional Windows main process priority elevation
    if os.environ.get("IAM_ELEVATE_MAIN") == "1":
        try:
            import win32api, win32process, win32con
            pid = win32api.GetCurrentProcessId()
            handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, True, pid)
            win32process.SetPriorityClass(handle, win32process.ABOVE_NORMAL_PRIORITY_CLASS)
            logger.info("⚡ [Main Process] Process priority elevated to ABOVE_NORMAL_PRIORITY_CLASS.")
        except Exception as e:
            logger.debug(f"Main process priority elevation note: {e}")

    app = LocalCoHostApp()

    # Clean signal handling for Ctrl+C, Ctrl+Break, and termination signals
    def _sig_handler(sig, frame):
        sig_name = "Ctrl+Break" if sig == getattr(signal, "SIGBREAK", -1) else "Ctrl+C"
        logger.info(f"Interrupt signal received ({sig_name}). Shutting down AI Co-Host cleanly...")
        try:
            app.stop()
        except Exception:
            pass
        os._exit(0)

    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, _sig_handler)
    except Exception:
        pass

    try:
        asyncio.run(app.start())
    except (KeyboardInterrupt, SystemExit):
        logger.info("AI Co-Host stopped.")
    except Exception as e:
        logger.error(f"Fatal unhandled exception in AI Co-Host: {e}", exc_info=True)
    finally:
        try:
            app.stop()
        except Exception:
            pass
        os._exit(0)


if __name__ == "__main__":
    main()
