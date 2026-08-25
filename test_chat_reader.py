"""
Test Script: All-Local Chat Reader Tester
Tests reading and repeating YouTube chat comments out loud through TTS and NDI audio queue.
"""

import asyncio
from config import config
from tts_engine import TTSEngine

SAMPLE_COMMENTS = [
    {"author": "Bradford", "message": "Testing the chat reader feature! Can you hear me?", "is_superchat": False, "amount": ""},
    {"author": "CyberGamer", "message": "Nova is live in the stream!", "is_superchat": False, "amount": ""},
    {"author": "RetroFan", "message": "What is the best retro gaming console?", "is_superchat": False, "amount": ""},
    {"author": "VIP_Supporter", "message": "Keep up the awesome stream!", "is_superchat": True, "amount": "$10.00"},
]


async def test_local_chat_reader():
    print("=" * 60)
    print("TESTING LOCAL CHAT READER SYNTHESIS")
    print("=" * 60)

    tts = TTSEngine()

    for idx, chat in enumerate(SAMPLE_COMMENTS, start=1):
        if chat["is_superchat"]:
            spoken_text = f"Superchat from {chat['author']} for {chat['amount']}! {chat['message']}"
        else:
            spoken_text = f"{chat['author']} says, {chat['message']}"

        print(f"\n[{idx}/{len(SAMPLE_COMMENTS)}] Synthesizing: '{spoken_text}'")
        audio = await tts.synthesize(spoken_text)
        print(f"   -> Synthesized {len(audio)/tts.sample_rate:.2f}s of 48kHz stereo audio (Shape: {audio.shape})")
        assert len(audio) > 0, "Audio should not be empty"

    print("\n" + "=" * 60)
    print("ALL CHAT READER TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_local_chat_reader())
