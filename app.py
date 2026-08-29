"""
All-Local Live Stream AI Co-Host Pipeline ("Nova" / "I Am").
Consolidated application running solely on the OBS Host machine.
Integrates OBS Studio WebSocket, YouTube Live Chat, Google Gemini LLM,
neural 48kHz TTS synthesis, 1080p60 Pygame visualizer, and local NDI broadcasting.
"""

import asyncio
import collections
from dataclasses import dataclass, field
import json
import logging
import os
import random
import re
import socket
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Deque, Dict, List, Optional

import numpy as np

from ai_brain import AIBrain
from config import config
from ndi_streamer import NDIStreamer
from tts_engine import TTSEngine
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
    print("Tip: Set LOCAL_AUDIO_DEVICE=<index or name> in .env to target a specific device.")
    print("=" * 65)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [AI-COHOST] %(message)s",
    datefmt="%H:%M:%S",
)
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

        pri_str = getattr(config, "process_priority", "above_normal").lower()
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


@dataclass
class CommentEvent:
    """Encapsulates an incoming comment trigger with priority and lifespan."""
    prompt_trigger: str
    event_type: str = "chat"  # "host", "superchat", "direct_mention", "greeting", "chat", "spontaneous"
    priority: int = 5         # Lower number = higher priority (1: Host, 2: Superchat, 3: Direct Mention, 4: Greeting, 5: Chat, 10: Spontaneous)
    created_at: float = field(default_factory=time.time)
    max_age_sec: float = 35.0
    force: bool = False


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
        self.visualizer = Visualizer()
        self.ndi = NDIStreamer()

        # OBS State
        self.obs_client = None
        self.obs_connected = False
        self.is_streaming = False
        self.is_recording = False
        self.current_scene = "Main"
        self.last_transcript_text = ""
        self.last_file_position = 0

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
        self.last_chat_time = 0.0
        self.last_spontaneous_time = time.time()
        self.last_chat_encouragement_time = 0.0
        self.last_viewer_join_welcome_time = 0.0
        self.spontaneous_idle_count = 0
        self.encouragement_idle_count = 0

        # Chat & Subtitle State
        self.current_host_transcript = ""
        self.current_ai_subtitle = ""
        self.chat_history: Deque[Dict] = collections.deque(maxlen=50)
        self.seen_chat_handles: set = set()
        self.discovered_channel_handle: Optional[str] = None

        # Restore previous chat messages into visualizer without re-triggering AI commentary
        self._load_cached_chat()

        # Comment Event Priority Queue & Serialized Scheduling
        self.comment_queue: List[CommentEvent] = []
        self.active_turn_event: Optional[CommentEvent] = None
        self.active_turn_task: Optional[asyncio.Task] = None
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
        """Persists recent chat history to disk for seamless recovery upon restart."""
        try:
            items = list(self.chat_history)[-50:]
            temp_file = self.CHAT_CACHE_FILE.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2)
            temp_file.replace(self.CHAT_CACHE_FILE)
        except Exception as e:
            logger.debug(f"Failed to save chat cache: {e}")

    # --------------------------------------------------------------------------
    # 1. State & Engagement State Management
    # --------------------------------------------------------------------------
    def _wake_up_and_trigger_comment(self, viewers: int):
        """
        Wakes up the system when a viewer enters an empty room (0 -> 1+) or on initial boot with active viewers.
        Immediately triggers the next scripted comment event and establishes the active cadence.
        """
        now = time.time()
        cooldown = getattr(self.cfg, "viewer_join_cooldown_sec", 60.0)
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
        should_greet = getattr(self.cfg, "greet_viewer_joins", False)
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
            logger.info(f"⚡ [Room Wake-Up] Viewer entered empty room ({viewers} active). Immediately performing comment event: {prompt}...")
            self._trigger_ai_turn(prompt_trigger=prompt, force=False)
        else:
            logger.info(f"⚡ [Room Wake-Up] Viewer entered empty room ({viewers} active). Room transitioned to ACTIVE.")

    def _on_viewer_count_update(self, new_viewers: int, new_chat_velocity: int = 0):
        """Processes viewer count updates and manages active vs eco engagement transitions."""
        prev_viewers = self.concurrent_viewers
        self.concurrent_viewers = new_viewers
        self.chat_velocity = new_chat_velocity
        now = time.time()
        min_viewers = getattr(self.cfg, "min_concurrent_viewers_active", 1)

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
            self._wake_up_and_trigger_comment(new_viewers)

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
            is_chat_recently_active = (now - self.last_chat_time < self.cfg.chat_idle_timeout_sec)
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
    ):
        """Thread-safe and async-safe enqueueing of AI comment turns with priority and backpressure."""
        if not prompt_trigger or not self.running:
            return

        # Default priorities & TTLs based on event type
        priority_map = {
            "host": (1, 60.0),
            "superchat": (2, 60.0),
            "direct_mention": (3, 40.0),
            "greeting": (4, 30.0),
            "chat": (5, 30.0),
            "spontaneous": (10, 15.0),
        }
        def_pri, def_ttl = priority_map.get(event_type.lower(), (5, 30.0))
        prio = priority if priority is not None else def_pri
        ttl = max_age_sec if max_age_sec is not None else def_ttl

        # Spontaneous Gating: Never queue spontaneous reflections if AI is busy speaking, generating, or queue is active
        if event_type == "spontaneous":
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

        event = CommentEvent(
            prompt_trigger=prompt_trigger,
            event_type=event_type,
            priority=prio,
            created_at=time.time(),
            max_age_sec=ttl,
            force=force,
        )

        if force:
            if self.active_turn_task and not self.active_turn_task.done():
                self.active_turn_task.cancel()
            self.tts.clear_audio_buffer()
            self.comment_queue.insert(0, event)
            if self.new_comment_signal:
                self.new_comment_signal.set()
            logger.info(f"⚡ [Forced AI Turn] Dispatched immediate interrupt for: '{prompt_trigger[:60]}...'")
            return

        # Backpressure & Queue Overflow Management (Max 3 pending items)
        max_queue = 3
        if len(self.comment_queue) >= max_queue:
            # Find lowest-priority (highest numerical value) item in queue
            lowest_prio_idx = max(range(len(self.comment_queue)), key=lambda i: self.comment_queue[i].priority)
            lowest_item = self.comment_queue[lowest_prio_idx]

            if prio < lowest_item.priority:
                # Evict lower priority item to make room for this higher priority event
                evicted = self.comment_queue.pop(lowest_prio_idx)
                logger.info(f"⚠️ [Queue Eviction] Evicted lower-priority '{evicted.event_type}' request to prioritize incoming '{event_type}'.")
                self.comment_queue.append(event)
            else:
                logger.info(f"🛑 [Queue Full] Dropped '{event_type}' request ('{prompt_trigger[:45]}...') to prevent response latency backlog.")
                return
        else:
            self.comment_queue.append(event)

        # Sort queue by priority first (1=highest), then arrival time (oldest first)
        self.comment_queue.sort(key=lambda x: (x.priority, x.created_at))
        if self.new_comment_signal:
            self.new_comment_signal.set()
        logger.info(f"📥 [Queued Comment] Added '{event_type}' (Pri: {prio}, Queue: {len(self.comment_queue)}): '{prompt_trigger[:60]}...'")

    async def comment_queue_scheduler_task(self):
        """
        Dedicated sequential comment scheduler task.
        Executes one AI speech turn at a time, strictly waiting for complete audio
        playback before proceeding to the next event or clearing the screen.
        """
        logger.info("🧠 [Comment Scheduler] Serialized AI turn scheduler active.")
        if self.new_comment_signal is None:
            self.new_comment_signal = asyncio.Event()

        while self.running:
            try:
                # Prune stale events from queue before taking the next one
                now = time.time()
                valid_queue = []
                for ev in self.comment_queue:
                    if now - ev.created_at <= ev.max_age_sec:
                        valid_queue.append(ev)
                    else:
                        logger.info(f"⏱️ [Stale Request Pruned] Dropped '{ev.event_type}' request ({now - ev.created_at:.1f}s old) to keep co-host real-time.")
                self.comment_queue = valid_queue

                if not self.comment_queue:
                    self.new_comment_signal.clear()
                    try:
                        await asyncio.wait_for(self.new_comment_signal.wait(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    continue

                # Pop highest priority event
                event = self.comment_queue.pop(0)
                self.active_turn_event = event
                self.active_turn_task = asyncio.current_task()

                # Execute full sequential turn
                await self._execute_ai_turn(event)

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

        # 1. Clear previous subtitle card
        self.visualizer.clear_subtitle()
        self.current_ai_subtitle = ""

        full_statement = ""
        is_completed = False
        active_mood = "energetic"
        try:
            # 3. Stream from Gemini AI Brain
            async for chunk_ev in self.brain.generate_response_stream(event.prompt_trigger):
                ev_type = chunk_ev.get("type", "")
                if ev_type == "mood":
                    active_mood = chunk_ev.get("mood", "chill")
                    self.visualizer.set_mood(active_mood)
                elif ev_type == "complete":
                    full_text = chunk_ev.get("full_text", "").strip()
                    mood = chunk_ev.get("mood", active_mood)
                    full_statement = full_text
                    is_completed = True
                    self.visualizer.set_mood(mood)

            # 4. Synthesize speech and begin typewriter display
            clean_speech = full_statement.strip()
            words = clean_speech.split()
            if (
                is_completed
                and len(clean_speech) >= 12
                and len(words) >= 3
                and clean_speech[-1] in ".!?\"'”’)"
            ):
                logger.info(f"🔊 [AI Speech] Synthesizing audio for: '{clean_speech}'")
                await self.tts.queue_speech(clean_speech)
                self.current_ai_subtitle = clean_speech
                self.visualizer.set_subtitle(clean_speech)

                # 5. CRITICAL: Wait until audio has completely finished broadcasting out
                await self.tts.wait_until_speech_completed()
                logger.info(f"✅ [Turn Completed] Speech playback finished cleanly ({time.perf_counter() - t_start:.2f}s total turn time).")
            else:
                logger.warning(f"Incomplete, truncated, or empty response generated ('{clean_speech}'). Suppressing subtitle card.")
                self.visualizer.clear_subtitle()
                self.current_ai_subtitle = ""

        except asyncio.CancelledError:
            logger.debug("Active AI turn was cancelled.")
            self.visualizer.clear_subtitle()
            self.current_ai_subtitle = ""
            self.tts.clear_audio_buffer()
        except Exception as e:
            logger.error(f"Error executing AI turn: {e}", exc_info=True)
            self.visualizer.clear_subtitle()
            self.current_ai_subtitle = ""
        finally:
            self.last_activity_time = time.time()
            self.last_spontaneous_time = time.time()

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
        """Monitors local OBS Studio for broadcast status, scenes, and microphone speech transcripts."""
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
                    getattr(self.cfg, "obs_connect_timeout", 0.2),
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
                    await asyncio.sleep(getattr(self.cfg, "obs_retry_interval_sec", 5.0))
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
                stream_poll_interval = getattr(self.cfg, "obs_stream_status_poll_interval", 2.0)

                while self.running:
                    now = time.time()
                    check_stream = (now - last_stream_check >= stream_poll_interval)
                    if check_stream:
                        last_stream_check = now

                    source_name = self.cfg.obs_transcript_source_name

                    # 3. Offload all synchronous OBS request-responses to thread pool
                    def _poll_obs_sync():
                        res_st = ws_client.call(obs_requests.GetStreamStatus()) if check_stream else None
                        res_sc = ws_client.call(obs_requests.GetCurrentProgramScene()) if check_stream else None
                        res_tr = ws_client.call(obs_requests.GetInputSettings(inputName=source_name))
                        return res_st, res_sc, res_tr

                    try:
                        res_stream, res_scene, res_transcript = await loop.run_in_executor(None, _poll_obs_sync)
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

                    # Process transcript
                    if res_transcript and getattr(res_transcript, "status", False):
                        settings = res_transcript.getSettings()
                        text = settings.get("text", "").strip()
                        if text and text != self.last_transcript_text:
                            self.last_transcript_text = text
                            logger.info(f"🎙️ [OBS Transcript] {text}")
                            self.current_host_transcript = text
                            self.brain.add_transcript("Host", text)
                            self.last_activity_time = time.time()

                            if not self.cfg.chat_reader_mode:
                                should_trigger, reason = self.brain.should_trigger_response(text, is_host=True)
                                if should_trigger:
                                    logger.info(f"Triggering AI response for host transcript: {reason}")
                                    self._trigger_ai_turn(prompt_trigger=f"Host said: '{text}'", event_type="host", priority=1)

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
                await asyncio.sleep(getattr(self.cfg, "obs_retry_interval_sec", 5.0))

    # --------------------------------------------------------------------------
    # 4. Local Transcript File Watcher (LocalVocal / Whisper fallback)
    # --------------------------------------------------------------------------
    async def transcript_file_task(self):
        """Asynchronously tails a local speech-to-text / SRT transcript file."""
        file_path = self.cfg.transcript_file_path
        if not file_path:
            return

        logger.info(f"Watching transcript file: {file_path}")
        while self.running:
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        f.seek(self.last_file_position)
                        lines = f.readlines()
                        self.last_file_position = f.tell()

                        for line in lines:
                            line_clean = line.strip()
                            if line_clean and not line_clean.isdigit() and "-->" not in line_clean:
                                logger.info(f"🎙️ [File Transcript] {line_clean}")
                                self.current_host_transcript = line_clean
                                self.brain.add_transcript("Host", line_clean)
                                self.last_activity_time = time.time()

                                if not self.cfg.chat_reader_mode:
                                    should_trigger, reason = self.brain.should_trigger_response(line_clean, is_host=True)
                                    if should_trigger:
                                        self._trigger_ai_turn(prompt_trigger=f"Host said: '{line_clean}'", event_type="host", priority=1)
                except Exception as e:
                    logger.debug(f"Error reading transcript file: {e}")
            await asyncio.sleep(0.3)

    # --------------------------------------------------------------------------
    # 5. YouTube Live Chat Poller & Mock Generator
    # --------------------------------------------------------------------------
    async def youtube_chat_task(self):
        """Polls YouTube Live Chat via pytchat or runs simulated stream chat."""
        raw_input = (
            self.cfg.youtube_video_id.strip()
            or getattr(self.cfg, "youtube_channel_handle", "").strip()
            or getattr(self.cfg, "host_streamer_handle", "").strip()
        )

        if self.cfg.mock_chat_enabled:
            logger.info("Using Mock Chat Generator (MOCK_CHAT_ENABLED=true)")
            await self._run_mock_chat_generator()
            return

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

                        # Comprehensive set of channel, host, and AI cohost handles to prevent self-triggering
                        own_identifiers = {
                            "host",
                            "owner",
                            "broadcaster",
                        }
                        for val in [
                            self.cfg.host_streamer_handle,
                            self.cfg.youtube_channel_handle,
                            self.cfg.host_streamer_name,
                            getattr(self.cfg, "ai_cohost_name", ""),
                            self.discovered_channel_handle,
                        ]:
                            if val:
                                v_clean = val.lower().strip().lstrip("@")
                                own_identifiers.add(v_clean)
                                own_identifiers.add(v_clean.replace(" ", "").replace("_", "").replace("-", ""))

                        for ch in getattr(self.cfg, "channel_handles", []):
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
                                self.brain.update_channel_identity(clean_handle, author_name, self.cfg.host_streamer_name)

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
                                self._trigger_ai_turn(prompt_trigger=prompt, event_type="superchat", priority=2)

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
                            )

                        # Record chat entry
                        now_ts = time.time()
                        self.chat_timestamps.append(now_ts)
                        if not is_channel_owner:
                            self.last_chat_received_time = now_ts
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
                        self.last_activity_time = now_ts
                        self.last_chat_time = now_ts
                        self.spontaneous_idle_count = 0
                        self.encouragement_idle_count = 0

                        if not is_channel_owner and self.concurrent_viewers < 1:
                            self.concurrent_viewers = 1

                        self._update_engagement_state()

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
                            spoken_text = f"Superchat from @{author_name} for {item.amountString}! {msg}" if is_superchat else f"@{author_name} says, {msg}"
                            mood = "hyped" if is_superchat else "energetic"
                            self.visualizer.set_mood(mood)
                            self.current_ai_subtitle = f"💬 @{author_name}: {msg}"
                            self.visualizer.set_subtitle(self.current_ai_subtitle)
                            asyncio.create_task(self.tts.queue_speech(spoken_text))
                        elif is_new_chatter and self.cfg.greet_new_chatters:
                            should_trigger, reason = self.brain.should_trigger_response(msg, is_host=False, is_new_chatter=True)
                            if is_superchat or should_trigger:
                                prompt = (
                                    f"[NEW_CHATTER_GREETING] @{author_name} just sent their very first message: '{msg}'. "
                                    f"Greet @{author_name} warmly and wittily by name while responding to their comment!"
                                )
                                self._trigger_ai_turn(prompt_trigger=prompt, event_type="greeting", priority=4)
                        else:
                            should_trigger, reason = self.brain.should_trigger_response(msg, is_host=False)
                            if is_superchat or should_trigger:
                                prefix = f"Chat message from @{author_name}"
                                prio = 2 if is_superchat else (3 if "direct_mention" in reason else 5)
                                ev_type = "superchat" if is_superchat else ("direct_mention" if "direct_mention" in reason else "chat")
                                self._trigger_ai_turn(prompt_trigger=f"{prefix}: '{msg}'", event_type=ev_type, priority=prio)
                            else:
                                if "member_reply_entanglement" in reason:
                                    logger.info(f"⏸️ [Chat Filtered] Not triggering AI ({reason}). Preserving member entanglement.")
                                elif "eco_mode_suppressed" in reason:
                                    logger.info(f"🌙 [Eco Mode Throttled] Not triggering AI ({reason}).")

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
        poll_interval = self.cfg.viewer_count_poll_interval
        if not self.cfg.auto_track_live_viewers:
            return

        logger.info(f"Starting YouTube Live Concurrent Viewer Poller (every {poll_interval}s)...")
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
                        idle_timeout = self.cfg.chat_idle_timeout_sec
                        if self.last_chat_received_time > 0 and (now - self.last_chat_received_time) > idle_timeout:
                            if self.concurrent_viewers > 0:
                                logger.info("🌙 [Chat Inactive] No recent chat activity; resetting viewer count to 0 (ECO mode).")
                                self._on_viewer_count_update(0, 0)
                else:
                    if self.cfg.mock_chat_enabled:
                        simulated_viewers = max(5, chat_velocity * 3)
                        self._on_viewer_count_update(simulated_viewers, chat_velocity)

            except Exception as e:
                logger.debug(f"Viewer poller cycle note: {e}")

            await asyncio.sleep(poll_interval)

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
            f"Console Chat Input active: Type comments in terminal (e.g. '{self.cfg.host_streamer_name}: Celebrate!' "
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
                    author = "Host"
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
                        self._trigger_ai_turn(prompt_trigger=prompt, event_type="superchat", priority=2)
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
                        self._trigger_ai_turn(prompt_trigger=prompt, event_type="superchat", priority=2)
                    continue

                # Celebration command
                if msg_lower in ("celebrate!", "celebrate", "!celebrate", "party!", "let's celebrate", "lets celebrate") or msg_lower.startswith("celebrate!"):
                    logger.info(f"🎉 [Console Event] Celebration trigger from {author}: '{message}'")
                    self.visualizer.trigger_celebration(duration=5.0)
                    await self.trigger_obs_fx(duration_sec=5.0)
                    self._trigger_ai_turn(
                        prompt_trigger=f"[CELEBRATION] Host @{author} called for a celebration: '{message}'. Hyped celebration response!",
                        event_type="superchat",
                        priority=2,
                    )
                    continue

                is_host_author = author.lower() in ("host", "owner", self.cfg.host_streamer_name.lower(), self.cfg.host_streamer_handle.lower().lstrip("@"))
                author_type = "owner" if is_host_author else "viewer"

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
                self.last_activity_time = time.time()
                self.last_chat_time = time.time()
                self.spontaneous_idle_count = 0
                self.encouragement_idle_count = 0

                should_trigger, reason = self.brain.should_trigger_response(message, is_host=is_host_author)
                if should_trigger:
                    prefix = f"Host @{author} in chat" if is_host_author else f"Chat message from @{author}"
                    prio = 1 if is_host_author else (3 if "direct_mention" in reason else 5)
                    ev_type = "host" if is_host_author else ("direct_mention" if "direct_mention" in reason else "chat")
                    self._trigger_ai_turn(prompt_trigger=f"{prefix}: '{message}'", event_type=ev_type, priority=prio)

            except (KeyboardInterrupt, asyncio.CancelledError):
                self.stop()
                break
            except Exception as e:
                logger.debug(f"Console input error: {e}")
                await asyncio.sleep(0.5)

    async def _run_mock_chat_generator(self):
        """Generates realistic stream chat messages for testing and offline rehearsal."""
        host_name = self.cfg.host_streamer_name
        cohost_name = self.cfg.ai_cohost_name
        mock_viewers = [
            ("CyberViper", f"Hey {host_name} & {cohost_name}! Ready for the stream!"),
            ("NeonGamer99", f"{cohost_name} what do you think about the new update?"),
            ("PixelPanda", "LMAO that was crazy!!"),
            ("RetroByte", "W streamer + W AI cohost"),
            ("ShadowRider", f"Hey {cohost_name}, can you roast the host real quick?"),
            ("AeroBlade", "That clutch play was 10/10"),
            ("GlitchCat", "Super stoked for today's live build"),
            ("QuantumTech", f"{cohost_name}, what is the nature of consciousness?"),
            ("Valkyrie", "Let's goooo! 🔥🔥🔥"),
            ("CodeSamurai", "All local architecture is blazing fast!"),
        ]

        while self.running:
            await asyncio.sleep(random.uniform(4.0, 8.0))
            author, message = random.choice(mock_viewers)
            is_sc = random.random() < 0.08
            sc_amount = "$5.00" if is_sc else ""

            now_ts = time.time()
            self.chat_timestamps.append(now_ts)

            chat_entry = {
                "author": author,
                "author_type": "member" if is_sc else "viewer",
                "message": message,
                "is_superchat": is_sc,
                "amount": sc_amount,
                "timestamp": now_ts,
            }
            self.chat_history.append(chat_entry)
            self._save_cached_chat()
            self.brain.add_chat_message(author, message, is_sc, sc_amount)
            self.last_activity_time = now_ts
            self.last_chat_time = now_ts

            logger.info(f"💬 [Simulated Chat] @{author}: {message} {f'({sc_amount})' if is_sc else ''}")

            should_trigger, reason = self.brain.should_trigger_response(message, is_host=False)
            if is_sc or should_trigger:
                prio = 2 if is_sc else (3 if "direct_mention" in reason else 5)
                ev_type = "superchat" if is_sc else ("direct_mention" if "direct_mention" in reason else "chat")
                self._trigger_ai_turn(prompt_trigger=f"Chat message from @{author}: '{message}'", event_type=ev_type, priority=prio)

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

                if self.engagement_mode != "active" or self.concurrent_viewers == 0:
                    continue

                now = time.time()
                if (
                    self.brain.is_generating
                    or self.tts.is_speaking
                    or self.tts.remaining_speech_duration > 0.05
                    or self.active_turn_event is not None
                    or len(self.comment_queue) > 0
                ):
                    continue

                silence_dur = now - self.last_activity_time
                time_since_last_spontaneous = now - self.last_spontaneous_time
                time_since_last_chat = now - self.last_chat_time
                time_since_last_encouragement = now - self.last_chat_encouragement_time
                encouragement_enabled = getattr(self.cfg, "chat_encouragement_enabled", False)
                encouragement_base_interval = getattr(self.cfg, "chat_encouragement_interval_sec", 300.0)
                encouragement_backoff = min(600.0, encouragement_base_interval * (1.5 ** self.encouragement_idle_count))

                # 1. Chat Encouragement: Viewers watching, but chat silent (only if enabled)
                if (encouragement_enabled and
                    encouragement_base_interval > 0 and
                    time_since_last_chat >= encouragement_backoff and
                    time_since_last_encouragement >= encouragement_backoff and
                    silence_dur >= 30.0):

                    logger.info(
                        f"📣 [Chat Encouragement] {self.concurrent_viewers} viewers watching, chat silent for {time_since_last_chat:.0f}s. "
                        "Triggering AI co-host call-to-action..."
                    )
                    self.last_chat_encouragement_time = now
                    self.last_activity_time = now
                    self.last_spontaneous_time = now
                    self.encouragement_idle_count += 1
                    self.visualizer.set_mood("hyped")
                    host_name = self.cfg.host_streamer_name
                    chan_handle = self.cfg.youtube_channel_handle
                    prompt = (
                        f"[CHAT_ENCOURAGEMENT] There are currently {self.concurrent_viewers} viewers watching on {chan_handle} with {host_name}, "
                        f"but chat has been quiet. "
                        f"Deliver a witty, engaging call-to-action to wake up the chat: tell them to drop comments or roast {host_name}!"
                    )
                    self._trigger_ai_turn(prompt_trigger=prompt, event_type="spontaneous", priority=10)

                # 2. General Spontaneous Reflection with Adaptive Backoff
                spontaneous_base = getattr(self.cfg, "spontaneous_min_interval_sec", 60.0)
                spontaneous_max = getattr(self.cfg, "spontaneous_max_backoff_sec", 600.0)
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
                    self._trigger_ai_turn(prompt_trigger="[SPONTANEOUS_REFLECTION]", event_type="spontaneous", priority=10)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in idle reflection monitor: {e}")

    # --------------------------------------------------------------------------
    # 7. High-Precision Audio & 60 FPS Visualizer Video Loop (Synchronized NDI)
    # --------------------------------------------------------------------------
    def _sd_audio_callback(self, outdata, frames, time_info, status):
        """High-priority PortAudio real-time audio callback running on kernel MMCSS thread."""
        if status:
            logger.debug(f"Audio Callback status: {status}")
        outdata[:] = self.tts.pop_local_audio(frames, volume=getattr(self.cfg, "local_audio_volume", 1.0))

    def _ndi_audio_pump_worker(self):
        """
        High-priority isochronous audio pump thread for NDI.
        Pumps 480 audio samples (10ms @ 48kHz) directly to NDI, completely
        decoupled from video rendering delays to guarantee zero buffer underruns in OBS.
        """
        packet_samples = 480
        target_interval = packet_samples / 48000.0  # 0.010 s
        t_next = time.perf_counter()

        while self.running and self.ndi_audio_running:
            try:
                audio_for_ndi, _ = self.tts.pop_audio_packet(packet_samples)
                if self.ndi and self.ndi.is_open:
                    self.ndi.send_audio(audio_for_ndi)
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
        60 FPS visualizer rendering and asynchronous NDI video transmission.
        Audio is pumped concurrently by the dedicated _ndi_audio_pump_worker and/or PortAudio callback.
        Guarantees zero audio jitter, zero sample drift, and perfect lip-sync in OBS.
        """
        logger.info(f"Starting 60 FPS Visualizer Video Loop ({self.visualizer.width}x{self.visualizer.height} @ 60fps + 48kHz Audio)...")
        target_frame_time = 1.0 / self.cfg.visualizer_fps  # 16.666 ms

        frame_count = 0
        t_last_log = time.time()
        next_frame_time = time.perf_counter() + target_frame_time
        try:
            while self.running:
                audio_metrics = self.tts.get_audio_metrics()
                chat_list = list(self.chat_history)

                # 1. Render visualizer frame
                rgba_bytes = self.visualizer.render_frame(
                    audio_metrics=audio_metrics,
                    chat_messages=chat_list,
                    host_transcript=self.current_host_transcript,
                    ai_subtitle=self.current_ai_subtitle,
                    host_connected=True,
                    obs_connected=self.obs_connected,
                    engagement_mode=self.engagement_mode,
                    concurrent_viewers=self.concurrent_viewers,
                    is_stream_live=self.is_streaming,
                )

                # 2. Transmit video frame asynchronously over NDI (zero copy, zero drift)
                self.ndi.send_video(rgba_bytes)

                if getattr(self.visualizer, "should_quit", False):
                    logger.info("Visualizer window closed by user (QUIT event). Shutting down...")
                    self.stop()
                    break

                frame_count += 1
                if frame_count % 120 == 0:
                    self._update_engagement_state()

                if time.time() - t_last_log >= 10.0:
                    elapsed = time.time() - t_last_log
                    measured_fps = frame_count / elapsed
                    num_connections = self.ndi.get_num_connections()
                    logger.info(
                        f"Broadcasting: {measured_fps:.1f} FPS | NDI Receivers: {num_connections} | "
                        f"Mode: {self.engagement_mode.upper()} ({self.concurrent_viewers} viewers) | "
                        f"Mood: {self.visualizer.current_mood.upper()}"
                    )
                    frame_count = 0
                    t_last_log = time.time()

                now = time.perf_counter()
                sleep_time = max(0.0005, next_frame_time - now)
                await asyncio.sleep(sleep_time)
                next_frame_time += target_frame_time
                if now - next_frame_time > target_frame_time * 2:
                    next_frame_time = now + target_frame_time

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
        logger.info(f"TTS Engine: {self.cfg.tts_engine} ({self.cfg.tts_voice}) @ 48kHz Stereo")
        logger.info(f"LLM Brain: {self.cfg.ai_cohost_name} ({self.cfg.gemini_model})")
        logger.info(f"Local OBS WebSocket: {self.cfg.obs_ws_host}:{self.cfg.obs_ws_port}")
        logger.info("=" * 65)

        self.ndi.open()

        # Perform startup health check on primary TTS backend (e.g. remote Chatterbox server)
        try:
            await self.tts.check_health()
        except Exception as e:
            logger.warning(f"Error during initial TTS health check: {e}")

        # Start high-priority dedicated NDI audio pump thread
        if getattr(self.cfg, "ndi_audio_enabled", True) and not self.ndi.is_mock:
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
        if getattr(self.cfg, "local_audio_enabled", True) and sd is not None:
            try:
                target_dev_idx = resolve_wasapi_output_device(self.cfg.local_audio_device)
                dev_info = sd.query_devices(target_dev_idx) if target_dev_idx is not None else None
                dev_name = dev_info["name"] if dev_info else "Default"
                api_name = sd.query_hostapis(dev_info["hostapi"])["name"] if dev_info else "WASAPI"
                latency_setting = getattr(self.cfg, "local_audio_latency", "high")

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
        elif not getattr(self.cfg, "local_audio_enabled", True):
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
            asyncio.create_task(self.transcript_file_task(), name="transcript_watcher"),
            asyncio.create_task(self.console_chat_task(), name="console_input"),
            asyncio.create_task(self.idle_reflection_monitor_task(), name="idle_reflection"),
        ]

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


def main():
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
    parser.add_argument("--mock-chat", action="store_true", help="Enable simulated YouTube live chat")
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
    if args.mock_chat:
        config.mock_chat_enabled = True
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

    app = LocalCoHostApp()

    # Clean signal handling for Ctrl+C, Ctrl+Break, and termination signals
    import signal
    def _sig_handler(sig, frame):
        sig_name = "Ctrl+Break" if sig == getattr(signal, "SIGBREAK", -1) else "Ctrl+C"
        logger.info(f"Interrupt signal received ({sig_name}). Shutting down AI Co-Host cleanly...")
        try:
            app.stop()
        except Exception:
            pass
        import os
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
        import os
        os._exit(0)


if __name__ == "__main__":
    main()
