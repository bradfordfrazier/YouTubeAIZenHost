"""
Bit Lab — offline A/B harness for spontaneous bits.

The reason this exists: every prompt change so far has been judged against memory of how bits
sounded a week ago. That is how the show lost its register for a stretch and why it took days to
find. This generates two batches under two configurations, interleaves them blind, and writes a
key you open only after you have picked. A change either wins the comparison or it does not ship.

It never touches the render worker, NDI, or the turn scheduler — it only calls the brain, so it
is safe to run while the stream is DOWN (it will compete for the GPU if TTS is mid-turn, and it
consumes Gemini credits, so do not run it during a broadcast).

USAGE
  # 30 bits on the current settings, for a baseline
  python bit_lab.py --n 30 --label baseline

  # A/B: current settings vs one changed value
  python bit_lab.py --n 24 --a "{}" --b '{"one_liner_ratio": 0.6}'
  python bit_lab.py --n 24 --a '{"bit_temperature": 0.85}' --b '{"bit_temperature": 1.0}'

  # A/B a prompt edit: stash the current ai_brain.py, edit it, and pass --b-file
  python bit_lab.py --n 24 --b-file ai_brain_variant.py

  # Overrides may be key=value pairs (works in every shell, including Windows PowerShell, which
  # mangles the JSON form). 'default' = no overrides.
  # A/B the bit gate (writer -> lint -> cold-read editor) against single-pass generation
  python bit_lab.py --n 24 --a bit_gate_enabled=false --b default
  # ...the editor alone (lint stays on in both arms)
  python bit_lab.py --n 24 --a bit_editor_enabled=false --b default
  # ...handing the whole theme card over (legacy) vs anchor + direction, vs anchor only
  python bit_lab.py --n 24 --a bit_theme_mode=full --b default
  python bit_lab.py --n 24 --a bit_theme_mode=anchor_hint --b bit_theme_mode=anchor_only

  # score a finished blind file back into a verdict
  python bit_lab.py --score bitlab/20260908-141500/blind.md

OUTPUT  bitlab/<timestamp>/
  blind.md     interleaved, unlabelled, with a [ ] box per bit — mark the ones that land
  KEY.json     which variant produced which line (do not open until you have marked blind.md)
  raw.jsonl    every bit with variant, form, theme, mood, words, latency
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_brain(module_path: Optional[str] = None):
    """Imports AIBrain, optionally from an alternate ai_brain file for prompt A/B."""
    if module_path:
        import importlib.util
        spec = importlib.util.spec_from_file_location("ai_brain_variant", module_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.AIBrain
    from ai_brain import AIBrain
    return AIBrain


def _parse_overrides(arg: Optional[str]) -> Dict[str, Any]:
    """
    Accepts either JSON ('{"bit_gate_enabled": false}') or shell-proof pairs
    (bit_gate_enabled=false,bit_candidates=5). The pair form exists because Windows PowerShell
    strips the inner double quotes from a JSON argument before Python ever sees it, which made
    every documented A/B command die in json.loads before a single file was written.
    'default', 'current', 'none' and '{}' all mean "no overrides".
    """
    a = (arg or "").strip()
    if a.lower() in ("", "{}", "default", "current", "none"):
        return {}
    if a.startswith("{"):
        try:
            return json.loads(a)
        except json.JSONDecodeError:
            raise SystemExit(
                f"Could not read overrides {a!r} as JSON — your shell probably ate the quotes.\n"
                "Use the pair form instead, e.g.  --a bit_gate_enabled=false --b default"
            )
    out: Dict[str, Any] = {}
    for pair in a.split(","):
        if "=" not in pair:
            raise SystemExit(f"Override {pair!r} is not key=value.")
        k, v = pair.split("=", 1)
        v = v.strip()
        try:
            out[k.strip()] = json.loads(v.lower() if v.lower() in ("true", "false", "null") else v)
        except json.JSONDecodeError:
            out[k.strip()] = v          # bare string, e.g. bit_theme_mode=full
    return out


def _apply_overrides(cfg, overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Sets config attributes for one batch; returns the previous values for restoration."""
    prev = {}
    for k, v in overrides.items():
        if not hasattr(cfg, k):
            print(f"  ! unknown config key '{k}' — ignoring")
            continue
        prev[k] = getattr(cfg, k)
        setattr(cfg, k, v)
    return prev


async def _generate_batch(brain, n: int, variant: str, overrides: Dict[str, Any]) -> List[Dict]:
    """Generates n bits, feeding each back into dialogue_history so anti-repetition behaves live."""
    from config import config
    prev = _apply_overrides(config, overrides)
    # brain.cfg normally IS `config`. Applying the overrides to it a second time recorded the
    # already-overridden values as "previous", and restoring those last left arm A's overrides in
    # force for arm B. Any A/B where --a set a key that --b did not was comparing A with A.
    prev_brain = _apply_overrides(brain.cfg, overrides) if brain.cfg is not config else {}
    out: List[Dict] = []
    try:
        for i in range(n):
            t0 = time.perf_counter()
            text, mood, vetted = "", "", False
            try:
                async for ev in brain.generate_response_stream("[SPONTANEOUS_REFLECTION]", bypass_cache=True):
                    if ev.get("type") == "mood":
                        mood = ev.get("mood", "")
                    elif ev.get("type") == "complete":
                        text = (ev.get("full_text") or "").strip()
                        mood = ev.get("mood", mood)
                        vetted = bool(ev.get("is_vetted"))
            except Exception as e:
                print(f"  ! generation {i+1} failed: {e}")
                continue
            if not text:
                # With the bit gate on, "nothing" is a legitimate result: every candidate was
                # linted out or the editor passed on all of them. It costs the arm a sample.
                print(f"  [{variant}] {i+1}/{n}  (no bit — see [Bit Gate] lines in the log)")
                continue
            dt = time.perf_counter() - t0
            rec = {
                "variant": variant,
                "text": text,
                "mood": mood,
                "form": getattr(brain, "last_bit_form", ""),
                "theme": getattr(brain, "last_spontaneous_theme", ""),
                "words": len(text.split()),
                "seconds": round(dt, 2),
                "vetted": vetted,
            }
            out.append(rec)
            # Feed it back so the anti-repetition window sees a realistic history.
            brain.dialogue_history.append({"text": text, "mood": mood, "timestamp": time.time()})
            print(f"  [{variant}] {i+1}/{n}  {rec['form']:<13} {rec['words']:>3}w  {dt:4.1f}s  {text[:70]}")
    finally:
        _apply_overrides(brain.cfg, prev_brain)   # reverse order of application
        _apply_overrides(config, prev)
    return out


def _write_blind(rows: List[Dict], outdir: Path, two_variants: bool) -> None:
    shuffled = rows[:]
    random.shuffle(shuffled)
    lines = [
        "# Bit Lab — blind comparison",
        "",
        "Mark the bits that actually land: change `[ ]` to `[x]`. Mark nothing else.",
        "Do NOT open KEY.json until every box is decided.",
        "",
        "Judge only: did it make you laugh, and would it survive being clipped cold?",
        "Ignore length, mood, and whether it 'sounds like the show'.",
        "",
    ]
    for i, r in enumerate(shuffled, 1):
        lines.append(f"- [ ] **{i:02d}.** {r['text']}")
        lines.append("")
    (outdir / "blind.md").write_text("\n".join(lines), encoding="utf-8")
    key = {str(i): {"variant": r["variant"], "form": r["form"], "theme": r["theme"]}
           for i, r in enumerate(shuffled, 1)}
    (outdir / "KEY.json").write_text(json.dumps(key, indent=2), encoding="utf-8")


def score_blind(blind_path: Path) -> None:
    """Reads a marked blind.md next to its KEY.json and reports the verdict."""
    outdir = blind_path.parent
    key = json.loads((outdir / "KEY.json").read_text(encoding="utf-8"))
    marked, total = {}, {}
    forms_hit, forms_total = {}, {}
    for line in blind_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"- \[( |x|X)\] \*\*(\d+)\.\*\*", line)
        if not m:
            continue
        hit = m.group(1).lower() == "x"
        idx = str(int(m.group(2)))
        entry = key.get(idx)
        if not entry:
            continue
        v, f = entry["variant"], entry.get("form", "?")
        total[v] = total.get(v, 0) + 1
        forms_total[f] = forms_total.get(f, 0) + 1
        if hit:
            marked[v] = marked.get(v, 0) + 1
            forms_hit[f] = forms_hit.get(f, 0) + 1

    print("\n=== VERDICT ===")
    for v in sorted(total):
        hits = marked.get(v, 0)
        print(f"  variant {v}:  {hits}/{total[v]} landed  ({hits / total[v] * 100:.0f}%)")
    if len(total) == 2:
        a, b = sorted(total)
        ra, rb = marked.get(a, 0) / total[a], marked.get(b, 0) / total[b]
        diff = abs(ra - rb) * 100
        winner = a if ra > rb else b
        # With ~25 per arm, anything under ~15 points is noise. Say so rather than declaring a win.
        verdict = f"{winner} wins by {diff:.0f} points" if diff >= 15 else "TOO CLOSE TO CALL — treat as no difference"
        print(f"\n  {verdict}")
    print("\n  by form:")
    for f in sorted(forms_total):
        h = forms_hit.get(f, 0)
        print(f"    {f:<14} {h}/{forms_total[f]}  ({h / forms_total[f] * 100:3.0f}%)")

    keepers = []
    for line in blind_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"- \[(x|X)\] \*\*(\d+)\.\*\* (.+)", line)
        if m:
            keepers.append(m.group(3).strip())
    if keepers:
        fav = outdir / "winners.jsonl"
        with fav.open("w", encoding="utf-8") as fh:
            for t in keepers:
                idx = None
                for line in blind_path.read_text(encoding="utf-8").splitlines():
                    mm = re.match(r"- \[(x|X)\] \*\*(\d+)\.\*\* (.+)", line)
                    if mm and mm.group(3).strip() == t:
                        idx = str(int(mm.group(2)))
                        break
                meta = key.get(idx or "", {})
                fh.write(json.dumps({"text": t, "form": meta.get("form", ""),
                                     "theme": meta.get("theme", ""), "saved_at": time.time()},
                                    ensure_ascii=False) + "\n")
        print(f"\n  {len(keepers)} winners written to {fav}")
        print("  Append them to data/favorite_bits.jsonl to use them as few-shot examples.")


async def main_async(args) -> None:
    outdir = Path(args.out) / time.strftime("%Y%m%d-%H%M%S")
    outdir.mkdir(parents=True, exist_ok=True)

    AIBrainA = _load_brain(None)
    brain_a = AIBrainA()
    rows: List[Dict] = []

    a_over = _parse_overrides(args.a)
    print(f"\n--- variant A ({args.label or 'current'}) overrides={a_over or 'none'} ---")
    rows += await _generate_batch(brain_a, args.n, "A", a_over)

    if args.b is not None or args.b_file:
        b_over = _parse_overrides(args.b)
        if args.b_file:
            AIBrainB = _load_brain(args.b_file)
            brain_b = AIBrainB()
        else:
            brain_b = AIBrainA()
        print(f"\n--- variant B ({args.b_file or 'same file'}) overrides={b_over or 'none'} ---")
        rows += await _generate_batch(brain_b, args.n, "B", b_over)

    if not rows:
        print("\nNo bits generated — check GEMINI_API_KEY and the server logs.")
        return

    with (outdir / "raw.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    _write_blind(rows, outdir, two_variants=len({r["variant"] for r in rows}) == 2)

    print(f"\nWrote {len(rows)} bits to {outdir.resolve()}")
    print(f"  1. Mark the ones that land in {outdir / 'blind.md'}")
    print(f"  2. python bit_lab.py --score {outdir / 'blind.md'}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Offline A/B harness for spontaneous bits.")
    ap.add_argument("--n", type=int, default=24, help="bits per variant")
    ap.add_argument("--a", help='JSON config overrides for variant A, e.g. \'{"bit_temperature":0.85}\'')
    ap.add_argument("--b", help="JSON config overrides for variant B; omit for a single-variant baseline")
    ap.add_argument("--b-file", help="alternate ai_brain.py for variant B (prompt A/B)")
    ap.add_argument("--label", help="name for a single-variant run")
    ap.add_argument("--out", default="bitlab")
    ap.add_argument("--score", help="score a previously marked blind.md")
    args = ap.parse_args()

    if args.score:
        score_blind(Path(args.score))
        return
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
