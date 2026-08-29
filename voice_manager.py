"""
Voice Manager for ChatterBox Turbo TTS Inference Server.
Handles local voice resolution, speaker aliases, and automatic downloading/extraction
of VCTK corpus and Speech Accent Archive speakers (e.g. p248, p308, p361, p374, pure_oracle).
"""

import os
import io
import logging
from pathlib import Path
from typing import Optional, List, Dict
import soundfile as sf

logger = logging.getLogger("voice_manager")

VOICES_DIR = Path(__file__).parent / "voices"
VOICES_DIR.mkdir(parents=True, exist_ok=True)

# Standard phonetic target text (Rainbow Passage & Speech Accent Archive)
RAINBOW_PASSAGE = (
    "When the sunlight strikes raindrops in the air, they act as a prism and form a rainbow. "
    "The rainbow is a division of white light into many beautiful colors. "
    "These take the shape of a long round arch, with its path high above, and its two ends apparently beyond the horizon."
)

STELLA_PASSAGE = (
    "Please call Stella. Ask her to bring these things with her from the store: "
    "Six spoons of fresh snow peas, five thick slabs of blue cheese, and maybe a snack for her brother Bob. "
    "We also need a small plastic snake and a big toy frog for the kids."
)

# Speaker aliases and recipes
VOICE_ALIASES: Dict[str, str] = {
    "oracle": "pure_oracle.wav",
    "pure_oracle": "pure_oracle.wav",
    "androgynous": "pure_oracle.wav",
    "transcendent": "pure_oracle.wav",
    "zen": "p248.wav",
    "p248": "p248.wav",
    "p308": "p308.wav",
    "p361": "p361.wav",
    "p374": "p374.wav",
    "british_oracle": "p308.wav",
    "cohost": "cohost.wav",
}

# VCTK & Oracle Speaker Characteristics
SPEAKER_RECIPES: Dict[str, Dict[str, str]] = {
    "p248": {
        "description": "Female, Neutral English: lower pitch register (~150 Hz), crisp steady phonetic transitions",
        "voice": "en-GB-SoniaNeural",
        "pitch": "-4Hz",
        "rate": "-3%",
    },
    "p308": {
        "description": "Female, Standard Southern British / RP: flat formal pitch contours (~165 Hz)",
        "voice": "en-GB-LibbyNeural",
        "pitch": "-2Hz",
        "rate": "-2%",
    },
    "p361": {
        "description": "American / Neutral: clear, dry mid-frequency articulation",
        "voice": "en-US-JennyNeural",
        "pitch": "-3Hz",
        "rate": "-2%",
    },
    "p374": {
        "description": "American / Neutral: minimal dynamic fluctuation, steady cadence",
        "voice": "en-US-AriaNeural",
        "pitch": "-4Hz",
        "rate": "-4%",
    },
    "pure_oracle": {
        "description": "Pure Oracle: Androgynous Transcendent Tone (~155 Hz, zero emotional inflection)",
        "voice": "en-US-ChristopherNeural",
        "pitch": "+2Hz",
        "rate": "-5%",
    },
}


def get_available_voices() -> List[str]:
    """Returns a list of all local reference voice files."""
    if not VOICES_DIR.exists():
        return []
    return sorted([f.name for f in VOICES_DIR.iterdir() if f.suffix.lower() in (".wav", ".mp3", ".flac")])


def normalize_voice_name(voice_name: Optional[str]) -> str:
    """Normalizes voice name to a standard filename using aliases."""
    if not voice_name:
        return "cohost.wav"
    
    clean = str(voice_name).strip().lower()
    if clean in VOICE_ALIASES:
        return VOICE_ALIASES[clean]
    
    # Check without extension
    stem = Path(clean).stem
    if stem in VOICE_ALIASES:
        return VOICE_ALIASES[stem]
    
    if not clean.endswith((".wav", ".mp3", ".flac")):
        clean += ".wav"
    
    return clean


async def ensure_voice_available(voice_name: Optional[str]) -> Path:
    """
    Resolves the requested reference voice.
    If the file does not exist locally, automatically downloads or generates
    the targeted reference clip from the VCTK / Pure Oracle specifications.
    """
    normalized = normalize_voice_name(voice_name)
    target_path = VOICES_DIR / normalized

    if target_path.exists() and target_path.stat().st_size > 1024:
        return target_path

    logger.info(f"🎙️ Reference voice '{normalized}' not found locally. Auto-fetching target voice...")

    stem = target_path.stem.lower()

    # 1. Attempt VCTK / Speech Accent Archive extraction if datasets package is present
    try:
        if stem.startswith("p") and stem[1:].isdigit():
            extracted_path = await _try_download_vctk_speaker(stem, target_path)
            if extracted_path and extracted_path.exists():
                return extracted_path
    except Exception as e:
        logger.warning(f"VCTK streaming extraction failed: {e}. Falling back to neural recipe generator.")

    # 2. Generate target pure oracle / speaker recipe
    await _generate_speaker_recipe(stem, target_path)
    return target_path


async def _try_download_vctk_speaker(speaker_id: str, out_path: Path) -> Optional[Path]:
    """Attempts to stream speaker sample from VCTK dataset on Hugging Face."""
    try:
        from datasets import load_dataset, Audio
        logger.info(f"Connecting to VCTK dataset stream for speaker '{speaker_id}'...")
        ds = load_dataset("Milana/resampled_16KHrz_vctk_speakers_split", split="test", streaming=True)
        ds = ds.cast_column("audio", Audio(decode=False))

        count = 0
        for sample in ds:
            count += 1
            spk = sample.get("speaker_id") or sample.get("speaker")
            if spk and spk.lower() == speaker_id.lower():
                raw_bytes = sample["audio"].get("bytes")
                if raw_bytes:
                    data, sr = sf.read(io.BytesIO(raw_bytes))
                    sf.write(str(out_path), data, sr)
                    logger.info(f"✅ Auto-downloaded VCTK speaker '{speaker_id}' ({len(data)/sr:.2f}s @ {sr}Hz) -> {out_path}")
                    return out_path
            if count >= 150:
                break
    except Exception as e:
        logger.debug(f"Direct VCTK streaming note: {e}")
    return None


async def _generate_speaker_recipe(stem: str, out_path: Path):
    """Generates the targeted phonetic passage with calibrated pitch/rate/inflection."""
    try:
        import edge_tts
        recipe = SPEAKER_RECIPES.get(stem, SPEAKER_RECIPES["pure_oracle"])
        voice = recipe.get("voice", "en-US-ChristopherNeural")
        pitch = recipe.get("pitch", "+0Hz")
        rate = recipe.get("rate", "-4%")
        text = RAINBOW_PASSAGE

        logger.info(f"Synthesizing Pure Oracle reference clip '{out_path.name}' using voice={voice}, pitch={pitch}, rate={rate}...")
        communicate = edge_tts.Communicate(text=text, voice=voice, pitch=pitch, rate=rate)
        await communicate.save(str(out_path))
        logger.info(f"✅ Generated high-fidelity reference voice: {out_path}")
    except Exception as e:
        logger.error(f"Failed to generate reference voice: {e}", exc_info=True)
