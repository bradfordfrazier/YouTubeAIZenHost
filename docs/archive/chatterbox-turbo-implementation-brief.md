# Implementation Brief: Networked Chatterbox Turbo TTS for AI Live Stream Co-Host

You are implementing a two-part change: a GPU-backed TTS inference server on one
machine, and a refactor of an existing audio engine on another to consume it.
Read the entire brief before writing code. Where this brief says **VERIFY**, do
not guess the API — check the upstream repository and adapt.

---

## 1. Physical setup

Two Windows 11 machines on the same 1 Gbps LAN.

**STREAMING BOX — `DESKTOP-M2EVKBV` @ 192.168.0.183**
- Intel i5-10600 (6C/12T), 16 GB RAM
- Intel UHD 630 integrated graphics only — **no CUDA, no discrete GPU**
- Runs OBS Studio 32.1.0, NDI 6 Runtime, obs-asio, RME Fireface interface
- Runs the existing Python co-host app, including `tts_engine.py`
- This machine is resource-critical. It is encoding and streaming live video.
  Anything you add here must be near-zero CPU.

**INFERENCE BOX — `GAMER` @ 192.168.0.115**
- Intel i7-14700KF (20C/28T), 32 GB DDR5-5600, NVMe
- **NVIDIA RTX 4070 SUPER, 12 GB VRAM** (Windows WMI misreports this as 4 GB —
  ignore that, confirm with `nvidia-smi`)
- NVIDIA driver 560.94 → CUDA 12.6 ceiling. Use a PyTorch cu124 or cu126 wheel.
  Do not install a wheel requiring CUDA 12.7+ without upgrading the driver first.
- Already installed: Python 3.11.9 and 3.13.0, Docker Desktop 4.52, WSL2, Git,
  Node 24, VS Build Tools 2022, eSpeak NG 1.51, NDI 6 Tools
- The operator has confirmed this machine will be **dedicated** during streams —
  no gaming, no other models on the GPU. Assume the full 12 GB is available.

---

## 2. Goal

Replace the current `edge-tts` synthesis path with **Chatterbox Turbo**
(Resemble AI, MIT licensed) served over HTTP from GAMER.

**Why:** edge-tts is a non-LLM synthesizer with no contextual understanding, so
it applies flat generic intonation regardless of meaning. Chatterbox Turbo is a
350M-parameter model with paralinguistic tags and an emotion "exaggeration"
control, quoted at ~75ms latency and ~6x real time. On a 4070 SUPER expect
roughly 3–5x real time with time-to-first-audio in the low hundreds of ms.

**Success means:** the co-host's speech carries audible emotional inflection that
varies with content, the streaming box's CPU load is unchanged from today, and a
failure on GAMER degrades gracefully instead of silencing the stream.

### Non-goals
- Do not change the NDI output path, the visualizer FFT/RMS analysis, or the
  60 fps frame-slicing logic.
- Do not change the public method signatures of `TTSEngine` (see §6).
- Do not add a GUI, a database, or authentication. This is a trusted LAN.

---

## 3. Part A — Inference server on GAMER

Build a small FastAPI service. Target layout:

```
C:\Services\tts-server\
    server.py
    requirements.txt
    voices\           # reference audio clips for voice cloning
    .venv\
    run.ps1
```

### Environment
Use **Python 3.11**, not 3.13 — the ML wheel ecosystem is more reliable there.
Create a dedicated venv. Install `chatterbox-tts`, `fastapi`, `uvicorn[standard]`,
`soundfile`, and a CUDA-matched `torch`.

**VERIFY** the exact package name, model class, checkpoint identifier, and
`generate()` signature for the **Turbo** variant against
`https://github.com/resemble-ai/chatterbox` and the Hugging Face model card
before writing inference code. The base Chatterbox API is roughly
`ChatterboxTTS.from_pretrained(device="cuda")` then `model.generate(text, ...)`
returning a torch tensor with the sample rate on `model.sr`, but Turbo is a
distinct checkpoint and may differ. Report what you find rather than assuming.

### Behavior

**Load the model once at process startup**, not per request. Run one dummy
generation during startup to warm CUDA kernels before the server reports ready.
Log VRAM occupancy after warmup.

**Serialize GPU access.** Wrap generation in an `asyncio.Lock` or a single-slot
worker queue. Concurrent generation on one card will thrash. There is exactly one
client; a queue depth of one is correct.

**Never let the model run on CPU silently.** If `torch.cuda.is_available()` is
False at startup, log a fatal error and exit non-zero. A silent CPU fallback here
would produce 30-second latencies and look like a hang.

### API contract

```
GET /health
  → 200 {"status":"ok","model":"<name>","device":"cuda","sample_rate":<int>,
         "vram_used_mb":<int>,"warm":true}
  Must respond in <50ms without touching the GPU. The client polls this.

POST /synthesize
  Request:
    {
      "text": "string, required",
      "voice": "string, optional — filename in voices/, or null for default",
      "exaggeration": 0.5,     # float, model's emotion control
      "cfg_weight": 0.5,       # float
      "format": "wav"
    }
  Response 200:
    Content-Type: audio/wav
    Body: RIFF WAV, mono, model-native sample rate, 16-bit PCM or float32
  Response 4xx/5xx:
    {"error":"...","detail":"..."} as JSON
```

Return a complete WAV with a valid header. Do not invent a custom binary
framing — the client decodes with `soundfile`, which needs a real header.

### Sentence chunking

Split incoming text into sentences server-side and generate per sentence. This
lowers time-to-first-audio and keeps each generation inside the model's
comfortable length. Two consequences you must handle:

1. **Concatenate chunks without per-chunk fades.** Apply a fade-in only to the
   first chunk and a fade-out only to the last. Fading every chunk to zero
   produces an audible amplitude dip at every sentence boundary. This is the
   single most likely source of "why does it sound like it's pulsing."
2. If a single sentence exceeds a sane character limit, split on clause
   boundaries rather than truncating.

### Streaming (second iteration, not first)

Get the blocking endpoint correct first. Then add `POST /synthesize/stream`
returning `Transfer-Encoding: chunked` with a WAV header followed by PCM frames
as each sentence completes. This is what turns "a few seconds of dead air" into
conversational timing. Do not attempt it until the blocking path passes §7.

### Windows integration
- Bind `0.0.0.0:8123`. Single uvicorn worker (`--workers 1`) — multiple workers
  would each load a copy of the model into VRAM.
- Add an inbound Windows Firewall rule for TCP 8123 scoped to the local subnet
  `192.168.0.0/24` only. Do not open it to any interface.
- Provide `run.ps1` to activate the venv and launch uvicorn, plus instructions
  for registering it as a Scheduled Task at logon. Do not auto-install the task.

---

## 4. Part B — Client refactor on the streaming box

The file is `tts_engine.py`. Read it fully before editing. Relevant existing
structure:

- `synthesize(text) -> np.ndarray` — async, returns `(n_samples, 2)` float32
- `_decode_and_resample(audio_bytes) -> np.ndarray` — runs in a worker thread via
  `asyncio.to_thread`; decodes with `soundfile`, converts mono→stereo,
  polyphase-resamples to 48 kHz, normalizes peaks, applies fades
- `queue_speech(text)` — awaits `synthesize`, vstacks into two buffers under
  `self._buffer_lock`
- `pop_audio_packet` / `pop_local_audio` / `pop_frame_samples` — called from the
  NDI and PortAudio threads at 60 fps

### Changes

**Replace the `edge_tts.Communicate` block inside `synthesize()`** with an
`aiohttp` POST to the server. Everything downstream stays: you still hand raw
bytes to `_decode_and_resample` via `asyncio.to_thread`, and that function needs
no changes — its gcd-based `resample_poly` path already handles whatever sample
rate the model returns.

**Keep edge-tts as a fallback.** On `aiohttp.ClientError`, `asyncio.TimeoutError`,
or a non-200 response, log a warning and fall through to the existing edge-tts
code path. If edge-tts also fails, fall through to `_generate_sine_placeholder`
as it does today. The stream must never go silent because GAMER rebooted.

**Use the `[MOOD: x]` tag instead of deleting it.** Line ~1 of `synthesize()`
currently regexes the mood tag out and discards it. Parse it first, map it to an
`exaggeration` value, and send that with the request. Something like
`{"excited": 0.8, "amused": 0.7, "neutral": 0.5, "thoughtful": 0.4,
"deadpan": 0.3}`, with an unknown mood defaulting to 0.5. Put the map in
`config`, not inline. This is where most of the perceived inflection improvement
actually comes from — the model swap enables it, the tag delivers it.

**Timeout policy.** Total request timeout proportional to text length, floor
~5s, ceiling ~30s. A hung request must not block the asyncio loop that drives
frame output.

**Voice selection.** Chatterbox does not have named preset voices like edge-tts —
it clones zero-shot from a reference clip. `config.tts_voice` therefore changes
meaning from a voice name to a reference filename resolved server-side. Update
the config key name and its docstring so this isn't confusing in six months.
`config.tts_pitch` and `config.tts_rate` no longer apply to this backend; leave
them in place for the edge-tts fallback and document that they are backend-specific.

### New config keys
```
tts_backend: "chatterbox" | "edge"     # default "chatterbox"
tts_server_url: "http://192.168.0.115:8123"
tts_request_timeout_floor: 5.0
tts_request_timeout_ceiling: 30.0
tts_reference_voice: "cohost.wav"
tts_exaggeration_default: 0.5
tts_mood_exaggeration_map: {...}
```

---

## 5. Startup health check

On app start, `GET /health` once. If it fails, log a clear warning naming the
server URL and set the backend to `edge` for the session rather than retrying on
every utterance. Expose the active backend in `get_audio_metrics()` so the
operator can see which path is live without reading logs mid-stream.

---

## 6. Hard constraints — do not break these

- `pop_audio_packet`, `pop_local_audio`, `pop_frame_samples`, and
  `get_audio_metrics` keep their exact current signatures and return shapes.
  Other modules call them from the NDI and PortAudio callback threads.
- All buffer mutation stays inside `with self._buffer_lock`.
- `pop_audio_packet` must remain non-blocking and allocation-light. It runs 60
  times per second on a callback thread. No network calls, no logging above
  DEBUG, no unbounded allocation inside it.
- Audio stays float32 throughout. Output to NDI stays `(2, num_samples)`
  C-contiguous.
- `samples_per_frame` stays 800 (48000 ÷ 60).
- Add no new dependencies to the streaming box beyond `aiohttp`.

---

## 7. Acceptance criteria

Verify each and report results:

1. `/health` returns 200 in under 50ms with `"warm": true`.
2. A 15-word request returns valid WAV that `soundfile` decodes without error.
3. Measured wall-clock generation time for a 10-second utterance is **under 4
   seconds** on the 4070 SUPER. If it exceeds real time, stop and investigate —
   something is on CPU.
4. Two identical requests with `exaggeration` 0.3 vs 0.8 produce audibly
   different deliveries.
5. A 4-sentence paragraph has **no audible dip or click** at sentence
   boundaries. Inspect the concatenated waveform for amplitude notches, not just
   by ear.
6. With the server stopped, the app still speaks via edge-tts and logs one
   warning — not one per utterance.
7. During a 10-minute synthesis loop, CPU usage of the Python process on the
   **streaming box** stays within noise of its edge-tts baseline. Measure before
   and after; this is the whole point of the architecture.
8. No dropped frames in the 60 fps NDI output during synthesis.

---

## 8. Notes and gotchas

- **Watermarking.** Every Chatterbox output carries Resemble's PerTh neural
  watermark, embedded at generation. Inaudible, and irrelevant for most uses, but
  the operator should know it is in the broadcast audio.
- **VRAM headroom.** Turbo at 350M should occupy 1–2 GB of 12. If you measure
  substantially more, you have loaded the wrong checkpoint — likely full
  Chatterbox rather than Turbo.
- **Do not run the first-boot model download during a live stream.** Weights pull
  from Hugging Face on first `from_pretrained`. Pre-cache it.
- **Paralinguistic tags** (`[laugh]`, `[sigh]`, `[whisper]`) are supported. The
  current regex in `synthesize()` strips `*` and backticks but leaves square
  brackets other than the mood tag alone — confirm that tags survive the cleaning
  step intact, since that cleaning was written for a backend that had no use for
  them.
- Both machines have a plaintext SMB credential in a `ResticBackup` scheduled
  task. Unrelated to this work; mention it once in your summary and move on.

---

## 9. Deliverables

1. `server.py` and `requirements.txt` with pinned versions, plus `run.ps1`.
2. Modified `tts_engine.py` with the fallback chain intact.
3. Config additions, documented.
4. A short `README.md` covering setup on GAMER, the firewall rule, how to swap
   the reference voice, and how to force the edge-tts backend for troubleshooting.
5. A results section reporting measured latency, measured VRAM, and pass/fail per
   item in §7.

Work in order: server first, verify it standalone with `curl`, then the client
refactor. Do not modify both sides simultaneously — if audio breaks you need to
know which half did it.
