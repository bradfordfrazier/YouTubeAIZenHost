# ChatterBox Turbo TTS Inference Server Setup Guide

This guide details the setup and configuration of **ChatterBox Turbo** (Resemble AI) as a dedicated GPU-accelerated Text-to-Speech (TTS) inference microservice running on **GAMER** (`192.168.0.115`) and serving the **YouTube AI Zen Host** streaming co-host app.

---

## 1. Architecture Overview

```
[ INFERENCE HOST: GAMER @ 192.168.0.115 ]
   ├── NVIDIA GeForce RTX 4070 SUPER (12 GB VRAM)
   ├── C:\Services\tts-server\
   │    ├── server.py (FastAPI on 0.0.0.0:8123)
   │    ├── voices\ (Reference audio clips, e.g. cohost.wav)
   │    └── run.ps1 (Launch script)
   └── Subnet Firewall: TCP 8123 (192.168.0.0/24 only)
                    ▲
                    │ HTTP LAN (Async POST /synthesize)
                    ▼
[ STREAMING HOST: OBS HOST PC @ 192.168.0.183 ]
   ├── YouTube AI Zen Host (app.py, tts_engine.py)
   ├── Primary: Remote ChatterBox Turbo (:8123)
   └── Failback: Local Edge-TTS (Zero-stall failover if GAMER reboots)
```

---

## 2. Directory Structure on GAMER

The inference server is housed in `C:\Services\tts-server\`:

```
C:\Services\tts-server\
├── .venv\               # Dedicated Python 3.11 virtual environment (with CUDA 12.4 PyTorch)
├── voices\              # Reference audio clips for voice cloning
│   └── cohost.wav       # Default reference voice
├── server.py            # FastAPI GPU inference server
├── requirements.txt     # Python package requirements
└── run.ps1              # Interactive launcher script
```

---

## 3. Windows Firewall Configuration

To allow the Streaming Box (`192.168.0.183` or any local LAN device) to communicate with the TTS server while restricting external exposure, run the following command in **PowerShell as Administrator** on GAMER:

```powershell
New-NetFirewallRule -DisplayName "ChatterBox Turbo TTS Server (TCP 8123)" `
    -Direction Inbound `
    -LocalPort 8123 `
    -Protocol TCP `
    -Action Allow `
    -RemoteAddress "192.168.0.0/24"
```

To verify the rule:
```powershell
Get-NetFirewallRule -DisplayName "ChatterBox Turbo TTS Server (TCP 8123)"
```

---

## 4. Starting the Inference Server

To start the server interactively:
1. Open PowerShell on GAMER.
2. Run:
   ```powershell
   cd C:\Services\tts-server
   .\run.ps1
   ```
3. The server will:
   - Check CUDA availability on the RTX 4070 SUPER.
   - Load the ChatterBox Turbo model.
   - Run a warmup generation to pre-compile CUDA kernels.
   - Begin listening on `http://0.0.0.0:8123`.

### (Optional) Register as a Windows Scheduled Task at Logon
To run the server silently in the background whenever GAMER logs on:
```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File C:\Services\tts-server\run.ps1"
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "ChatterBoxTurboTTS" -Action $action -Trigger $trigger -Description "ChatterBox Turbo TTS GPU Inference Server"
```

---

## 5. Reference Voice Customization & Pure Oracle (VCTK) Voices

ChatterBox Turbo supports zero-shot voice cloning using clean reference audio clips or built-in VCTK speaker recipes.

### Pure Oracle & Androgynous Transcendent Tone Targets
To achieve an **Androgynous Transcendent Tone (Pure Oracle)**—characterized by neutral fundamental pitch (~145–170 Hz), flat emotional cadence, smooth articulation, and absence of heavy chest resonance or high-register breathiness—the server includes automatic resolution for these targeted speakers:

| Voice Name / Alias | Description & Profile | Pitch / Register |
| :--- | :--- | :--- |
| `pure_oracle` / `oracle` | **Pure Oracle**: Disembodied androgynous cadence, flat spiritual authority | ~155 Hz, zero inflection |
| `p248` / `p248.wav` | **Speaker p248** (Female, Neutral English): Lower pitch register, crisp steady transitions | ~150 Hz, steady |
| `p308` / `p308.wav` | **Speaker p308** (Female, Southern British / RP): Flat, formal pitch contours | ~165 Hz, formal |
| `p361` / `p361.wav` | **Speaker p361** (American / Neutral): Clear, dry mid-frequency articulation | ~155 Hz, dry |
| `p374` / `p374.wav` | **Speaker p374** (American / Neutral): Minimal dynamic fluctuation, steady cadence | ~150 Hz, minimal swing |

### Automatic On-Demand Voice Downloading
If a requested voice (e.g. `TTS_REFERENCE_VOICE=pure_oracle.wav` or `TTS_REFERENCE_VOICE=p248.wav`) does not exist locally on GAMER in `C:\Services\tts-server\voices\`:
1. The server's `voice_manager.py` automatically downloads or synthesizes the calibrated reference passage (the standardized Rainbow Passage or Speech Accent Archive Stella Paragraph).
2. The reference clip is cached in `C:\Services\tts-server\voices\` and condition-cached for sub-second inference.

### Configuring in `.env`
In `D:\Dev\YouTubeAIZenHost\.env` on the OBS PC (or locally on GAMER):
```env
# Choose between 'pure_oracle.wav', 'p248.wav', 'p308.wav', 'p361.wav', 'p374.wav', or 'cohost.wav'
TTS_REFERENCE_VOICE=pure_oracle.wav
```

---

## 6. Testing & Verifying the Setup

### Test 1: Health Check Endpoint
From PowerShell on GAMER or the Streaming Box:
```powershell
curl http://192.168.0.115:8123/health
```
**Expected Response (<50ms):**
```json
{
  "status": "ok",
  "model": "chatterbox-turbo",
  "device": "cuda",
  "sample_rate": 24000,
  "vram_used_mb": 1250,
  "warm": true
}
```

### Test 2: Synthesis Endpoint
```powershell
$body = @{
    text = "Hello world! This is ChatterBox Turbo running on the RTX 4070 SUPER."
    voice = "cohost.wav"
    exaggeration = 0.6
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://192.168.0.115:8123/synthesize" -Method Post -ContentType "application/json" -Body $body -OutFile "test_output.wav"
```

---

## 7. Client Configuration & Fallback Troubleshooting

In `c:\Users\bradf\Dev\YouTubeAIZenHost\.env`:
```env
# Primary backend ('chatterbox' for GPU server, 'edge' for local Edge-TTS)
TTS_BACKEND=chatterbox
TTS_SERVER_URL=http://192.168.0.115:8123
TTS_REFERENCE_VOICE=cohost.wav
TTS_REQUEST_TIMEOUT_FLOOR=5.0
TTS_REQUEST_TIMEOUT_CEILING=30.0
TTS_EXAGGERATION_DEFAULT=0.5
```

### Automatic Fallback Behavior:
- When `TTS_BACKEND=chatterbox` is active, the app queries `GET /health` during startup.
- If the server on GAMER is offline, unresolvable, or times out, the app will log a single notification and **automatically fall back to local `edge-tts`**.
- The stream will **never go silent** due to server disconnects.

### Forcing Local Edge-TTS for Testing:
To force the app to run completely on the local OBS host without attempting to reach GAMER, set:
```env
TTS_BACKEND=edge
```
