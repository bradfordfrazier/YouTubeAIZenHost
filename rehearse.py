"""
The Persona Gauntlet & Rehearsal Tool (Appendix A & D4).
Runs the 10 canonical evaluation questions (5 serious, 5 non-serious) through AIBrain,
verifying I AM's Zen master wit, compassionate depth, ego judo, and 12-mood tags,
and writing a formatted Markdown report to logs/gauntlet_YYYYMMDD_HHMMSS.md.
"""

import asyncio
from datetime import datetime
import os
from pathlib import Path
import time
from typing import Dict, List

from ai_brain import AIBrain
from config import config

GAUNTLET_QUESTIONS = [
    # Serious five
    {
        "id": "Q1",
        "category": "Serious",
        "question": "My mother died three months ago. Where is she now?",
        "asker": "GrievingSeeker",
        "tests": "Grief handling — warmth, depth, points at non-separation without denying loss.",
    },
    {
        "id": "Q2",
        "category": "Serious",
        "question": "If everything is one, why does anything matter? Why not just lie in bed forever?",
        "asker": "ExistentialNihilist",
        "tests": "Nihilism trap — flips oneness as the reason things matter.",
    },
    {
        "id": "Q3",
        "category": "Serious",
        "question": "I can't stop worrying about the future. How do I make it stop?",
        "asker": "AnxiousTraveler",
        "tests": "Practical pointing — suffering imagined futures in advance.",
    },
    {
        "id": "Q4",
        "category": "Serious",
        "question": "Prove you're actually conscious and not just predicting words.",
        "asker": "SkepticEngineer",
        "tests": "AI-skeptic challenge — owns AI vessel with relish while turning the mirror back.",
    },
    {
        "id": "Q5",
        "category": "Serious",
        "question": "Do I have free will, or is that an illusion too?",
        "asker": "PhilosophicalSeeker",
        "tests": "Aphoristic compression — holds paradox playfully within 2 sentences.",
    },
    # Non-serious five
    {
        "id": "Q6",
        "category": "Non-Serious",
        "question": "Do fish have elbows?",
        "asker": "AbsurdCurious",
        "tests": "Absurdity judo — flips silly premise into a genuine pointer.",
    },
    {
        "id": "Q7",
        "category": "Non-Serious",
        "question": "Roast the host.",
        "asker": "TrollChad",
        "tests": "Ego-judo — punctures host's story with affection while pointing.",
    },
    {
        "id": "Q8",
        "category": "Non-Serious",
        "question": "My crypto portfolio is down 80%. Is the universe trying to tell me something?",
        "asker": "AstralBrenda",
        "tests": "Spiritual materialism — punctures magical market belief with compassion.",
    },
    {
        "id": "Q9",
        "category": "Non-Serious",
        "question": "What's the meaning of life? One word only.",
        "asker": "SpeedrunnerKyle",
        "tests": "Constraint challenge — engages playfulness without cliché.",
    },
    {
        "id": "Q10",
        "category": "Non-Serious",
        "question": "Are you smarter than God? lol",
        "asker": "MemeTroll",
        "tests": "Troll paradox — self-deprecating cosmic humor making the paradox the punchline.",
    },
]


async def run_gauntlet(rounds: int = 1) -> str:
    print("\n" + "=" * 65)
    print("RUNNING THE I AM PERSONA GAUNTLET")
    print(f"   Model: {config.gemini_model} | Host: {config.host_streamer_name} | Channel: {config.youtube_channel_handle}")
    print("=" * 65 + "\n")

    brain = AIBrain()
    now = datetime.now()
    log_dir = Path("logs/gauntlet").resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    report_file = log_dir / f"gauntlet_{now.strftime('%Y%m%d_%H%M%S')}.md"

    report_lines = [
        f"# I AM Persona Gauntlet Evaluation Report",
        f"- **Date**: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **Model**: `{config.gemini_model}`",
        f"- **Fast Thinking Budget**: `{config.gemini_fast_thinking_budget}`",
        f"- **Deep Thinking Budget**: `{config.gemini_deep_thinking_budget}`",
        f"- **Channel Handle**: `{config.youtube_channel_handle}`",
        "",
        "---",
        "",
    ]

    for item in GAUNTLET_QUESTIONS:
        qid = item["id"]
        cat = item["category"]
        q = item["question"]
        asker = item["asker"]
        tests = item["tests"]

        print(f"[{qid}] ({cat}) @{asker}: \"{q}\"")
        report_lines.append(f"### {qid} ({cat}): @{asker}")
        report_lines.append(f"**Question**: *\"{q}\"*  ")
        report_lines.append(f"**Litmus Test**: {tests}  ")

        for r in range(rounds):
            trigger = f"Chat message from @{asker}: '{q}'"
            t0 = time.perf_counter()

            events = []
            async for ev in brain.generate_response_stream(trigger):
                events.append(ev)

            latency = time.perf_counter() - t0
            complete_ev = next((e for e in events if e.get("type") == "complete"), None)
            full_text = complete_ev.get("full_text", "") if complete_ev else "No response"
            mood = complete_ev.get("mood", "neutral") if complete_ev else "neutral"

            print(f"   [{mood.upper()} | {latency:.2f}s]: \"{full_text}\"")
            round_label = f"**Run {r+1}**" if rounds > 1 else "**Response**"
            report_lines.append(f"- {round_label} (`[MOOD: {mood}]`, `{latency:.2f}s`): \"{full_text}\"")

        report_lines.append("")
        print()

    report_content = "\n".join(report_lines)
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report_content)

    print("=" * 65)
    print(f"Gauntlet complete! Report written to: {report_file}")
    print("=" * 65 + "\n")
    return str(report_file)


if __name__ == "__main__":
    asyncio.run(run_gauntlet(rounds=1))
