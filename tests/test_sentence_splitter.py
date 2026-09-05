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
