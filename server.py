"""
ChatterBox Turbo GPU Inference Microservice for Live Streaming.
Runs on dedicated GPU machine (GAMER @ 192.168.0.115) on RTX 4070 SUPER.
Provides /synthesize and /health endpoints with sub-50ms monitoring.
Includes automatic reference voice resolution, auto-downloading, and Pure Oracle VCTK targets.
"""

import asyncio
import io
import logging
import os
import re
import time
from pathlib import Path
from typing import List, Optional

import numpy as np
import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI, HTTPException, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from voice_manager import ensure_voice_available, get_available_voices
from logging_setup import configure_logging

configure_logging("SERVER")
logger = logging.getLogger("chatterbox_server")

# Strict directory paths
BASE_DIR = Path(__file__).parent.resolve()
VOICES_DIR = BASE_DIR / "voices"
VOICES_DIR.mkdir(parents=True, exist_ok=True)

# GPU Lock: strictly 1 inference at a time (queue depth = 1)
gpu_lock = asyncio.Lock()

# Global model container
tts_model = None
SAMPLE_RATE = 24000  # ChatterBox Turbo native rate


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000, description="Text to synthesize")
    voice: Optional[str] = Field(
        default="cohost.wav",
        description="Reference voice filename, speaker ID (e.g. p248, p308, p361, p374), or alias (oracle, pure_oracle)",
    )
    exaggeration: Optional[float] = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Emotion exaggeration factor (0.0 to 1.0)",
    )


app = FastAPI(
    title="ChatterBox Turbo TTS Inference Server",
    description="GPU-accelerated text-to-speech inference service for live stream co-hosting.",
    version="1.1.0",
)


@app.on_event("startup")
async def startup_event():
    """Validates CUDA, initializes ChatterBox Turbo, ensures default voices, and runs kernel warmup."""
    global tts_model

    logger.info("=" * 60)
    logger.info("INITIALIZING CHATTERBOX TURBO INFERENCE SERVER ON GAMER")
    logger.info("=" * 60)

    # 1. Validate CUDA availability
    if not torch.cuda.is_available():
        error_msg = "FATAL: CUDA is NOT available! ChatterBox Turbo requires a dedicated NVIDIA GPU."
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    device_name = torch.cuda.get_device_name(0)
    logger.info(f"Using GPU: {device_name} (CUDA Version: {torch.version.cuda})")

    # 2. Pre-cache & ensure Pure Oracle default voices
    logger.info("Verifying reference voices...")
    for vname in ["cohost.wav", "pure_oracle.wav", "p248.wav", "p308.wav", "p361.wav", "p374.wav"]:
        await ensure_voice_available(vname)
    logger.info(f"Available reference voices: {get_available_voices()}")

    # 3. Load ChatterBox Turbo model
    try:
        from chatterbox import ChatterboxTTS
        logger.info("Loading ChatterBox Turbo model checkpoint onto CUDA...")
        t0 = time.perf_counter()
        tts_model = ChatterboxTTS.from_pretrained(device="cuda")
        logger.info(f"Model loaded successfully in {time.perf_counter() - t0:.2f}s!")
    except Exception as e:
        logger.error(f"Failed to load ChatterBox model: {e}", exc_info=True)
        raise RuntimeError(f"ChatterBox initialization error: {e}")

    # 4. Warm up CUDA kernels with short synthesis
    logger.info("Warming up CUDA inference pipeline...")
    try:
        sample_voice = VOICES_DIR / "pure_oracle.wav"
        if not sample_voice.exists():
            sample_voice = VOICES_DIR / "cohost.wav"
        
        warmup_audio = tts_model.generate(
            "System online and operational.",
            audio_prompt_path=str(sample_voice) if sample_voice.exists() else None,
            exaggeration=0.5,
        )
        logger.info(f"Warmup successful! Output tensor shape: {warmup_audio.shape}")
    except Exception as e:
        logger.warning(f"Warmup generation note: {e}")

    logger.info("ChatterBox Turbo inference server is ready to accept requests on port 8123.")


@app.get("/health")
async def health():
    """
    Lightweight health check endpoint.
    Must respond in <50ms without acquiring GPU lock so streaming client never stalls.
    """
    vram_mb = int(torch.cuda.memory_allocated() / (1024 * 1024)) if torch.cuda.is_available() else 0
    return {
        "status": "ok",
        "model": "chatterbox-turbo",
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "sample_rate": SAMPLE_RATE,
        "vram_used_mb": vram_mb,
        "warm": tts_model is not None,
        "available_voices": get_available_voices(),
    }


def chunk_text_by_sentence(text: str) -> List[str]:
    """Splits long text into sentence chunks for stable autoregressive generation."""
    chunks = re.split(r"(?<=[.!?])\s+", text.strip())
    return [c.strip() for c in chunks if c.strip()]


@app.post("/synthesize")
async def synthesize(req: SynthesizeRequest):
    """
    Synthesizes speech from text using ChatterBox Turbo on CUDA.
    Resolves reference voice (auto-downloading/extracting if missing) and returns 24kHz Mono RIFF WAV bytes.
    """
    global tts_model
    if tts_model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ChatterBox model is not loaded.",
        )

    t0 = time.perf_counter()
    clean_text = req.text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    # 1. Resolve reference voice path (auto-download/generate if not yet cached)
    voice_path = await ensure_voice_available(req.voice)
    voice_str = str(voice_path) if voice_path.exists() else None

    # 2. Acquire GPU inference lock (strict single-slot queue)
    async with gpu_lock:
        try:
            chunks = chunk_text_by_sentence(clean_text)
            if not chunks:
                chunks = [clean_text]

            chunk_audios = []
            num_chunks = len(chunks)

            for idx, chunk in enumerate(chunks):
                # Run synchronous GPU inference in executor thread to keep FastAPI event loop free
                loop = asyncio.get_running_loop()

                def _infer():
                    return tts_model.generate(
                        chunk,
                        audio_prompt_path=voice_str,
                        exaggeration=req.exaggeration or 0.5,
                    )

                audio_tensor = await loop.run_in_executor(None, _infer)

                # Convert torch tensor (1, N) or (N,) to 1D float32 numpy array
                if hasattr(audio_tensor, "detach"):
                    audio_np = audio_tensor.detach().cpu().numpy().squeeze()
                else:
                    audio_np = np.asarray(audio_tensor, dtype=np.float32).squeeze()

                # Boundary Dip Elimination: Apply fade-in only on chunk 0, fade-out only on last chunk
                fade_len = min(120, len(audio_np) // 4)  # 5ms @ 24kHz = 120 samples
                if fade_len > 0:
                    if idx == 0:
                        audio_np[:fade_len] *= np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
                    if idx == num_chunks - 1:
                        audio_np[-fade_len:] *= np.linspace(1.0, 0.0, fade_len, dtype=np.float32)

                chunk_audios.append(audio_np)

            # Concatenate chunks without boundary dip pulses
            if len(chunk_audios) == 1:
                final_audio = chunk_audios[0]
            else:
                final_audio = np.concatenate(chunk_audios)

            # Peak normalization
            max_amp = float(np.max(np.abs(final_audio))) if len(final_audio) > 0 else 0.0
            if max_amp > 0.95:
                final_audio = (final_audio / max_amp) * 0.90

            # Encode to standard 24kHz 16-bit PCM RIFF WAV in memory
            wav_io = io.BytesIO()
            sf.write(wav_io, final_audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
            wav_bytes = wav_io.getvalue()

            dur = len(final_audio) / SAMPLE_RATE
            elapsed = time.perf_counter() - t0
            rtf = dur / max(0.001, elapsed)
            logger.info(
                f"Synthesized '{clean_text[:45]}...' ({dur:.2f}s audio with voice='{voice_path.name}' "
                f"in {elapsed:.2f}s, {rtf:.1f}x real-time)"
            )

            return Response(
                content=wav_bytes,
                media_type="audio/wav",
                headers={
                    "Content-Disposition": 'attachment; filename="synthesis.wav"',
                    "X-Audio-Duration": f"{dur:.3f}",
                    "X-Audio-SampleRate": f"{SAMPLE_RATE}",
                    "X-Voice-Used": voice_path.name,
                },
            )

        except Exception as e:
            logger.error(f"Inference error: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Inference failed: {e}",
            )


if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8123,
        workers=1,
        log_level="info",
    )
