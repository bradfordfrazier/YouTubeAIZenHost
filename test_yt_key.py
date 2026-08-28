import urllib.request
import urllib.error
import json
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from app import extract_youtube_video_id

api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
raw_video_input = os.getenv("YOUTUBE_VIDEO_ID", "").strip() or os.getenv("YOUTUBE_CHANNEL_HANDLE", "").strip()
video_id = extract_youtube_video_id(raw_video_input) if raw_video_input else ""

print("=" * 60)
print("YOUTUBE DATA API V3 VIEWER TELEMETRY VALIDATOR")
print("=" * 60)

if not api_key:
    print("\n[!] YOUTUBE_API_KEY is currently empty in .env!")
    print("Please open .env and paste your API key on line 19:")
    print("  YOUTUBE_API_KEY=AIzaSyYourActualKeyHere\n")
    print("To get a YouTube Data API v3 key:")
    print("  1. Go to Google Cloud Console: https://console.cloud.google.com/apis/credentials")
    print("  2. Ensure 'YouTube Data API v3' is enabled: https://console.cloud.google.com/apis/library/youtube.googleapis.com")
    print("  3. Create or copy an API key and paste it into .env under YOUTUBE_API_KEY=")
    sys.exit(1)

if not video_id:
    print(f"\n[!] Could not resolve a video ID from: '{raw_video_input}'")
    print("Please set YOUTUBE_VIDEO_ID in .env with a live video ID or URL.")
    sys.exit(0)

print(f"-> Target Video Input: {raw_video_input}")
print(f"-> Resolved Video ID:  {video_id}")
print(f"-> Testing with API Key: {api_key[:8]}...{api_key[-4:] if len(api_key) > 8 else ''}")

url = f"https://www.googleapis.com/youtube/v3/videos?part=liveStreamingDetails,snippet,status&id={video_id}&key={api_key}"
req = urllib.request.Request(
    url,
    headers={
        "User-Agent": "YouTubeAIHost/1.0",
        "Accept": "application/json"
    }
)

try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        items = data.get("items", [])
        if not items:
            print(f"\n[?] No video found with ID '{video_id}'. Is the stream live or scheduled?")
            sys.exit(0)

        item = items[0]
        title = item.get("snippet", {}).get("title", "Unknown Title")
        live_details = item.get("liveStreamingDetails", {})
        concurrent_str = live_details.get("concurrentViewers")

        print(f"\n[OK] Connected to YouTube Data API v3!")
        print(f"-> Stream Title: {title}")
        print(f"-> liveStreamingDetails fields: {list(live_details.keys())}")

        if concurrent_str is not None:
            viewers = int(concurrent_str)
            print(f"\n[VIEWERS DETECTED]: {viewers}")
            print(f"-> Engagement Mode: ACTIVE ('LIVE ON AIR - {viewers} VIEWERS')")
        else:
            print(f"\n[NO CONCURRENT VIEWERS (concurrentViewers field omitted by Google)]")
            print(f"-> Viewers: 0")
            print(f"-> Engagement Mode: ECO ('ECO MODE (IDLE)')")

except urllib.error.HTTPError as e:
    err_body = e.read().decode("utf-8", errors="ignore")
    print(f"\n[HTTP ERROR {e.code}]: {e.reason}")
    print(err_body)
    if "API_KEY_INVALID" in err_body:
        print("\nTip: The API key is invalid or not recognized by Google.")
    elif "accessNotConfigured" in err_body or "SERVICE_DISABLED" in err_body:
        print("\nTip: Enable 'YouTube Data API v3' in Google Cloud Console for this project:")
        print("   https://console.cloud.google.com/apis/library/youtube.googleapis.com")
except Exception as e:
    print(f"\n[CONNECTION ERROR]: {e}")
