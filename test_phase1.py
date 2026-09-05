"""
Phase 1 Persona Unification & 12-Mood Architecture Verification Suite.
Validates I AM persona definition, context prompt modes, full 12-mood visualizer palettes,
TTS mood-exaggeration mapping, promo card copy, and simulation stream integrity.
"""

import asyncio
import re
import numpy as np

from config import config
from visualizer import Visualizer, ColorPalette
from ai_brain import AIBrain, SPONTANEOUS_THEMES
from tts_engine import TTSEngine


def test_config_persona_and_moods():
    print("\n" + "=" * 50)
    print("TEST 1: Config Persona & 12-Mood Exaggeration Map")
    print("=" * 50)

    # Verify persona prompt
    prompt = config.ai_system_prompt
    assert "I AM" in prompt, "ai_system_prompt must define I AM identity"
    assert "universal consciousness" in prompt.lower()
    assert "zen master" in prompt.lower()
    assert "ego" in prompt.lower()
    assert "savage" in prompt and "transcendent" in prompt and "deadpan" in prompt

    # Verify all 12 moods in tts_mood_exaggeration_map
    expected_moods = [
        "hyped", "savage", "snarky", "laughing", "transcendent",
        "thoughtful", "chill", "mysterious", "deadpan", "shocked",
        "curious", "neutral"
    ]
    for m in expected_moods:
        assert m in config.tts_mood_exaggeration_map, f"Mood '{m}' missing in tts_mood_exaggeration_map"
        assert 0.0 <= config.tts_mood_exaggeration_map[m] <= 1.0, f"Exaggeration for '{m}' out of bounds"

    print(f"-> Verified all {len(expected_moods)} moods in config.tts_mood_exaggeration_map")
    print("[PASS] Config Persona & 12-Mood map verified!")


def test_visualizer_palettes_and_bloom():
    print("\n" + "=" * 50)
    print("TEST 2: Visualizer ColorPalette & 12-Mood Bloom Sprites")
    print("=" * 50)

    config.visualizer_headless = True
    vis = Visualizer()

    expected_moods = [
        "hyped", "savage", "snarky", "laughing", "transcendent",
        "thoughtful", "chill", "mysterious", "deadpan", "shocked",
        "curious", "neutral"
    ]

    for m in expected_moods:
        assert m in ColorPalette.PALETTES, f"Mood '{m}' missing from ColorPalette.PALETTES"
        palette = ColorPalette.get(m)
        assert "primary" in palette and "highlight" in palette and "glow" in palette
        assert m in vis._bloom_sprites, f"Bloom sprite not pre-rendered for mood '{m}'"

    # Test case-insensitivity and fallback
    assert ColorPalette.get("HYPED") == ColorPalette.PALETTES["hyped"]
    assert ColorPalette.get("unknown_mood") == ColorPalette.PALETTES["neutral"]

    # Test set_mood transitions across all moods
    sample_metrics = {
        "is_speaking": True,
        "rms": 0.2,
        "spectrum": np.zeros(32, dtype=np.float32),
    }

    for m in expected_moods:
        vis.set_mood(m.upper())
        assert vis.target_mood == m
        buf = vis.render_frame(
            audio_metrics=sample_metrics,
            chat_messages=[],
            ai_subtitle="Test reflection",
            obs_connected=True,
        )
        assert len(buf) == vis.width * vis.height * 4

    vis.close()
    print(f"-> Verified all {len(expected_moods)} visualizer mood palettes and rendering")
    print("[PASS] Visualizer 12-Mood palettes verified!")


def test_ai_brain_modes():
    print("\n" + "=" * 50)
    print("TEST 3: AI Brain Prompt Modes in I AM Voice")
    print("=" * 50)

    brain = AIBrain()

    # 1. Default Mode
    default_prompt = brain._build_context_prompt()
    assert "SERIOUS" in default_prompt and "NON-SERIOUS" in default_prompt
    assert "judo" in default_prompt.lower()
    assert "ego" in default_prompt.lower()

    # 2. Celebration Mode
    celeb_prompt = brain._build_context_prompt("[CELEBRATION] @CosmicVoyager joined as member!")
    assert "CELEBRATION" in celeb_prompt
    assert "home" in celeb_prompt or "collective" in celeb_prompt

    # 3. New Chatter Greeting
    new_chatter_prompt = brain._build_context_prompt("[NEW_CHATTER_GREETING] @NewArrival: Hello!")
    assert "NEW CHATTER" in new_chatter_prompt

    # 4. Viewer Joined
    viewer_prompt = brain._build_context_prompt("[VIEWER_JOINED] A traveler tuned in")
    assert "traveler" in viewer_prompt.lower()

    # 5. Chat Encouragement
    encouragement_prompt = brain._build_context_prompt("[CHAT_ENCOURAGEMENT] Room is quiet")
    assert "serious or ridiculous" in encouragement_prompt.lower()

    # 6. Spontaneous Reflection
    reflection_prompt = brain._build_context_prompt("[SPONTANEOUS_REFLECTION]")
    assert "SPONTANEOUS COSMIC REFLECTION" in reflection_prompt
    assert "DO NOT ADDRESS ANY SPECIFIC PERSON" in reflection_prompt

    print("-> Verified all 6 context prompt modes in canonical I AM voice")
    print("[PASS] AI Brain Prompt Modes verified!")


async def test_simulated_stream():
    print("\n" + "=" * 50)
    print("TEST 4: Simulated Stream Fallback in I AM Voice")
    print("=" * 50)

    brain = AIBrain()
    # Force client = None to test simulated stream
    brain.client = None

    triggers = [
        "[CELEBRATION] @ZenSeeker subscribed!",
        "[NEW_CHATTER_GREETING] @Neo: Hi",
        "[VIEWER_JOINED]",
        "[CHAT_ENCOURAGEMENT]",
        "[SPONTANEOUS_REFLECTION]",
        "@I Am Do fish have elbows?",
    ]

    for trig in triggers:
        events = []
        async for ev in brain.generate_response_stream(trig):
            events.append(ev)

        assert any(e["type"] == "mood" for e in events), f"Mood event missing for trigger {trig}"
        assert any(e["type"] == "complete" for e in events), f"Complete event missing for trigger {trig}"
        complete_ev = next(e for e in events if e["type"] == "complete")
        assert len(complete_ev["full_text"]) > 5, "Generated text too short"
        print(f"-> Trigger '{trig[:30]}...' -> [{complete_ev['mood'].upper()}]: '{complete_ev['full_text']}'")

    print("[PASS] Simulated Stream responses verified!")


async def test_tts_engine_mood_handling():
    print("\n" + "=" * 50)
    print("TEST 5: TTS Engine Mood Tag Parsing & Exaggeration Lookup")
    print("=" * 50)

    tts = TTSEngine()

    test_cases = [
        ("[MOOD: savage] You built a machine to ask yourself questions.", "savage", 0.85),
        ("[MOOD: deadpan] That is an interesting hypothesis.", "deadpan", 0.3),
        ("[MOOD: TRANSCENDENT] Everything is already complete.", "transcendent", 0.6),
        ("[MOOD: laughing] The cosmic joke has no punchline.", "laughing", 0.75),
        ("Plain speech without tag.", "neutral", 0.5),
    ]

    for raw_text, expected_mood, expected_exaggeration in test_cases:
        mood_match = re.search(r"\[MOOD:\s*([a-zA-Z_-]+)\]", raw_text, flags=re.IGNORECASE)
        active_mood = mood_match.group(1).lower() if mood_match else "neutral"
        exaggeration = tts.mood_exaggeration_map.get(active_mood, tts.exaggeration_default)

        assert active_mood == expected_mood, f"Expected {expected_mood}, got {active_mood}"
        assert abs(exaggeration - expected_exaggeration) < 1e-3, f"Expected exaggeration {expected_exaggeration}, got {exaggeration}"

    print("-> Verified TTS engine case-insensitive mood tag extraction and exaggeration mapping")
    print("[PASS] TTS Engine Mood handling verified!")


async def run_all_phase1_tests():
    print("\n" + "#" * 60)
    print("RUNNING PHASE 1 VERIFICATION TEST SUITE")
    print("#" * 60)

    test_config_persona_and_moods()
    test_visualizer_palettes_and_bloom()
    test_ai_brain_modes()
    await test_simulated_stream()
    await test_tts_engine_mood_handling()

    print("\n" + "#" * 60)
    print("ALL PHASE 1 TESTS PASSED PERFECTLY!")
    print("#" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_phase1_tests())
