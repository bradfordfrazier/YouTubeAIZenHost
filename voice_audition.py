"""
Voice Audition Harness for I AM.

Renders the SAME set of persona-critical lines through every candidate reference voice on the
Chatterbox server, at the exaggeration values the app actually uses, so you can pick a reference
clip by ear instead of by vibes.

Usage (from the app folder, with the Chatterbox server running):

    python voice_audition.py                       # audition every voice the server knows about
    python voice_audition.py --voices emmanuel p308 candidate_a candidate_b
    python voice_audition.py --blind               # randomise names into A/B/C for honest comparison
    python voice_audition.py --lines one_liner closer

Output: auditions/<timestamp>/<voice>__<line>__<mood>.wav  plus a manifest.json.
With --blind the folder is auditions/<timestamp>/blind/ and the mapping is written to
KEY.json — don't open it until you've picked a winner.

Why these lines: the persona lives or dies on (a) a flat one-liner that must not sound performed,
(b) a setup->[BEAT]->punchline where the pause has to feel intentional, (c) a savage closer that
needs range without shouting, and (d) a warm answer to a real viewer. A reference clip that
handles all four is the one to use.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

try:
    from config import config
    DEFAULT_SERVER = config.tts_server_url
    DEFAULT_VOICE = config.tts_reference_voice
    MOOD_MAP = dict(config.tts_mood_exaggeration_map)
    BEAT_GAP = float(config.tts_beat_gap_sec)
except Exception:  # standalone use without the app package
    DEFAULT_SERVER = "http://192.168.0.115:8123"
    DEFAULT_VOICE = "emmanuel"
    MOOD_MAP = {"deadpan": 0.30, "snarky": 0.70, "savage": 0.85, "thoughtful": 0.45, "hyped": 0.80}
    BEAT_GAP = 0.55


# Each line: (id, mood, text). [BEAT] is rendered as a real pause, exactly as the app does it.
AUDITION_LINES = [
    (
        "one_liner",
        "deadpan",
        "I bought a book on time travel. It arrived yesterday, which I felt was showing off.",
    ),
    (
        "bit_with_beat",
        "deadpan",
        "You spent nine minutes looking for the keys that were in your other hand. "
        "The universe did not hide them; it just wanted to watch. [BEAT] "
        "You are infinity, patting its own pockets.",
    ),
    (
        "savage_closer",
        "savage",
        "You asked the cosmos for a sign that you are on the right path. [BEAT] "
        "It sent you a buffering icon and a mild sense of dread.",
    ),
    (
        "warm_answer",
        "thoughtful",
        "MillCreekExchange, you are not lost. You are just standing somewhere you have not "
        "decided to call home yet.",
    ),
    (
        "long_form",
        "snarky",
        "Official notice from management: the search for meaning has been discontinued due to "
        "lack of interest from meaning itself. Refunds are unavailable, as no one has been "
        "charged. Existing seekers may continue seeking, but the department has been converted "
        "into a break room. [BEAT] The coffee is free, which is the closest thing to an answer "
        "anyone has produced in four thousand years.",
    ),
]

BEAT_RE = re.compile(r"\[\s*BEAT\s*\]", re.IGNORECASE)


async def fetch_server_voices(server: str) -> List[str]:
    """Asks the server what reference voices it has. Falls back to an empty list."""
    for path in ("/voices", "/api/voices", "/v1/voices"):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.get(server.rstrip("/") + path) as r:
                    if r.status != 200:
                        continue
                    data = await r.json(content_type=None)
        except Exception:
            continue
        if isinstance(data, dict):
            for key in ("voices", "predefined_voices", "reference_voices", "data"):
                if key in data:
                    data = data[key]
                    break
        if isinstance(data, list):
            out = []
            for v in data:
                name = v.get("name") or v.get("id") or v.get("filename") if isinstance(v, dict) else str(v)
                if name:
                    out.append(Path(str(name)).stem)
            if out:
                return sorted(set(out))
    return []


async def synth(session: aiohttp.ClientSession, server: str, text: str, voice: str,
                exaggeration: float, cfg_weight: float) -> Optional[bytes]:
    payload = {"text": text, "voice": voice, "exaggeration": exaggeration,
               "cfg_weight": cfg_weight, "format": "wav"}
    try:
        async with session.post(server.rstrip("/") + "/synthesize", json=payload) as r:
            if r.status != 200:
                print(f"    ! server returned {r.status} for voice={voice}")
                return None
            return await r.read()
    except Exception as e:
        print(f"    ! request failed for voice={voice}: {e}")
        return None


def stitch_with_beat(chunks: List[bytes], gap_sec: float) -> bytes:
    """Concatenates WAV chunks with `gap_sec` of silence between them (mirrors push_audio)."""
    import io
    import numpy as np
    import soundfile as sf

    pieces = []
    sr = None
    for i, raw in enumerate(chunks):
        data, this_sr = sf.read(io.BytesIO(raw), dtype="float32", always_2d=True)
        sr = sr or this_sr
        if i > 0:
            pieces.append(np.zeros((int(sr * gap_sec), data.shape[1]), dtype="float32"))
        pieces.append(data)
    out = np.concatenate(pieces, axis=0)
    buf = io.BytesIO()
    sf.write(buf, out, sr or 24000, format="WAV", subtype="FLOAT")
    return buf.getvalue()


async def audition(server: str, voices: List[str], line_ids: Optional[List[str]],
                   cfg_weight: float, blind: bool, outdir: Path) -> None:
    lines = [l for l in AUDITION_LINES if not line_ids or l[0] in line_ids]
    if not lines:
        print(f"No lines matched {line_ids}. Available: {[l[0] for l in AUDITION_LINES]}")
        return

    labels = {v: v for v in voices}
    if blind:
        tags = [chr(ord("A") + i) for i in range(len(voices))]
        shuffled = voices[:]
        random.shuffle(shuffled)
        labels = {v: f"voice_{tags[i]}" for i, v in enumerate(shuffled)}
        outdir = outdir / "blind"

    outdir.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, object] = {"server": server, "cfg_weight": cfg_weight,
                                   "beat_gap_sec": BEAT_GAP, "renders": []}

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
        for voice in voices:
            print(f"\n=== {voice} ===")
            for line_id, mood, text in lines:
                exag = float(MOOD_MAP.get(mood, 0.5))
                parts = [p.strip() for p in BEAT_RE.split(text) if p.strip()]
                t0 = time.perf_counter()
                chunks = []
                ok = True
                for part in parts:
                    raw = await synth(session, server, part, voice, exag, cfg_weight)
                    if raw is None:
                        ok = False
                        break
                    chunks.append(raw)
                if not ok or not chunks:
                    continue
                wav = stitch_with_beat(chunks, BEAT_GAP) if len(chunks) > 1 else chunks[0]
                name = f"{labels[voice]}__{line_id}__{mood}.wav"
                (outdir / name).write_bytes(wav)
                dt = time.perf_counter() - t0
                print(f"  {line_id:<14} mood={mood:<10} exag={exag:.2f}  {dt:5.1f}s  -> {name}")
                manifest["renders"].append(
                    {"voice": voice, "label": labels[voice], "line": line_id,
                     "mood": mood, "exaggeration": exag, "file": name, "wall_sec": round(dt, 2)}
                )

    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if blind:
        (outdir.parent / "KEY.json").write_text(
            json.dumps({v: k for k, v in labels.items()}, indent=2), encoding="utf-8"
        )
        print(f"\nBlind renders in {outdir}. Pick a winner, THEN open {outdir.parent / 'KEY.json'}.")
    else:
        print(f"\nDone. {outdir}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Audition Chatterbox reference voices for I AM.")
    ap.add_argument("--server", default=DEFAULT_SERVER)
    ap.add_argument("--voices", nargs="*", help="voice names; default = ask the server, else current voice")
    ap.add_argument("--lines", nargs="*", help=f"subset of {[l[0] for l in AUDITION_LINES]}")
    ap.add_argument("--cfg-weight", type=float, default=0.5,
                    help="Chatterbox cfg_weight. Lower (0.3) = slower, more deliberate pacing.")
    ap.add_argument("--blind", action="store_true", help="label outputs voice_A/B/C and hide the key")
    ap.add_argument("--out", default="auditions")
    args = ap.parse_args()

    voices = args.voices
    if not voices:
        voices = asyncio.run(fetch_server_voices(args.server))
        if voices:
            print(f"Server reports {len(voices)} voices: {', '.join(voices)}")
        else:
            voices = [DEFAULT_VOICE]
            print(f"Server did not list voices; auditioning current voice only: {DEFAULT_VOICE}")

    outdir = Path(args.out) / time.strftime("%Y%m%d-%H%M%S")
    asyncio.run(audition(args.server, voices, args.lines, args.cfg_weight, args.blind, outdir))


if __name__ == "__main__":
    main()
