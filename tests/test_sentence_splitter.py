"""
Unit tests for incremental sentence-splitting and mood tag extraction (Phase 2).
Runnable via pytest.
"""

from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_brain import AIBrain


def test_sentence_splitter_basic():
    brain = AIBrain()
    stream_buffer = "We are all one experiencing itself. What is your question today? "
    sentences, rem = brain._extract_completed_sentences(stream_buffer)
    assert len(sentences) == 2
    assert sentences[0] == "We are all one experiencing itself."
    assert sentences[1] == "What is your question today?"
    assert rem == ""


def test_sentence_splitter_partial():
    brain = AIBrain()
    stream_buffer = "The universe is expanding into infinity. But in your mind,"
    sentences, rem = brain._extract_completed_sentences(stream_buffer)
    assert len(sentences) == 1
    assert sentences[0] == "The universe is expanding into infinity."
    assert rem == "But in your mind,"


def test_sentence_splitter_abbreviations():
    brain = AIBrain()
    stream_buffer = "Dr. Smith met with Mr. Jones vs. the cosmic council. What do you think? "
    sentences, rem = brain._extract_completed_sentences(stream_buffer)
    assert len(sentences) == 2
    assert sentences[0] == "Dr. Smith met with Mr. Jones vs. the cosmic council."
    assert sentences[1] == "What do you think?"


def test_mood_tag_extraction():
    brain = AIBrain()
    raw = "[MOOD: transcendent] We are all one experiencing itself."
    mood, clean = brain._extract_mood(raw)
    assert mood == "transcendent"
    assert clean == "We are all one experiencing itself."


def test_mood_tag_fallback():
    brain = AIBrain()
    raw = "No explicit mood tag here."
    mood, clean = brain._extract_mood(raw)
    assert mood == "neutral"
    assert clean == "No explicit mood tag here."


def test_sentence_pipelining_producer_consumer():
    """Verifies async sentence producer-consumer queue streaming mechanism."""
    import asyncio

    async def _runner():
        sentence_queue = asyncio.Queue()
        produced = ["First thought.", "Second conclusion.", "Final aphorism."]
        consumed = []

        async def _consumer():
            while True:
                item = await sentence_queue.get()
                if item is None:
                    sentence_queue.task_done()
                    break
                sent_text, sent_mood = item
                consumed.append((sent_text, sent_mood))
                sentence_queue.task_done()

        consumer_task = asyncio.create_task(_consumer())

        for s in produced:
            await sentence_queue.put((s, "thoughtful"))

        await sentence_queue.put(None)
        await consumer_task

        assert len(consumed) == 3
        assert [c[0] for c in consumed] == produced
        assert all(c[1] == "thoughtful" for c in consumed)

    asyncio.run(_runner())
