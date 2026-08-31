"""
YouTube Shorts Related Video Link Updater Subsystem.
Automatically discovers all YouTube Shorts on the configured channel and links
their 'Related Video' button to the active live stream ID upon startup.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("shorts_updater")


def parse_cookie_source(
    raw_cookies: str = "",
    cookies_file: str = "youtube_cookies.txt",
) -> Dict[str, str]:
    """
    Parses cookies from:
    1. Direct raw string (e.g. 'SAPISID=...; __Secure-1PSID=...; LOGIN_INFO=...')
    2. JSON file (dict or list of cookie dicts)
    3. Netscape format cookies.txt file
    """
    cookies: Dict[str, str] = {}

    # 1. Try direct raw cookie string
    if raw_cookies and raw_cookies.strip():
        cookie_str = raw_cookies.strip()
        # Check if JSON string
        if cookie_str.startswith("{") and cookie_str.endswith("}"):
            try:
                parsed = json.loads(cookie_str)
                if isinstance(parsed, dict):
                    return {str(k): str(v) for k, v in parsed.items()}
            except Exception:
                pass

        for part in cookie_str.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                cookies[k.strip()] = v.strip()
        if cookies:
            return cookies

    # 2. Try file path
    target_path = cookies_file.strip() if cookies_file else ""
    if not target_path:
        target_path = "youtube_cookies.txt"

    if os.path.exists(target_path):
        try:
            with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()

            if content.startswith("{") or content.startswith("["):
                try:
                    data = json.loads(content)
                    if isinstance(data, dict):
                        return {str(k): str(v) for k, v in data.items()}
                    elif isinstance(data, list):
                        # List of cookie dicts (e.g. from browser extension export)
                        for item in data:
                            if isinstance(item, dict) and "name" in item and "value" in item:
                                cookies[item["name"]] = item["value"]
                        return cookies
                except Exception:
                    pass

            # Netscape format (tab-separated)
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    name = parts[5].strip()
                    val = parts[6].strip()
                    cookies[name] = val
                elif "=" in line:
                    for part in line.split(";"):
                        if "=" in part:
                            k, v = part.split("=", 1)
                            cookies[k.strip()] = v.strip()
        except Exception as e:
            logger.debug(f"Error loading cookies from '{target_path}': {e}")

    return cookies


def compute_sapisid_hash(sapisid: str, origin: str = "https://studio.youtube.com") -> Tuple[int, str]:
    """
    Computes standard SAPISIDHASH authentication header used by YouTube Studio.
    Formula: SHA1("{timestamp} {sapisid} {origin}")
    """
    now_sec = int(time.time())
    to_hash = f"{now_sec} {sapisid} {origin}".encode("utf-8")
    sha_hash = hashlib.sha1(to_hash).hexdigest()
    return now_sec, sha_hash


class ShortsRelatedVideoUpdater:
    """
    Discovers channel Shorts and batch-updates their Related Video link to the active stream ID.
    Maintains persistent JSON cache for idempotency across app restarts.
    """

    def __init__(
        self,
        channel_handle: str = "@MassiveGodComplex",
        channel_id: str = "",
        api_key: str = "",
        raw_cookies: str = "",
        cookies_file: str = "youtube_cookies.txt",
        strategy: str = "studio_api",
        max_batch_size: int = 50,
        cache_file: str = "data/shorts_related_video_cache.json",
    ):
        self.channel_handle = channel_handle.strip()
        self.channel_id = channel_id.strip()
        self.api_key = api_key.strip()
        self.raw_cookies = raw_cookies.strip()
        self.cookies_file = cookies_file.strip()
        self.strategy = strategy.strip().lower()  # "studio_api", "description_link", "both"
        self.max_batch_size = max_batch_size
        self.cache_file = cache_file

        self.cookies: Dict[str, str] = parse_cookie_source(self.raw_cookies, self.cookies_file)
        self.cache: Dict[str, Any] = self._load_cache()

    def _load_cache(self) -> Dict[str, Any]:
        """Loads persistent JSON cache tracking which shorts have been updated."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.debug(f"Error reading cache file '{self.cache_file}': {e}")
        return {"last_stream_id": "", "updated_shorts": {}}

    def _save_cache(self):
        """Persists updated cache to disk."""
        try:
            os.makedirs(os.path.dirname(self.cache_file) or ".", exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.debug(f"Error saving cache to '{self.cache_file}': {e}")

    def discover_channel_shorts(self) -> List[Dict[str, str]]:
        """
        Discovers Shorts published on the configured channel.
        1. First tries public /shorts tab HTML parsing (fast, 0 quota).
        2. If empty and api_key present, queries uploads playlist.
        """
        shorts: List[Dict[str, str]] = []
        seen_ids = set()

        # Strategy 1: Public Shorts Tab Scraper
        handle_clean = self.channel_handle.lstrip("@")
        if handle_clean:
            url = f"https://www.youtube.com/@{handle_clean}/shorts"
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")

                # Match video IDs in shortsLockupViewModel or richItemRenderer
                matches = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
                for vid in matches:
                    if vid not in seen_ids:
                        seen_ids.add(vid)
                        shorts.append({"video_id": vid, "title": f"Short {vid}", "source": "public_shorts_tab"})
                        if len(shorts) >= self.max_batch_size:
                            break

                logger.info(f"📱 [Shorts Discovery] Found {len(shorts)} Shorts from public channel tab '@{handle_clean}'.")
                if shorts:
                    return shorts
            except Exception as e:
                logger.debug(f"Public shorts tab query notice: {e}")

        # Strategy 2: YouTube Data API v3 Uploads Playlist (Fallback)
        if self.api_key and (self.channel_id or self.channel_handle):
            try:
                chan_param = f"id={self.channel_id}" if self.channel_id else f"forHandle={self.channel_handle}"
                chan_url = f"https://www.googleapis.com/youtube/v3/channels?part=contentDetails,snippet&{chan_param}&key={self.api_key}"
                req = urllib.request.Request(chan_url, headers={"User-Agent": "YouTubeAIHost/1.0", "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    chan_data = json.loads(resp.read().decode("utf-8"))

                items = chan_data.get("items", [])
                if items:
                    uploads_id = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", "")
                    if uploads_id:
                        pl_url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet,contentDetails&playlistId={uploads_id}&maxResults={self.max_batch_size}&key={self.api_key}"
                        req_pl = urllib.request.Request(pl_url, headers={"User-Agent": "YouTubeAIHost/1.0", "Accept": "application/json"})
                        with urllib.request.urlopen(req_pl, timeout=8) as resp_pl:
                            pl_data = json.loads(resp_pl.read().decode("utf-8"))

                        for pl_item in pl_data.get("items", []):
                            vid = pl_item.get("contentDetails", {}).get("videoId", "")
                            title = pl_item.get("snippet", {}).get("title", "")
                            if vid and vid not in seen_ids:
                                seen_ids.add(vid)
                                shorts.append({"video_id": vid, "title": title, "source": "youtube_api_uploads"})

                        logger.info(f"📱 [Shorts Discovery] Found {len(shorts)} videos from YouTube Data API uploads playlist.")
            except Exception as e:
                logger.debug(f"YouTube Data API uploads query notice: {e}")

        return shorts

    def update_short_related_video_studio(self, short_video_id: str, stream_video_id: str) -> bool:
        """
        Calls YouTube Studio's authenticated InnerTube endpoint to set the official Related Video link.
        Requires valid SAPISID / studio session cookies.
        """
        sapisid = self.cookies.get("SAPISID") or self.cookies.get("__Secure-3PAPISID") or self.cookies.get("__Secure-1PAPISID")
        if not sapisid:
            logger.warning(
                f"⚠️ [Shorts Updater] Cannot update Related Video for Short '{short_video_id}': "
                "No 'SAPISID' cookie found. Please provide valid YouTube Studio cookies in YOUTUBE_STUDIO_COOKIES or youtube_cookies.txt."
            )
            return False

        ts, sapisid_hash = compute_sapisid_hash(sapisid, origin="https://studio.youtube.com")
        cookie_header = "; ".join(f"{k}={v}" for k, v in self.cookies.items())

        endpoints = [
            "https://studio.youtube.com/youtubei/v1/video_manager/metadata_update",
            "https://studio.youtube.com/youtubei/v1/creator/modify_creator_video",
        ]

        payload = {
            "context": {
                "client": {
                    "clientName": "WEB_CREATOR",
                    "clientVersion": "1.0",
                }
            },
            "encryptedVideoId": short_video_id,
            "flowType": "MDE_FLOW_TYPE_EDIT",
            "relatedVideoMetadata": {
                "videoId": stream_video_id,
            },
            "shortRelatedVideoId": stream_video_id,
        }

        json_bytes = json.dumps(payload).encode("utf-8")

        for endpoint in endpoints:
            try:
                req = urllib.request.Request(
                    endpoint,
                    data=json_bytes,
                    headers={
                        "Authorization": f"SAPISIDHASH {ts}_{sapisid_hash}",
                        "X-Origin": "https://studio.youtube.com",
                        "Origin": "https://studio.youtube.com",
                        "Referer": f"https://studio.youtube.com/video/{short_video_id}/edit",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Content-Type": "application/json",
                        "Cookie": cookie_header,
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    resp_data = resp.read().decode("utf-8", errors="ignore")
                    logger.info(f"✅ [Studio API] Successfully linked Short '{short_video_id}' -> Stream '{stream_video_id}' via {endpoint.split('/')[-1]}.")
                    return True
            except urllib.error.HTTPError as he:
                err_body = he.read().decode("utf-8", errors="ignore") if hasattr(he, "read") else str(he)
                logger.debug(f"Studio update attempt to '{endpoint}' returned HTTP {he.code}: {err_body[:200]}")
            except Exception as e:
                logger.debug(f"Studio update attempt to '{endpoint}' failed: {e}")

        return False

    def update_all_shorts(
        self,
        stream_video_id: str,
        force: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Orchestrates updating all channel Shorts to link to the target stream video ID.
        Skips already updated Shorts unless force=True.
        """
        clean_stream_id = stream_video_id.strip()
        if not clean_stream_id:
            logger.warning("⚠️ [Shorts Updater] No stream video ID provided. Skipping update.")
            return {"status": "skipped", "reason": "empty_stream_id", "updated": 0, "total": 0}

        shorts = self.discover_channel_shorts()
        if not shorts:
            logger.info("ℹ️ [Shorts Updater] No Shorts discovered on channel.")
            return {"status": "success", "updated": 0, "total": 0, "skipped": 0}

        updated_shorts_cache = self.cache.setdefault("updated_shorts", {})
        results: Dict[str, Any] = {
            "stream_id": clean_stream_id,
            "total_discovered": len(shorts),
            "updated": 0,
            "skipped": 0,
            "failed": 0,
            "details": [],
        }

        logger.info(
            f"🚀 [Shorts Updater] Starting update for {len(shorts)} Shorts to point to Live Stream '{clean_stream_id}' "
            f"(Strategy: {self.strategy}, Dry-Run: {dry_run}, Force: {force})..."
        )

        for s in shorts:
            vid = s["video_id"]
            title = s.get("title", vid)

            # Check cache for idempotency
            cached = updated_shorts_cache.get(vid)
            if not force and cached and cached.get("stream_id") == clean_stream_id and cached.get("status") == "success":
                logger.debug(f"⏩ [Shorts Updater] Short '{vid}' already points to current stream '{clean_stream_id}'. Skipping.")
                results["skipped"] += 1
                continue

            if dry_run:
                logger.info(f"🔍 [DRY-RUN] Would link Short '{vid}' ('{title}') -> Stream '{clean_stream_id}'")
                results["updated"] += 1
                results["details"].append({"video_id": vid, "title": title, "status": "dry_run"})
                continue

            success = False
            if self.strategy in ("studio_api", "both"):
                success = self.update_short_related_video_studio(vid, clean_stream_id)

            if success:
                results["updated"] += 1
                updated_shorts_cache[vid] = {
                    "stream_id": clean_stream_id,
                    "updated_at": time.time(),
                    "status": "success",
                    "strategy": self.strategy,
                }
                results["details"].append({"video_id": vid, "title": title, "status": "success"})
            else:
                results["failed"] += 1
                results["details"].append({"video_id": vid, "title": title, "status": "failed"})

            # Rate limit pacing between updates
            time.sleep(0.5)

        self.cache["last_stream_id"] = clean_stream_id
        self._save_cache()

        logger.info(
            f"🎉 [Shorts Updater Complete] Summary: {results['updated']} updated, "
            f"{results['skipped']} skipped (already current), {results['failed']} failed (Total: {len(shorts)})."
        )
        return results


async def run_startup_shorts_update(stream_video_id: str, cfg: Any) -> Dict[str, Any]:
    """
    Non-blocking async runner called at application startup when stream ID is resolved.
    Runs discovery and updates in threadpool executor.
    """
    if not getattr(cfg, "update_shorts_related_video", False):
        return {"status": "disabled"}

    if not stream_video_id:
        return {"status": "skipped", "reason": "empty_stream_id"}

    channel_handle = getattr(cfg, "youtube_channel_handle", "@MassiveGodComplex")
    channel_id = getattr(cfg, "youtube_channel_id", "")
    api_key = getattr(cfg, "youtube_api_key", "")
    raw_cookies = getattr(cfg, "youtube_studio_cookies", "")
    cookies_file = getattr(cfg, "youtube_cookies_file", "youtube_cookies.txt")
    strategy = getattr(cfg, "shorts_update_strategy", "studio_api")
    max_batch_size = getattr(cfg, "shorts_max_batch_size", 50)

    updater = ShortsRelatedVideoUpdater(
        channel_handle=channel_handle,
        channel_id=channel_id,
        api_key=api_key,
        raw_cookies=raw_cookies,
        cookies_file=cookies_file,
        strategy=strategy,
        max_batch_size=max_batch_size,
    )

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, updater.update_all_shorts, stream_video_id)


def main():
    parser = argparse.ArgumentParser(description="YouTube Shorts Related Video Link Updater Utility")
    parser.add_argument("--stream-id", "-s", type=str, default="", help="YouTube Live Stream Video ID to link as Related Video")
    parser.add_argument("--channel-handle", "-c", type=str, default="", help="YouTube Channel Handle (e.g. @MassiveGodComplex)")
    parser.add_argument("--cookies-file", "-f", type=str, default="youtube_cookies.txt", help="Path to YouTube Studio cookies file")
    parser.add_argument("--cookies", type=str, default="", help="Raw YouTube Studio cookie string")
    parser.add_argument("--strategy", choices=["studio_api", "description_link", "both"], default="studio_api", help="Update strategy")
    parser.add_argument("--dry-run", action="store_true", help="Simulate discovery and update without sending write requests")
    parser.add_argument("--force", action="store_true", help="Force update all Shorts even if already cached for current stream")
    parser.add_argument("--batch-size", type=int, default=50, help="Maximum number of Shorts to process")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    stream_id = args.stream_id.strip()
    if not stream_id:
        from dotenv import load_dotenv
        load_dotenv()
        from app import extract_youtube_video_id
        raw_stream = os.getenv("YOUTUBE_VIDEO_ID", "").strip() or os.getenv("YOUTUBE_CHANNEL_HANDLE", "").strip()
        stream_id = extract_youtube_video_id(raw_stream) if raw_stream else ""

    if not stream_id and not args.dry_run:
        print("❌ Error: No stream ID provided or resolvable from .env. Pass --stream-id <VIDEO_ID> or set YOUTUBE_VIDEO_ID in .env.")
        sys.exit(1)

    from dotenv import load_dotenv
    load_dotenv()
    handle = args.channel_handle or os.getenv("YOUTUBE_CHANNEL_HANDLE", "@MassiveGodComplex")
    api_key = os.getenv("YOUTUBE_API_KEY", "")
    raw_cookies = args.cookies or os.getenv("YOUTUBE_STUDIO_COOKIES", "")
    cookies_file = args.cookies_file or os.getenv("YOUTUBE_COOKIES_FILE", "youtube_cookies.txt")

    updater = ShortsRelatedVideoUpdater(
        channel_handle=handle,
        api_key=api_key,
        raw_cookies=raw_cookies,
        cookies_file=cookies_file,
        strategy=args.strategy,
        max_batch_size=args.batch_size,
    )

    print("=" * 65)
    print("YOUTUBE SHORTS RELATED VIDEO UPDATER")
    print(f"-> Target Live Stream ID: '{stream_id}'")
    print(f"-> Channel Handle:        '{handle}'")
    print(f"-> Cookies loaded:        {len(updater.cookies)} cookies (SAPISID: {'Present' if 'SAPISID' in updater.cookies else 'Missing'})")
    print(f"-> Dry Run:               {args.dry_run}")
    print("=" * 65)

    res = updater.update_all_shorts(stream_id, force=args.force, dry_run=args.dry_run)
    print("\nResult:", json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
