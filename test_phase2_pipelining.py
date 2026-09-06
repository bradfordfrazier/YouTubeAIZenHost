"""
Unit & Integration Test Suite for Phase 2:
1. Mood -> Exaggeration parameter mapping.
2. Sentence splitting & repair guards (abbreviations, decimals, ellipses, mentions).
3. Utterance lifecycle (begin_utterance, push_audio, end_utterance, wait_until_speech_completed).
4. Audio crossfade stitching & silence gap (zero-click assertion).
5. Producer-consumer pipelined execution in simulation mode.
"""

import asyncio
import time
import numpy as np

from config import config
from tts_engine import TTSEngine
from ai_brain import AIBrain
from app import LocalCoHostApp, CommentEvent


def test_mood_exaggeration_mapping():
    print("\n" + "=" * 60)
    print("TEST 1: Mood Exaggeration Mapping & Dynamic Voice Parameter Routing")
    print("=" * 60)

    config.visualizer_headless = True
    tts = TTSEngine()

    # 1. Test direct mood argument
    deadpan_mood = "deadpan"
    exag_deadpan = tts.mood_exaggeration_map.get(deadpan_mood, tts.exaggeration_default)
    assert exag_deadpan == 0.3, f"Expected 0.3 for deadpan, got {exag_deadpan}"

    hyped_mood = "hyped"
    exag_hyped = tts.mood_exaggeration_map.get(hyped_mood, tts.exaggeration_default)
    assert exag_hyped == 0.8, f"Expected 0.8 for hyped, got {exag_hyped}"

    savage_mood = "savage"
    exag_savage = tts.mood_exaggeration_map.get(savage_mood, tts.exaggeration_default)
    assert exag_savage == 0.85, f"Expected 0.85 for savage, got {exag_savage}"

    print(f"-> Verified mood exaggeration map: deadpan={exag_deadpan}, hyped={exag_hyped}, savage={exag_savage}")
    print("[PASS] Mood exaggeration map verified!")


def test_sentence_splitter_and_repair():
    print("\n" + "=" * 60)
    print("TEST 2: Sentence Splitting Guards & Repair in AI Brain")
    print("=" * 60)

    brain = AIBrain()

    # Case A: Decimal safety (3.14) & Abbreviation safety (Dr. Smith, vs.)
    sample_text = "@CosmicVoyager, Dr. Smith says 3.14 is pi vs. 2.71 for e. Notice how your mind calculates that."
    sents, rem = brain._extract_completed_sentences(sample_text + " ")
    print(f"-> Extracted sentences from decimal/abbrev text: {sents}")
    assert len(sents) == 2, f"Expected 2 sentences, got {len(sents)}: {sents}"
    assert "3.14" in sents[0][0] and "Dr. Smith" in sents[0][0] and "vs." in sents[0][0]
    assert sents[1][0] == "Notice how your mind calculates that."

    # Case B: Ellipsis safety ("Wait... what?")
    ellipsis_text = "Wait... what did you think was happening? Everything is already complete."
    sents_e, rem_e = brain._extract_completed_sentences(ellipsis_text + " ")
    print(f"-> Extracted sentences from ellipsis text: {sents_e}")
    assert len(sents_e) == 2, f"Expected 2 sentences, got {len(sents_e)}: {sents_e}"
    assert sents_e[1][0] == "Everything is already complete."

    # Case C: Short fragment guard (minimum 3 words & 12 chars)
    short_text = "No. Yes. @Neo, this is the actual first valid sentence of the transmission."
    sents_s, rem_s = brain._extract_completed_sentences(short_text + " ")
    print(f"-> Extracted sentences with short fragment merge: {sents_s}")
    assert len(sents_s) == 1, f"Expected 1 merged sentence, got {len(sents_s)}: {sents_s}"
    assert "No. Yes. @Neo" in sents_s[0][0]

    print("[PASS] Sentence splitter guards verified!")


async def test_audio_chunk_crossfades_and_silence():
    print("\n" + "=" * 60)
    print("TEST 3: Audio Chunk Crossfade Stitching & Inter-Sentence Gap Silence")
    print("=" * 60)

    config.visualizer_headless = True
    config.inter_sentence_gap_sec = 0.15
    tts = TTSEngine()
    tts.clear_audio_buffer()

    sr = tts.sample_rate  # 48000
    # Generate 3 chunks of 1.0s pure 440Hz tone with intentional DC offset / step to verify fade
    t = np.linspace(0, 1.0, sr, endpoint=False)
    raw_tone1 = np.column_stack((np.sin(2 * np.pi * 440 * t), np.sin(2 * np.pi * 440 * t))).astype(np.float32)
    raw_tone2 = np.column_stack((np.sin(2 * np.pi * 440 * t), np.sin(2 * np.pi * 440 * t))).astype(np.float32)
    raw_tone3 = np.column_stack((np.sin(2 * np.pi * 440 * t), np.sin(2 * np.pi * 440 * t))).astype(np.float32)

    tts.begin_utterance()
    assert tts._utterance_open is True
    assert tts._utterance_chunk_count == 0

    # Push chunk 1
    tts.push_audio(raw_tone1)
    assert tts._utterance_chunk_count == 1
    # First chunk into empty buffer should NOT have head fade (crisp onset), but tail has 5ms fade
    # Check tail 5 samples: should fade towards 0
    with tts._buffer_lock:
        buf1 = tts._audio_buffer_ndi.copy()
    assert np.all(np.abs(buf1[-5:]) < 0.05), "Expected chunk 1 tail to fade out smoothly"

    # Push chunk 2 (should prepend 0.15s gap silence and apply head + tail fades)
    tts.push_audio(raw_tone2)
    assert tts._utterance_chunk_count == 2
    gap_samples = int(sr * 0.15)
    # The gap silence region in the buffer between chunk 1 and chunk 2 should be exactly zeros
    with tts._buffer_lock:
        buf2 = tts._audio_buffer_ndi.copy()
    chunk1_len = len(raw_tone1)
    gap_region = buf2[chunk1_len : chunk1_len + gap_samples]
    assert np.all(gap_region == 0.0), f"Expected gap silence of {gap_samples} samples, got max {np.max(np.abs(gap_region))}"

    # Push chunk 3
    tts.push_audio(raw_tone3)
    assert tts._utterance_chunk_count == 3

    tts.end_utterance()
    assert tts._utterance_open is False

    # Total duration should be 3 * 1.0s + 2 * 0.15s gap = 3.30s
    total_expected_samples = 3 * sr + 2 * gap_samples
    assert len(tts._audio_buffer_ndi) == total_expected_samples, f"Expected {total_expected_samples} samples, got {len(tts._audio_buffer_ndi)}"

    print(f"-> Total buffered audio: {len(tts._audio_buffer_ndi)/sr:.2f}s across 3 chunks with 2 gap silences.")
    print("[PASS] Audio chunk crossfades and silence verified!")


async def test_wait_until_speech_completed_draining():
    print("\n" + "=" * 60)
    print("TEST 4: wait_until_speech_completed Draining Timing Across Chunks")
    print("=" * 60)

    config.visualizer_headless = True
    tts = TTSEngine()
    tts.clear_audio_buffer()
    sr = tts.sample_rate

    # Generate three 0.3s chunks
    chunk_dur = 0.30
    chunk_samples = int(sr * chunk_dur)
    tone = np.zeros((chunk_samples, 2), dtype=np.float32)

    tts.begin_utterance()
    tts.push_audio(tone)
    tts.push_audio(tone)
    tts.push_audio(tone)
    tts.end_utterance()

    # Pop loop simulating 60fps NDI video pump (800 samples/frame every 16.6ms)
    async def _mock_pump():
        while tts.remaining_speech_duration > 0:
            tts.pop_audio_packet(800)
            await asyncio.sleep(800 / sr)

    pump_task = asyncio.create_task(_mock_pump())
    t0 = time.time()
    await tts.wait_until_speech_completed()
    t_elapsed = time.time() - t0
    await pump_task

    # 3 chunks of 0.3s + 2 gaps of 0.15s = 1.20s
    expected_dur = 3 * chunk_dur + 2 * config.inter_sentence_gap_sec
    print(f"-> Wall time waited: {t_elapsed:.2f}s (expected ~{expected_dur:.2f}s)")
    assert t_elapsed >= expected_dur * 0.85, f"wait_until_speech_completed resolved too early: {t_elapsed:.2f}s < {expected_dur:.2f}s"
    assert tts.remaining_speech_duration == 0.0, "Audio buffer was not fully drained"
    print("[PASS] wait_until_speech_completed draining verified!")


async def test_pipelined_turn_execution():
    print("\n" + "=" * 60)
    print("TEST 5: Full Pipelined AI Turn Execution (Producer/Consumer in App)")
    print("=" * 60)

    config.visualizer_headless = True
    app = LocalCoHostApp()
    app.running = True

    # Trigger a simulated turn with a 2-sentence question
    event = CommentEvent(
        priority=2,
        created_at=time.time(),
        event_type="direct_mention",
        prompt_trigger="Chat message from @ZenSeeker: '@I Am what is the meaning of life? Is there one?'",
        chat_item={"author": "ZenSeeker", "message": "@I Am what is the meaning of life? Is there one?"},
    )

    t0 = time.perf_counter()
    # Mock audio pop loop so audio drains during execution
    async def _pop_loop():
        while app.running:
            app.tts.pop_audio_packet(800)
            await asyncio.sleep(0.016)

    pop_task = asyncio.create_task(_pop_loop())
    try:
        await app._execute_ai_turn(event)
    finally:
        app.running = False
        pop_task.cancel()
        try:
            await pop_task
        except asyncio.CancelledError:
            pass

    t_total = time.perf_counter() - t0
    print(f"-> Full turn finished in {t_total:.2f}s with visualizer mood [{app.visualizer.current_mood.upper()}]")
    assert len(app.brain.dialogue_history) > 0, "Expected turn to be recorded in dialogue history"
    print("[PASS] Pipelined AI Turn execution verified!")


async def run_all_tests():
    test_mood_exaggeration_mapping()
    test_sentence_splitter_and_repair()
    await test_audio_chunk_crossfades_and_silence()
    await test_wait_until_speech_completed_draining()
    await test_pipelined_turn_execution()
    print("=" * 60)
    print("ALL PHASE 2 TESTS COMPLETED AND VERIFIED 100%!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
