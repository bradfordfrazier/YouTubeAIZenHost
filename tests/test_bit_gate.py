"""
Tests for the bit gate and for the four prompt/pipeline bugs found alongside it.

Each `test_regression_*` exists because the behaviour it guards was broken on the live show and
every other test passed (see PROJECT_MASTER §11: "add the test that would have caught it").
No network: the provider is replaced with a scripted delta stream.
"""
from pathlib import Path
import asyncio
import json
import sys
import types

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bit_gate
from ai_brain import AIBrain
from config import config


# ----------------------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------------------
@pytest.fixture()
def brain(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "bit_gate_log_path", str(tmp_path / "gate.jsonl"))
    monkeypatch.setattr(config, "bit_gate_enabled", True)
    monkeypatch.setattr(config, "bit_editor_enabled", True)
    monkeypatch.setattr(config, "bit_candidates", 3)
    monkeypatch.setattr(config, "bit_gate_max_attempts", 2)
    monkeypatch.setattr(config, "bit_gate_fail_open_after", 3)
    monkeypatch.setattr(config, "bit_words_min", 10)
    monkeypatch.setattr(config, "bit_words_max", 25)
    monkeypatch.setattr(config, "one_liner_ratio", 0.0)   # keep forms multi-sentence unless a test says otherwise
    monkeypatch.setattr(config, "reflection_cache_enabled", False)
    b = AIBrain()
    b.client = object()            # "a client exists"; the scripted stream below is what gets called
    b.provider = "gemini"
    b.favorites = []
    b.dialogue_history.clear()
    b.recent_qa_threads.clear()
    b.chat_buffer.clear()
    return b


def script(brain, replies):
    """Replaces the provider. `replies` are returned in order, one per model call; an Exception is raised."""
    calls = []

    def _delta_stream(self, target_model, full_context, is_deep, is_bit, system_override=None, temperature_override=None):
        calls.append({"prompt": full_context, "system": system_override, "temp": temperature_override, "is_bit": is_bit})
        reply = replies.pop(0)

        async def gen():
            if isinstance(reply, Exception):
                raise reply
            for i in range(0, len(reply), 7):     # small pieces, like a real stream
                yield reply[i:i + 7]
        return gen()

    brain._delta_stream = types.MethodType(_delta_stream, brain)
    return calls


def run(brain, trigger="[SPONTANEOUS_REFLECTION]", **kw):
    async def go():
        return [ev async for ev in brain.generate_response_stream(trigger, **kw)]
    return asyncio.run(go())


@pytest.fixture(autouse=True)
def operator_word_budget(monkeypatch):
    """The operator's .env values (PROJECT_MASTER §9); config.py's own defaults are 65-85."""
    monkeypatch.setattr(config, "bit_words_min", 10)
    monkeypatch.setattr(config, "bit_words_max", 25)
    monkeypatch.setattr(config, "one_liner_words_max", 25)


def lint(text, form="observation", theme="A lost sock — Where does the missing half of a pair go?", recent=(), favs=()):
    return bit_gate.lint_bit(text, form=form, theme=theme, recent=list(recent), favorites=list(favs), cfg=config)


GOOD_A = "[MOOD: deadpan] I invented gravity to keep things organised. [BEAT] Then I invented toddlers near staircases."
GOOD_B = "[MOOD: snarky] I spent four billion years perfecting the human knee. It lasts forty, and I bill myself for the replacement."
WE_BIT = "[MOOD: chill] We all carry a junk drawer somewhere inside. Mine holds eleven dead batteries and one allen wrench."


# ----------------------------------------------------------------------------------------------
# lint
# ----------------------------------------------------------------------------------------------
def test_lint_passes_a_clean_bit():
    assert lint("I invented gravity to keep things organised. Then I invented toddlers near staircases.") == []


@pytest.mark.parametrize("text,reason", [
    ("We all keep a junk drawer for the person I planned to become, next to the allen wrench.", "we_voice"),
    ("Let's be honest, I bought the chair for a man who never showed up to sit in it.", "we_voice"),
    ("As I said, the sock was never half of anything, it was just a sock in a dryer.", "handle_or_callback"),
    ("@Dave keeps a drawer of cables for devices that died before his last three phones did.", "handle_or_callback"),
    ("I built the eye and left a hole in the middle of it. Who signs off on that?", "ends_on_question"),
    ("I lost a sock in the dryer and I finally understood the nature of impermanence.", "abstract_landing"),
    ("I delve into the junk drawer every morning and come back with a single dead battery.", "banned_phrase"),
    ("Ah, the junk drawer, where I keep nine keys that fit no lock I have ever owned.", "banned_phrase"),
])
def test_lint_catches_declared_rules(text, reason):
    assert reason in lint(text)


def test_lint_allows_we_inside_story_dialogue():
    text = 'A roofer told the storm, "We are closed." The storm, being me as well, came in through the gutter.'
    assert "we_voice" not in lint(text, form="story")


def test_lint_abstract_noun_is_fine_when_it_is_not_the_landing():
    text = "I asked reality for a refund after the third flat tyre. It offered me store credit and a fourth tyre."
    assert "abstract_landing" not in lint(text)


def test_lint_rejects_a_reworded_theme_card():
    theme = "A cat sleeping in a sunbeam — Enlightenment with zero paperwork."
    assert "theme_parrot" in lint("My cat reached enlightenment in a sunbeam today, with zero paperwork filed.", theme=theme)
    assert "theme_parrot" not in lint("My cat found the one warm square on the floor. I have been paying rent on it for nine years.", theme=theme)


def test_lint_rejects_near_duplicates_and_repeated_openers():
    aired = ["I invented gravity to keep things organised. Then I invented toddlers near staircases."]
    assert "near_duplicate" in lint("I invented gravity to keep things tidy. Then I invented toddlers next to staircases.", recent=aired)
    assert "repeated_opener" in lint("I invented gravity after the third dropped plate and I have not apologised to the floor.", recent=aired)


def test_lint_one_liner_is_one_sentence_and_capped(monkeypatch):
    monkeypatch.setattr(config, "one_liner_words_max", 25)
    assert "one_liner_multi_sentence" in lint("I bought a ladder. It has been looking down on me ever since then.", form="one_liner")
    assert "too_long" in lint(" ".join(["word"] * 30) + ".", form="one_liner")
    assert lint("I wrote FRAGILE on the box, and it has been acting like it ever since.", form="one_liner") == []


# ----------------------------------------------------------------------------------------------
# parsing
# ----------------------------------------------------------------------------------------------
def test_parse_candidates_tolerates_formats():
    raw = "1. [MOOD: deadpan] First one here.\n2) **[MOOD: snarky]** Second one\n   wrapped onto a line.\n\n**3.** \"Third one here.\""
    out = bit_gate.parse_candidates(raw, expected=3)
    assert len(out) == 3 and out[1].endswith("wrapped onto a line.") and out[2] == "Third one here."
    assert bit_gate.parse_candidates("[MOOD: deadpan] Just one bit, unnumbered.") == ["[MOOD: deadpan] Just one bit, unnumbered."]


def test_parse_editor_reply():
    assert bit_gate.parse_editor_reply('```json\n{"scores": [], "pick": 2, "why": "lands"}\n```', 3)[0] == 2
    assert bit_gate.parse_editor_reply('{"pick": 0, "why": "all 2s"}', 3)[0] == 0
    assert bit_gate.parse_editor_reply('{"pick": 9}', 3)[0] is None        # out of range
    assert bit_gate.parse_editor_reply("I liked the second one", 3)[0] is None


def test_editor_never_sees_the_theme_or_form():
    p = bit_gate.build_editor_prompt(["one", "two"], ["aired"], 3)
    assert "ANCHOR" not in p and "DIRECTION" not in p and "FORM:" not in p and "laugh >= 3" in p


# ----------------------------------------------------------------------------------------------
# regressions in the prompt builder
# ----------------------------------------------------------------------------------------------
def test_regression_bits_keep_their_anti_repetition_window_after_a_turn_airs(brain):
    """record_completed_turn() fills recent_qa_threads for EVERY turn, which used to shadow the
    anti-repetition branch for bits from the first turn of the session onward."""
    for i in range(12):
        brain.dialogue_history.append({"text": f"Aired bit {i} about a lighthouse keeper.", "mood": "deadpan", "timestamp": 0})
    brain.add_chat_message("Bob", "is cereal soup?")
    brain.record_completed_turn("Viewer @Bob: 'is cereal soup?'", "@Bob, only if you are brave.", "snarky", "Bob")
    p = brain._build_context_prompt("[SPONTANEOUS_REFLECTION]")
    assert "Your Recent Remarks" in p and "Aired bit 3 about" in p
    assert "natural callbacks" not in p          # §2.5: bits may not call back
    assert "@Bob" not in p and "is cereal soup" not in p and "Recent YouTube Live Chat" not in p


def test_regression_chat_replies_still_get_the_room(brain):
    brain.add_chat_message("Bob", "is cereal soup?")
    brain.record_completed_turn("Viewer @Bob: 'hi'", "@Bob, welcome back to yourself.", "chill", "Bob")
    p = brain._build_context_prompt("Viewer @Bob: 'is cereal soup?'")
    assert "Viewer @Bob: is cereal soup?" in p and "Recent Q&A Conversational Thread" in p and "ROOM FACTS" in p


def test_memory_window_counts_distinct_lines(brain):
    for i in range(5):
        for _ in range(2):   # generated into the cache, then aired: two entries per bit
            brain.dialogue_history.append({"text": f"line {i}", "timestamp": 0})
    assert brain._recent_lines(4) == ["line 1", "line 2", "line 3", "line 4"]


def test_regression_chat_replies_are_not_bit_exemplars(brain):
    brain.favorites = [
        {"text": "@Dave, the ticket was closed as working as intended.", "form": "reply", "kind": "reply"},
        {"text": "I built the knee to last forty years and the warranty to last thirty-nine.", "form": "observation", "kind": "bit"},
        {"text": "I keep a spare key for a house I do not own.", "form": "one_liner"},          # bit_lab winner: no 'kind'
    ]
    got = {f["text"] for _ in range(20) for f in brain.sample_favorites(5, form="story")}
    assert len(got) == 2 and not any(t.startswith("@") for t in got)
    assert brain.sample_favorites(5, form=None)            # un-filtered callers unchanged


def test_theme_card_is_split_into_anchor_and_direction(brain, monkeypatch):
    monkeypatch.setattr(config, "bit_theme_mode", "anchor_hint")
    p = brain._build_context_prompt("[SPONTANEOUS_REFLECTION]")
    anchor, angle = bit_gate.split_theme(brain.last_spontaneous_theme)
    assert f"must be in the bit: {anchor}" in p and "A compass, not a script" in p and "THEME: '" not in p
    monkeypatch.setattr(config, "bit_theme_mode", "full")
    assert "THEME: '" in brain._build_context_prompt("[SPONTANEOUS_REFLECTION]")


def test_observation_form_no_longer_fights_the_theme(brain):
    for _ in range(12):
        p = brain._build_context_prompt("[SPONTANEOUS_REFLECTION]")
        if brain.last_bit_form == "observation":
            assert "Notice something about the ANCHOR" in p and "three steps" not in p   # 25 words cannot hold three steps
            return
    pytest.fail("observation form never drawn")


def test_writer_mode_asks_for_numbered_candidates(brain):
    p = brain._build_context_prompt("[SPONTANEOUS_REFLECTION]", bit_candidates=4, bit_retry_note="Say 'I'.")
    assert "exactly 4 finished candidates" in p and "EDITOR'S NOTE ON THE LAST ROUND: Say 'I'." in p
    assert "Output only the survivor" not in p
    assert "Output only the survivor" in brain._build_context_prompt("[SPONTANEOUS_REFLECTION]")


def test_regression_cast_roast_angle_reaches_the_prompt(brain):
    from cast_engine import CastEngine
    persona = next(iter(CastEngine().personas.values()))
    trig = f"Cast member @{persona.handle} ({persona.archetype_title}) asks: '{persona.questions[0]}'"
    p = brain._build_context_prompt(trig)
    assert persona.roast_angle in p and f"Tone of the exchange: {persona.tone}" in p


# ----------------------------------------------------------------------------------------------
# regression: short closers were never spoken
# ----------------------------------------------------------------------------------------------
def test_regression_short_closer_is_spoken_from_cache(brain):
    sents = brain._sentences_for_playback("I filed a complaint with management about the weather. [BEAT] I'm management.", "deadpan")
    assert [t for t, _, _ in sents] == ["I filed a complaint with management about the weather.", "I'm management."]
    assert sents[-1][1] is True                    # and it keeps its beat


def test_regression_short_closer_is_spoken_live(brain, monkeypatch):
    monkeypatch.setattr(config, "bit_gate_enabled", False)
    script(brain, ["[MOOD: deadpan] @Bob, you asked the universe for a sign. [BEAT] [MOOD: savage] It buffered."])
    evs = run(brain, "Viewer @Bob: 'give me a sign'")
    spoken = [(e["text"], e["beat_before"], e["mood"]) for e in evs if e["type"] == "sentence"]
    assert spoken[-1] == ("It buffered.", True, "savage")


def test_mid_stream_fragments_still_merge_forward(brain):
    sents = brain._sentences_for_playback("It stopped. Now I am wide awake and listening to the fridge.", "deadpan")
    assert len(sents) == 1                           # "It stopped." rides with the sentence after it, as before


# ----------------------------------------------------------------------------------------------
# the gate, end to end
# ----------------------------------------------------------------------------------------------
def test_gate_airs_the_editors_pick_and_keeps_the_event_contract(brain):
    calls = script(brain, [f"1. {WE_BIT}\n2. {GOOD_A}\n3. {GOOD_B}", '{"scores": [], "pick": 1, "why": "staircase lands"}'])
    evs = run(brain, bypass_cache=True)
    assert [e["type"] for e in evs] == ["mood", "sentence", "sentence", "token", "complete"]
    done = evs[-1]
    assert done["full_text"].startswith("I invented gravity") and "[BEAT]" in done["raw_text"] and "[" not in done["full_text"]
    assert evs[2]["beat_before"] is True and done["mood"] == "deadpan"
    # the 'we' candidate was removed BEFORE the editor saw anything, so pick 1 is GOOD_A
    assert "We all carry" not in calls[1]["prompt"] and calls[1]["system"] == bit_gate.EDITOR_SYSTEM
    assert calls[1]["temp"] == config.bit_editor_temperature and calls[0]["is_bit"] and not calls[1]["is_bit"]
    assert brain.is_generating is False and list(brain.dialogue_history)[-1]["text"] == done["full_text"]
    row = json.loads(open(config.bit_gate_log_path, encoding="utf-8").read().splitlines()[-1])
    assert row["aired"] == done["full_text"] and row["candidates"][0]["lint"] == ["we_voice"]


def test_gate_caches_nothing_when_the_editor_passes_then_fails_open_eventually(brain):
    none = '{"scores": [{"n": 1, "laugh": 2, "true": 3}, {"n": 2, "laugh": 1, "true": 3}], "pick": 0, "why": "wise, not funny"}'
    two = f"1. {GOOD_A}\n2. {GOOD_B}"
    calls = script(brain, [two, none, two, none] * 3)
    for _ in range(2):
        evs = run(brain, bypass_cache=True)
        assert evs == [] and brain.is_generating is False
    assert "An editor read the previous candidates cold" in calls[2]["prompt"]      # retry carries the verdict
    assert len(brain.dialogue_history) == 0                                          # rejects never enter memory
    evs = run(brain, bypass_cache=True)                                              # third empty refill in a row
    assert evs[-1]["type"] == "complete" and evs[-1]["full_text"].startswith("I invented gravity")


def test_gate_never_fails_open_with_a_rule_breaking_bit(brain, monkeypatch):
    monkeypatch.setattr(config, "bit_gate_fail_open_after", 1)
    script(brain, [f"1. {WE_BIT}", f"1. {WE_BIT}"])
    assert run(brain, bypass_cache=True) == []


def test_gate_survives_an_unreadable_editor(brain):
    script(brain, [f"1. {GOOD_B}\n2. {GOOD_A}", "Honestly they're both fine!"])
    assert run(brain, bypass_cache=True)[-1]["full_text"].startswith("I spent four billion")


def test_gate_falls_back_to_single_pass_on_provider_error(brain):
    script(brain, [RuntimeError("boom"), GOOD_A])
    evs = run(brain, bypass_cache=True)
    assert evs[-1]["type"] == "complete" and "is_vetted" not in evs[-1]


def test_live_turns_and_internal_retries_never_enter_the_gate(brain):
    calls = script(brain, [GOOD_A, GOOD_A])
    run(brain)                                       # live spontaneous turn, cache empty
    run(brain, bypass_cache=True, _skip_gate=True)   # the transient-error retry path
    assert len(calls) == 2 and all("finished candidates" not in c["prompt"] for c in calls)


def test_gate_can_be_switched_off_for_ab(brain, monkeypatch):
    monkeypatch.setattr(config, "bit_gate_enabled", False)
    calls = script(brain, [GOOD_A])
    assert run(brain, bypass_cache=True)[-1]["type"] == "complete" and len(calls) == 1
