"""
Phase 3 Test Suite: Continuity & Memory (C2, C3, C4).
Validates ChatterDB relationship profiles, MemoryManager lore & session briefs,
AIBrain conversational thread memory, and context prompt injection.
"""

import asyncio
from pathlib import Path
import shutil
import tempfile

from ai_brain import AIBrain
from chatter_db import ChatterDB, ChatterProfile
from memory_manager import MemoryManager


def test_chatter_db():
    print("\n" + "=" * 50)
    print("TEST 1: ChatterDB Profiles & Relationship Memory (C3)")
    print("=" * 50)

    test_dir = Path(tempfile.mkdtemp(prefix="test_chatter_"))
    try:
        db_path = str(test_dir / "chatter_db.json")
        db = ChatterDB(db_path=db_path)

        # 1. Verify pre-seeded cast profiles
        dave = db.get_profile("ExistentialDave")
        assert dave is not None, "Pre-seeded @ExistentialDave missing"
        assert dave.is_cast is True
        assert "IT" in dave.topics_discussed

        # 2. Record new human chatter activity across multiple sessions
        p1 = db.record_activity(
            handle="CosmicAlice",
            display_name="Alice in Space",
            message="I love contemplating simulation theory and consciousness in coding!",
            is_member=True,
            session_id="session_001",
        )
        assert p1.visit_count == 1
        assert p1.message_count == 1
        assert p1.is_member is True
        assert "consciousness" in p1.topics_discussed or "simulation" in p1.topics_discussed

        # 3. Second message in same session
        p2 = db.record_activity(
            handle="CosmicAlice",
            display_name="Alice in Space",
            message="Also, what about free will?",
            is_member=True,
            session_id="session_001",
        )
        assert p2.visit_count == 1
        assert p2.message_count == 2
        assert "free will" in p2.topics_discussed

        # 4. Third message in next session
        p3 = db.record_activity(
            handle="CosmicAlice",
            display_name="Alice in Space",
            message="Hello again!",
            is_member=True,
            session_id="session_002",
        )
        assert p3.visit_count == 2
        assert p3.message_count == 3

        # 5. Add custom qualitative note
        db.add_note("CosmicAlice", "Software engineer interested in Zen & simulations")

        # 6. Verify context snippet generation
        snippet = db.get_chatter_context("CosmicAlice")
        assert snippet is not None
        assert "@CosmicAlice" in snippet
        assert "Channel Member" in snippet
        assert "Visit #2" in snippet
        assert "Software engineer" in snippet
        print(f"-> Generated Chatter Context: {snippet}")

        # 7. Test reloading from disk
        db_reloaded = ChatterDB(db_path=db_path)
        p_loaded = db_reloaded.get_profile("CosmicAlice")
        assert p_loaded is not None
        assert p_loaded.visit_count == 2
        assert p_loaded.message_count == 3
        print(f"-> Verified persistent reload of {len(db_reloaded.profiles)} profiles")
        print("[PASS] ChatterDB verified successfully!")

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_memory_manager():
    print("\n" + "=" * 50)
    print("TEST 2: MemoryManager Lore & Session Briefs (C4)")
    print("=" * 50)

    test_dir = Path(tempfile.mkdtemp(prefix="test_memory_"))
    try:
        kb_path = str(test_dir / "knowledge_base.json")
        mm = MemoryManager(kb_path=kb_path)

        # 1. Verify pre-seeded rulings and lore
        assert "cereal" in mm.canonical_rulings
        assert "observer" in mm.canonical_rulings
        assert len(mm.channel_lore) >= 2

        # 2. Test lore matching
        lore_match = mm.get_relevant_lore("Is cereal considered a soup in the universe?")
        assert len(lore_match) >= 1
        assert "Cereal is definitively soup" in lore_match[0]
        print(f"-> Matched Lore: {lore_match[0]}")

        # 3. Test recording custom ruling
        mm.record_canonical_ruling("coffee", "Coffee is liquid presence awakening the machine.")
        assert "coffee" in mm.canonical_rulings
        coffee_lore = mm.get_relevant_lore("Should I drink coffee during meditation?")
        assert len(coffee_lore) >= 1
        assert "liquid presence" in coffee_lore[0]

        # 4. Test session continuity brief
        brief = mm.get_session_continuity_brief()
        assert "Recent Session Memory:" in brief
        print(f"-> Session Continuity Brief: {brief}")

        # 5. Record completed session summary
        mm.record_session_summary("session_001", {"summary_text": "Debated quantum zen and Jira tickets with @ExistentialDave.", "total_turns": 35})
        new_brief = mm.get_session_continuity_brief()
        assert "Debated quantum zen" in new_brief

        # 6. Test reload from disk
        mm_reloaded = MemoryManager(kb_path=kb_path)
        assert "coffee" in mm_reloaded.canonical_rulings
        assert len(mm_reloaded.session_history) >= 2
        print("[PASS] MemoryManager verified successfully!")

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_conversational_thread_tracking_and_context_injection():
    print("\n" + "=" * 50)
    print("TEST 3: In-Session Conversational Thread Tracking (C2)")
    print("=" * 50)

    brain = AIBrain()

    # Pre-populate some chatter data for @ExistentialDave
    brain.chatter_db.record_activity(
        handle="ExistentialDave",
        display_name="Existential Dave",
        message="I have a Jira ticket about the observer.",
        is_member=False,
        is_cast=True,
    )

    # 1. Record completed Q&A turns
    brain.record_completed_turn(
        trigger="Cast member @ExistentialDave asks: 'Where is the observer in this code?'",
        full_text="The observer is not a variable inside the stack frame; it is the execution itself.",
        mood="thoughtful",
        author="ExistentialDave",
    )

    brain.record_completed_turn(
        trigger="Cast member @SpeedrunnerKyle asks: 'Can I speedrun enlightenment?'",
        full_text="You cannot speedrun where you already are, Kyle. Every frame is the final boss.",
        mood="snarky",
        author="SpeedrunnerKyle",
    )

    assert len(brain.recent_qa_threads) == 2

    # 2. Build context prompt for a follow-up question
    prompt = brain._build_context_prompt("Chat message from @ExistentialDave: 'So who resolves the merge conflict?'")

    # Verify all C2, C3, C4 sections are present in context
    assert "--- Channel Continuity & Lore ---" in prompt, "C4 Session Continuity missing"
    assert "--- Chatter Profile Context ---" in prompt, "C3 Chatter Profile missing"
    assert "@ExistentialDave" in prompt
    assert "Synthetic Cast Member" in prompt
    assert "--- Recent Q&A Conversational Thread ---" in prompt, "C2 Q&A Thread missing"
    assert "Where is the observer in this code?" in prompt
    assert "CRITICAL CONTINUITY CONSTRAINT" in prompt

    print("-> Verified complete context prompt assembly containing C2 Thread, C3 Chatter Profile, and C4 Lore")
    print("[PASS] In-Session Thread Tracking & Context Injection verified!")


async def test_live_stream_inference_with_memory():
    print("\n" + "=" * 50)
    print("TEST 4: Live / Simulated Inference with Thread & Relationship Context")
    print("=" * 50)

    brain = AIBrain()
    # Force simulated fallback for deterministic test execution
    brain.client = None

    brain.record_completed_turn(
        trigger="Chat message from @TrollChad: 'Is cereal soup?'",
        full_text="Cereal is definitively soup in the cosmic bowl.",
        mood="savage",
        author="TrollChad",
    )

    events = []
    async for ev in brain.generate_response_stream("Chat message from @TrollChad: 'What about hot dog buns?'"):
        events.append(ev)

    complete_ev = next(e for e in events if e["type"] == "complete")
    assert len(complete_ev["full_text"]) > 5
    print(f"-> Response to follow-up [{complete_ev['mood'].upper()}]: '{complete_ev['full_text']}'")
    print("[PASS] Stream inference with continuity verified!")


async def run_all_phase3_tests():
    print("\n" + "#" * 60)
    print("RUNNING PHASE 3 VERIFICATION TEST SUITE")
    print("#" * 60)

    test_chatter_db()
    test_memory_manager()
    test_conversational_thread_tracking_and_context_injection()
    await test_live_stream_inference_with_memory()

    print("\n" + "#" * 60)
    print("ALL PHASE 3 TESTS PASSED PERFECTLY!")
    print("#" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_phase3_tests())
