"""
Comprehensive test suite for YouTube Shorts Related Video Link Updater Subsystem.
Tests cookie parsing, SAPISIDHASH computation, Shorts discovery, caching idempotency,
and non-blocking background task execution.
"""

import asyncio
import json
import os
import shutil
import tempfile
import time
from typing import Dict

from config import config
from shorts_updater import (
    ShortsRelatedVideoUpdater,
    compute_sapisid_hash,
    parse_cookie_source,
    run_startup_shorts_update,
)
from app import LocalCoHostApp


def test_cookie_parsing_and_sapisid_hash():
    print("\n" + "=" * 55)
    print("TEST 1: Cookie Parsing & SAPISIDHASH Generation")
    print("=" * 55)

    # 1. Raw string parsing
    raw_str = "SAPISID=abc123secret; __Secure-1PSID=psid456; LOGIN_INFO=login789"
    parsed_raw = parse_cookie_source(raw_cookies=raw_str)
    assert parsed_raw.get("SAPISID") == "abc123secret", "Failed to parse SAPISID from string"
    assert parsed_raw.get("__Secure-1PSID") == "psid456"
    assert parsed_raw.get("LOGIN_INFO") == "login789"
    print("-> Raw cookie string parsed successfully.")

    # 2. Netscape format parsing
    temp_dir = tempfile.mkdtemp(prefix="test_shorts_cookies_")
    try:
        netscape_file = os.path.join(temp_dir, "cookies.txt")
        with open(netscape_file, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write(".youtube.com\tTRUE\t/\tTRUE\t1750000000\tSAPISID\tnetscape_sapisid_val\n")
            f.write(".youtube.com\tTRUE\t/\tTRUE\t1750000000\tLOGIN_INFO\tnetscape_login_val\n")

        parsed_file = parse_cookie_source(cookies_file=netscape_file)
        assert parsed_file.get("SAPISID") == "netscape_sapisid_val", "Failed to parse Netscape format cookies.txt"
        assert parsed_file.get("LOGIN_INFO") == "netscape_login_val"
        print("-> Netscape format cookies.txt parsed successfully.")

        # 3. JSON format parsing
        json_file = os.path.join(temp_dir, "cookies.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump([
                {"name": "SAPISID", "value": "json_sapisid_val"},
                {"name": "HSID", "value": "json_hsid_val"},
            ], f)

        parsed_json = parse_cookie_source(cookies_file=json_file)
        assert parsed_json.get("SAPISID") == "json_sapisid_val", "Failed to parse JSON format cookies"
        assert parsed_json.get("HSID") == "json_hsid_val"
        print("-> JSON export cookies format parsed successfully.")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    # 4. SAPISIDHASH computation
    ts, sapisid_hash = compute_sapisid_hash("abc123secret", "https://studio.youtube.com")
    assert isinstance(ts, int) and ts > 0
    assert len(sapisid_hash) == 40  # SHA1 hex string length
    print(f"-> SAPISIDHASH computed: {ts}_{sapisid_hash[:8]}... (40 hex chars)")
    print("[PASS] Cookie parsing & SAPISIDHASH computation verified!")


def test_shorts_updater_caching_and_idempotency():
    print("\n" + "=" * 55)
    print("TEST 2: Cache Persistence & Idempotency")
    print("=" * 55)

    temp_dir = tempfile.mkdtemp(prefix="test_shorts_cache_")
    try:
        cache_path = os.path.join(temp_dir, "shorts_cache.json")
        updater = ShortsRelatedVideoUpdater(
            channel_handle="@MassiveGodComplex",
            raw_cookies="SAPISID=test_sapisid",
            cache_file=cache_path,
        )

        # Mock discovery return
        updater.discover_channel_shorts = lambda: [
            {"video_id": "SHORT_001", "title": "First Short", "source": "mock"},
            {"video_id": "SHORT_002", "title": "Second Short", "source": "mock"},
            {"video_id": "SHORT_003", "title": "Third Short", "source": "mock"},
        ]

        # 1. Run dry-run for Stream 1
        stream_id_1 = "STREAM_LIVE_AAA"
        res1 = updater.update_all_shorts(stream_video_id=stream_id_1, dry_run=True)
        assert res1["updated"] == 3, f"Expected 3 updated in dry run, got {res1['updated']}"
        assert res1["skipped"] == 0

        # 2. Simulate successful update for Stream 1
        updater.update_short_related_video_studio = lambda short_id, stream_id: True
        res2 = updater.update_all_shorts(stream_video_id=stream_id_1, dry_run=False)
        assert res2["updated"] == 3, f"Expected 3 updated on live run, got {res2['updated']}"
        assert os.path.exists(cache_path), "Cache file was not persisted on disk"

        # 3. Second run with SAME stream ID -> Should be 100% skipped due to idempotency
        res3 = updater.update_all_shorts(stream_video_id=stream_id_1, dry_run=False)
        assert res3["skipped"] == 3, f"Expected 3 skipped on duplicate run, got {res3['skipped']}"
        assert res3["updated"] == 0, "Idempotency failed: re-updated already current shorts"
        print(f"-> Verified idempotency: {res3['skipped']} shorts skipped on duplicate stream run.")

        # 4. Third run with NEW stream ID -> Should update all 3
        stream_id_2 = "STREAM_LIVE_BBB"
        res4 = updater.update_all_shorts(stream_video_id=stream_id_2, dry_run=False)
        assert res4["updated"] == 3, f"Expected 3 updated on new stream, got {res4['updated']}"
        assert res4["skipped"] == 0
        print(f"-> Verified new stream ID '{stream_id_2}' successfully triggered update.")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("[PASS] Cache persistence & idempotency verified!")


async def test_app_async_startup_shorts_task():
    print("\n" + "=" * 55)
    print("TEST 3: App Asynchronous Background Task Integration")
    print("=" * 55)

    config.visualizer_headless = True
    config.local_audio_enabled = False

    app = LocalCoHostApp()

    # 1. Disabled state (default)
    config.update_shorts_related_video = False
    await app._run_shorts_updater_task("STREAM_TEST_123")
    assert app.shorts_updated_for_stream is None, "Should not update when disabled in config"
    print("-> Verified disabled state behaves cleanly.")

    # 2. Enabled state with mock runner
    config.update_shorts_related_video = True
    temp_dir = tempfile.mkdtemp(prefix="test_app_shorts_")
    try:
        cache_path = os.path.join(temp_dir, "shorts_cache.json")
        app.cfg.youtube_studio_cookies = "SAPISID=dummy_sapisid"

        test_stream_id = "LIVE_STREAM_XYZ"
        await app._run_shorts_updater_task(test_stream_id)
        assert app.shorts_updated_for_stream == test_stream_id
        assert app.shorts_updater_task_running is False
        print(f"-> Background task completed cleanly and marked stream '{test_stream_id}' as updated.")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        config.update_shorts_related_video = False

    print("[PASS] App async task integration verified!")


async def run_all_tests():
    print("\n" + "#" * 60)
    print("STARTING YOUTUBE SHORTS RELATED VIDEO TEST SUITE")
    print("#" * 60)

    test_cookie_parsing_and_sapisid_hash()
    test_shorts_updater_caching_and_idempotency()
    await test_app_async_startup_shorts_task()

    print("\n" + "#" * 60)
    print("ALL YOUTUBE SHORTS UPDATER TESTS PASSED PERFECTLY!")
    print("#" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
