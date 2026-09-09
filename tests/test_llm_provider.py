"""
Multi-provider support: Gemini (default) and Anthropic Claude.

Both backends feed ONE processing loop. The mood tag, sentence splitting and [BEAT] handling are
subtle enough that a per-backend copy drifts out of sync — that class of bug already silenced the
whole TTS pipeline once via a key mismatch.
"""
from pathlib import Path
import asyncio
import importlib
import os
import sys
import types

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent


def _brain(**env):
    for k, v in env.items():
        os.environ[k] = v
    import config as cfgmod
    importlib.reload(cfgmod)
    import ai_brain
    importlib.reload(ai_brain)
    return ai_brain.AIBrain()


class _Delta:
    def __init__(self, type_, text=""):
        self.type = type_
        self.text = text


class _Event:
    def __init__(self, type_, delta=None):
        self.type = type_
        self.delta = delta


class _FakeStream:
    def __init__(self, pieces):
        self.pieces = pieces

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def __aiter__(self):
        # A thinking delta must never reach the speech pipeline; it would be spoken aloud.
        yield _Event("content_block_delta", _Delta("thinking_delta", "PRIVATE REASONING"))
        for p in self.pieces:
            yield _Event("content_block_delta", _Delta("text_delta", p))
        yield _Event("message_stop")


class _FakeMessages:
    def __init__(self, pieces):
        self.pieces = pieces
        self.last_kwargs = None

    def stream(self, **kw):
        self.last_kwargs = kw
        return _FakeStream(self.pieces)

    def create(self, *, max_tokens=None, messages=None, model=None, system=None,
               thinking=None, output_config=None, **k):
        pass


def _attach_fake(brain, pieces):
    fake = _FakeMessages(pieces)
    brain.anthropic_client = types.SimpleNamespace(messages=fake)
    return fake


def test_default_provider_is_gemini():
    b = _brain(LLM_PROVIDER="gemini")
    assert b.provider == "gemini"


def test_anthropic_selected_when_configured():
    b = _brain(LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="sk-ant-" + "x" * 40)
    assert b.provider == "anthropic"
    assert b.anthropic_client is not None
    assert b.model_name == b.cfg.anthropic_model


def test_missing_anthropic_key_falls_back_rather_than_going_silent():
    """A bad provider config must not drop the show into simulated mode without saying so."""
    b = _brain(LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="")
    assert b.provider == "gemini"


def test_anthropic_stream_drives_the_shared_pipeline():
    b = _brain(LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="sk-ant-" + "x" * 40)
    fake = _attach_fake(b, ["[MOOD: deadpan] I built a machine to find ",
                            "the machine. ", "[BEAT] It is still ", "looking. "])

    async def run():
        return [ev async for ev in b.generate_response_stream("[SPONTANEOUS_REFLECTION]",
                                                              bypass_cache=True)]
    events = asyncio.run(run())
    kinds = [e["type"] for e in events]
    assert "mood" in kinds and "sentence" in kinds and "complete" in kinds

    moods = [e["mood"] for e in events if e["type"] == "mood"]
    assert moods == ["deadpan"]

    sentences = [e for e in events if e["type"] == "sentence"]
    assert len(sentences) == 2
    assert sentences[1]["beat_before"] is True, "[BEAT] must survive the Anthropic path"

    final = [e for e in events if e["type"] == "complete"][0]["full_text"]
    assert "[MOOD:" not in final and "[BEAT]" not in final
    assert "PRIVATE REASONING" not in final, "thinking block leaked into spoken text"


def test_thinking_budget_and_kwarg_filtering():
    b = _brain(LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="sk-ant-" + "x" * 40)
    fake = _attach_fake(b, ["[MOOD: deadpan] A line that is long enough. "])

    async def run():
        async for _ in b.generate_response_stream("[SPONTANEOUS_REFLECTION]", bypass_cache=True):
            pass
    asyncio.run(run())

    kw = fake.last_kwargs
    assert kw["model"] == b.cfg.anthropic_model
    assert kw["system"] == b.cfg.ai_system_prompt
    assert kw["messages"][0]["role"] == "user"
    if "thinking" in kw:
        # Extended thinking requires budget >= 1024 and strictly less than max_tokens.
        assert kw["thinking"]["budget_tokens"] >= 1024
        assert kw["max_tokens"] > kw["thinking"]["budget_tokens"]
    # Unsupported params must be filtered, not passed blindly to a differing SDK version.
    assert "temperature" not in kw or "temperature" in _create_params(b)


def _create_params(brain):
    import inspect
    return inspect.signature(brain.anthropic_client.messages.create).parameters


def test_one_processing_loop_for_all_providers():
    """Guards against a per-backend copy of the mood/sentence/beat logic drifting."""
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    assert "_delta_stream" in src
    assert src.count("Detected Mood Tag:") == 1, "mood detection is duplicated per backend again"
    assert src.count('yield {"type": "sentence", "text": s_text') <= 4
