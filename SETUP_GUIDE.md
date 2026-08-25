# All-Local Live Stream AI Co-Host Setup Guide

Complete step-by-step setup guide for running the AI Co-Host pipeline solely on the OBS host machine.

---

## 1. System Requirements

* **Operating System**: Windows 10 / 11 (64-bit)
* **Python**: Python 3.10+ (64-bit)
* **Audio & Video Capture**:
  * **Option A (Windows OBS Source)**: Native Windows Window Capture / Game Capture + Application Audio Capture (built into OBS 28+).
  * **Option B (NDI Source)**: NDI 6 Core Runtime / NDI Tools with the **DistroAV** (formerly OBS-NDI) plugin.

---

## 2. Installation & Dependencies

1. Open Windows PowerShell or Command Prompt in the repository directory:
   ```bash
   cd c:\Users\bradf\Dev\YouTubeAIZenHost
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

---

## 3. Configuration (`.env`)

Copy `.env.example` to `.env` (or edit existing `.env`):
```env
# 1. OBS Studio Settings
OBS_WS_HOST=localhost
OBS_WS_PORT=4455
OBS_WS_PASSWORD=
OBS_TRANSCRIPT_SOURCE="Guest Transcript"

# 2. Streamer Identity & YouTube Live
HOST_STREAMER_NAME=Massive
HOST_STREAMER_HANDLE=@MassiveGodComplex
YOUTUBE_CHANNEL_HANDLE=@MassiveGodComplex
YOUTUBE_API_KEY=your_youtube_api_key_here
YOUTUBE_VIDEO_ID=

# 3. Google Gemini API
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
AI_COHOST_NAME=I Am

# 4. Neural TTS Voice
TTS_VOICE=en-US-ChristopherNeural

# 5. Visualizer & Display
VISUALIZER_ASPECT_RATIO=16:9
VISUALIZER_WIDTH=1920
VISUALIZER_HEIGHT=1080
VISUALIZER_FPS=60
VISUALIZER_HEADLESS=false

# 6. Windows Audio & NDI Settings
LOCAL_AUDIO_ENABLED=true
LOCAL_AUDIO_VOLUME=1.0
NDI_STREAM_NAME=AI_COHOST_FEED
```

---

## 4. OBS Studio Configuration (Choose Either or Both)

### Method 1: Windows OBS Source (Window Capture + Application Audio)
This method requires no NDI plugins and captures the visualizer window and audio directly through Windows:
1. In OBS Studio, click **+ (Add Source)** -> **Window Capture**.
2. Set **Window** to `[python.exe]: AI Co-Host Broadcast Visualizer...`.
3. In Window Capture properties, check **"Capture Audio (BETA)"** OR add an **"Application Audio Capture (BETA)"** source pointing to `python.exe`.
4. In OBS Audio Mixer, the AI Co-Host's voice will appear as an independent volume slider with full 48kHz stereo fidelity.

### Method 2: NDI Source (DistroAV / OBS-NDI)
1. In OBS Studio, click **+ (Add Source)** -> **NDI Source**.
2. Select **`AI_COHOST_FEED`** -> Bandwidth: `Highest` -> Latency: `Low (real-time)`.
3. In Audio Mixer gear icon -> **Advanced Audio Properties**, set `AI_COHOST_FEED` monitoring to **Monitor and Output**.

### Speech-to-Text Transcription Setup:
1. In OBS Studio, open **Tools** -> **WebSocket Server Settings**, verify server is enabled on port `4455`.
2. Add the **LocalVocal (Speech-to-Text)** audio filter to your microphone source in OBS.
3. Set the output target to an **OBS Text (GDI+) Source** named `"Guest Transcript"`.

---

## 5. Starting the AI Co-Host

Run the unified application directly:
```bash
python app.py
```

### Optional Launch Flags:
* **Vertical 9:16 Mode (YouTube Shorts / Mobile Live)**:
  ```bash
  python app.py --vertical
  ```
* **Offscreen Headless Mode**:
  ```bash
  python app.py --headless
  ```
* **Simulated Stream Chat Mode**:
  ```bash
  python app.py --mock-chat
  ```
* **Disable Local Windows Audio Output (NDI Audio Only)**:
  ```bash
  python app.py --no-local-audio
  ```

---

## 6. Interactive Console Commands

While `app.py` is running, you can type directly into the terminal to interact with the AI Co-Host:
* `Host: What do you think, Nova?` -> Triggers direct question response.
* `Host: Celebrate!` -> Triggers celestial celebration animation and hype voice.
* `viewers: 15` -> Overrides concurrent viewer count to test engagement modes.
* `sub: CosmicGamer` -> Simulates a new subscriber alert.
* `member: Alice` -> Simulates a new channel member alert.
