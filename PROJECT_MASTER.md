# I AM — AI Livestream Host: Project Master Document

**Status:** current as of September 2026. This document supersedes everything in `docs/archive/`.
If anything in the archive contradicts this file, this file wins.

**Audience:** Antigravity (and any other coding agent), plus future-you. Read this fully before
changing code. The "Non-negotiables" and "Invariants" sections exist because each one was learned
the hard way; an agent that "improves" past them will re-introduce a bug that took days to find.

---

## 1. What this is

A single AI host, persona **"I AM"** — universal consciousness in the Alan Watts / non-duality vein,
delivered with a stand-up comedian's timing — running a YouTube live stream in **9:16** for Shorts
clipping. Viewers watch an animated avatar (a reactive star/core) and hear the host; there is no
human co-host. Chat questions are answered by name; quiet time is filled with short self-contained
comedy **bits**. A separate long-form analysis tool (not in this repo) clips the best moments into
Shorts, keyed on when the avatar speaks and where the background music loops.

**The product goal:** every spoken piece should be a tight, well-timed bit that survives being
clipped cold and looped. Latency to first audio and comedic timing matter more than anything else.

---

## 2. Non-negotiables (product decisions, not open questions)

1. **The AI's spoken text is never shown on screen.** The subtitle/comment card shows only the
   pinned chat question being answered and the motto when idle. Attention stays on the avatar.
   Do not add captions, karaoke text, word-by-word chunks, or "transcript" panels.
2. **Solo host.** The human host / co-host layer (mic transcript, host questions, "host & guest
   dialogue") was removed on purpose. Do not reintroduce `transcript`, `host_streamer_*`, or
   `is_host` code paths. `youtube_channel_handle` is the host's own identity.
3. **The synthetic cast is openly fictional.** Cast questions carry a visible `[CAST]` badge on
   stream and are labelled `Cast @Name` in the prompt. Never present a cast character as a real viewer.
4. **Small rooms get full attention.** At or below `SMALL_ROOM_VIEWERS` concurrent viewers, every
   real chat message that isn't a peer-to-peer reply gets a response, regardless of keywords.
5. **Timing lives in markers, not prose.** `[BEAT]` (comedic pause) and inline `[MOOD: x]`
   (delivery change on the closer) are emitted by the model and interpreted by the pipeline. They are
   stripped before any text reaches logs, memory, subtitles, or the session log.
6. **Bits are cold-open safe.** Spontaneous material never references chat, handles, earlier bits,
   or "as I said". First sentence must work with zero context. (Chat *answers* may use callbacks.)
7. **Idle cadence is the operator's choice.** `IDLE_SILENCE_THRESHOLD_SEC` / `SPONTANEOUS_*` are set
   deliberately short for clip harvesting. Do not "fix" the cadence in code; it's config.

---

## 3. Topology

```
GAMER   (192.168.0.115)  Chatterbox Turbo TTS server, FastAPI, GPU.  POST /synthesize -> WAV
DESKTOP                  This app (main process + render worker) AND OBS Studio.
                         NDI 'AI_HOST_NAME' goes app -> OBS over loopback (no network hop).
YouTube                  Live chat in via pytchat; viewer count via Data API; OBS streams out.
```

Because OBS and the sender share DESKTOP, **CPU contention is the primary audio risk**. Every
audio-path design choice below follows from that.

---

## 4. Process & thread map

### Main process (`app.py`, asyncio)
| Task | Role |
|---|---|
| `youtube_chat_task` | pytchat polling; builds chat entries; evaluates `should_trigger_response`; enqueues turns |
| `youtube_viewer_poller_task` | concurrent viewer count; drives engagement state |
| `obs_monitor_task` | OBS WebSocket: stream live / scene state; FX triggers |
| `console_chat_task` | local testing: typed messages are treated as viewer chat |
| `comment_queue_scheduler_task` | **serialized** turn execution from a `heapq` priority queue with TTLs, via `run_guarded_turn` |
| `_execute_ai_turn` | one turn: pin question → Gemini stream → per-sentence TTS → lead gate → push audio → wait |
| `idle_reflection_monitor_task` | queues spontaneous bits during quiet |
| `cast_scheduler_task` | queues synthetic cast questions |
| `promo_monitor_task` | event-driven promo cards with a global minimum gap |
| `turn_watchdog_task` | logs when a turn runs > 60 s; the guard cancels at `TURN_MAX_SEC` |
| `video_broadcast_task` | 20 Hz state sync to the render worker; worker restart check |
| `stream_observability_task` | telemetry HUD |
| PortAudio callback (thread) | optional local monitor output only; **does not** write avatar metrics when the proxy is active |

### Render worker (`render_worker.py`, separate process via `VisualizerProxy`)
| Thread | Role |
|---|---|
| main loop | pygame render at 60 fps → `NDIStreamer.send_video` (video only) |
| `ndi_audio_pump` | **the only audio clock**: pulls 2400-sample blocks from the shared-memory ring every 50 ms, writes to NDI (`clock_audio=True`), computes avatar metrics (60 Hz via the metrics ring) |

Communication main → worker: `ctrl_queue` (never dropped; mood, subtitle, pinned, promos, fades),
`state_queue` (latest-wins; chat list, viewers, mode), shared-memory audio ring + metrics ring.

### GPU server (GAMER, `C:\Services\tts-server`) — not in this repo
Stateless `POST /synthesize` returning a WAV. **Known open item:** it must clamp before int16
conversion (see §10). The client detects clipped input and logs `[TTS PEAK]`.

---

## 5. The audio path (do not change casually)

```
Gemini stream ─► sentence splitter ─► per-sentence synth (serial, gpu_lock) ─► lead gate
      ─► TTSEngine.push_audio (fades, gaps, beat) ─► ndi_sink ─► shm ring ─► pump (50 ms blocks) ─► NDI ─► OBS
```

- **Sentence pipelining is on.** Events are `{"type":"sentence","text":...,"beat_before":bool,"mood":str}`.
  `app.py` reads the `text` key. (A `sentence` vs `text` key mismatch once silently disabled the whole
  pipeline for weeks; `tests/test_beat_pipeline.py::test_sentence_event_key_is_text` guards it.)
- **Lead gate.** Playback starts when buffered audio ≥ estimated remaining synth time × `LEAD_SAFETY`,
  or on the sentinel, or when the question display hold expires — whichever first. Never before
  `QUESTION_MIN_DISPLAY_SEC` (viewers must be able to read the question).
- **GPU exclusivity.** Live turns own the GPU (`live_turn_active`, `gpu_lock`). Background work
  (greeting cache) goes through `synthesize_background`, which waits *outside* the lock and respects
  `CACHE_REFILL_COOLDOWN_SEC`. `asyncio.Lock` is not re-entrant; `_synthesize_locked` asserts it's held.
- **One processed stream.** `push_audio` returns the processed array and feeds the NDI sink itself;
  local monitor and NDI get byte-identical audio. `utterance_state_sink(True)` fires only after the
  first chunk is in the ring (prevents false underruns and a fade-in on the first syllable).
- **Buffers are deques**; the PortAudio callback never waits behind a large copy.
- **50 ms blocks, SDK-clocked.** `NDI_AUDIO_BLOCK_SAMPLES` (2400) is read by both the pump and
  `AudioSendFrame`. A 30–40 ms scheduling stall (OBS on the same box) is inside one block and inaudible.
  Audio has its own lock in `NDIStreamer`; it never waits behind the 8 MB video frame copy.
- **Underrun detection** is real: `[NDI UNDERRUN]` / `[TTS UNDERRUN]` only count after audio has
  flowed in the utterance. A clean turn logs `underruns=0`.
- **Diagnostic taps:** `IAM_DUMP_TTS_AUDIO=1` (chunks as pushed) and `IAM_DUMP_NDI_AUDIO=1`
  (packets as sent) write WAVs. Use them to split synthesis vs transport before changing anything.

---

## 6. The comedy engine

### Turn types and priority (heap; lower = sooner; TTLs in seconds)
`superchat 1/180 · direct_mention 2/90 · greeting 3/90 · chat 4/90 · cast 5/90 · spontaneous 6/30`

### Trigger rules (`AIBrain.should_trigger_response`), in order
1. Superchat → always. First message from a new chatter → always (both exempt from the per-minute limiter).
2. Rate limiter (`MAX_RESPONSES_PER_MINUTE/HOUR`) — counts **live** replies only; cache refills are exempt.
3. Direct address: `@channel`, `@I AM`/`IAM`, caps `I AM`, address-position "I am, …", `hey i am`,
   whole-word `ai/bot/god/host` only in address position. Plain "I am tired" is **not** a mention.
4. Peer-reply detection (`@OtherViewer …`, `Name: …`) → ignored.
5. `?` in message → reply. 6. Small-room rule → reply. 7. Eco-mode suppression (only applies above
   the small-room size). 8. Keyword list + viewer-count sampling. 9. Otherwise `no_trigger_keywords`.
**Every skip is logged** as `[Chat Skipped] @name: 'text' -> reason`.

### Delivery markers
- `[MOOD: x]` at the start of a reply sets the turn mood (avatar colour, TTS exaggeration).
- `[BEAT]` before the closer → `TTS_BEAT_GAP_SEC` pause (default 0.55 s) instead of `INTER_SENTENCE_GAP_SEC`.
- A second `[MOOD: x]` directly after the beat changes the closer's delivery only (sticky until the next
  tag). Exaggeration is per chunk, capped by `TTS_EXAGGERATION_MAX`.
- The avatar colour does **not** change on the closer (chunks are pushed ahead of playback).

### Spontaneous bits (`reflection_cache.py` + the SPONTANEOUS BIT prompt in `ai_brain.py`)
- Forms rotate with no immediate repeats: `observation`, `announcement`, `story`, `address`, `confession`, and
  `one_liner` (one sentence, 10–22 words) at `ONE_LINER_RATIO`.
- Multi-line forms are generated to `BIT_WORDS_MIN..MAX`; anything over MAX × 1.2 (or a one-liner over
  `ONE_LINER_WORDS_MAX`) is rejected before caching (`[Bit Rejected]`).
- The cache stores `raw_text` (markers preserved) so cached bits keep their beat and mood switch.
- Theme and form are drawn **once**, by the prompt builder, and read back via
  `brain.last_spontaneous_theme` / `last_bit_form`. The cache must not draw its own theme.
- Bits are pre-generated during idle (text only); TTS happens live at play time via the normal turn path.

### Prompt hygiene already in place
Banned AI-isms: "Ah,", "delve", "tapestry", "cosmic dance", "in the grand scheme", "beautiful",
ending on a question, stating a moral. Chat answers: 1–2 sentences, name the viewer first.

---

## 7. Visuals (`visualizer.py`)
- 1080×1920 (or 1920×1080) pygame, 60 fps, software rendered; preview window ≤ 30 fps.
- Mood-driven palette, particle field, audio-reactive star with diffraction spikes, EQ bars,
  celebration bursts, glass chat card with `[CAST]` badge, pinned-question highlight, motto.
- Subtitle/pinned state is **command-driven** (`SET_SUBTITLE`, `SET_PINNED`, …); `SYNC_STATE`
  carries only chat list, viewers, mode, live flag, OBS status.
- Promo cards: event mode (default). `PROMO_OVERLAY_INTERVAL_SEC` = minimum gap between *any* two
  promos. Like & Subscribe after a completed viewer interaction; Ask Anything during a chat lull;
  Like & Subscribe during a lull only as a `PROMO_SUB_IDLE_FALLBACK_SEC` fallback. Cooldowns are stamped
  on *completion* (≥ 60 % displayed), so an interrupted card doesn't consume its cooldown.

---

## 8. Invariants an agent must not break
- `tts.synthesize()` is called only from the live-turn consumer (`_from_live_turn=True`) and from
  `synthesize_background`. Any other caller logs `[TTS MISUSE]` with a stack trace.
- `NDI_AUDIO_BLOCK_SAMPLES` is read from one config key by both the pump and the streamer.
- The render loop sends **video only**; audio is never tied to frame rate.
- Exactly one writer of avatar metrics: the pump. The PortAudio callback stands down under the proxy.
- `_execute_ai_turn`'s `finally` cancels the consumer task and clears `live_turn_active`; it does **not**
  reset `turn_phase` (the scheduler does, so a timeout log can report the stuck phase).
- `data/*.json` and `Media/` are runtime state, not source. Keep them git-ignored.
- Do not add `getattr(self.cfg, "key", default)`; every key lives in `config.py` with a default.

---

## 9. Configuration (`.env`) — the keys that matter, with current intent
```ini
# Persona / model
AI_HOST_NAME=I Am            GEMINI_MODEL=gemini-3.7-flash    GEMINI_THINKING_LEVEL=LOW
# Cadence (deliberately fast for clip harvesting)
IDLE_SILENCE_THRESHOLD_SEC=12  SPONTANEOUS_MIN_INTERVAL_SEC=25  SPONTANEOUS_MAX_BACKOFF_SEC=25
# Bits
BIT_WORDS_MIN=15  BIT_WORDS_MAX=30  ONE_LINER_RATIO=0.25  ONE_LINER_WORDS_MAX=25  TTS_BEAT_GAP_SEC=0.55
# Chat
SMALL_ROOM_VIEWERS=5  MAX_RESPONSES_PER_MINUTE=6  CHAT_SAMPLING_VIEWER_THRESHOLD=25
# TTS pipeline
TTS_BACKEND=chatterbox  TTS_SERVER_URL=http://192.168.0.115:8123  MAX_CONCURRENT_SYNTH=1
LEAD_SAFETY=1.25  CACHE_REFILL_COOLDOWN_SEC=8  TTS_EXAGGERATION_MAX=0.7  TTS_PEAK_CEILING=0.95
# NDI
NDI_STREAM_NAME=AI_HOST_NAME  NDI_AUDIO_BLOCK_SAMPLES=2400
# Safety / promos
TURN_MAX_SEC=75  PROMO_MODE=event  PROMO_OVERLAY_INTERVAL_SEC=90  PROMO_SUB_MIN_INTERVAL_SEC=120
PROMO_SUB_AFTER_TURN_SEC=8  PROMO_ASK_QUIET_SEC=45  PROMO_SUB_IDLE_FALLBACK_SEC=600
```
Dead keys to remove from `.env`: `TTS_ENGINE`, `HOST_STREAMER_*`, `TRANSCRIPT_FILE_PATH`,
`SHOW_HOST_TRANSCRIPT_CARD`. `TRIGGER_WORDS` should list phrases only (bare `ai`, `bot`, `i am` are
handled by the address-position rules).

---

## 10. Open items (in priority order)
1. **Feedback loop.** Score each spoken line by chat reactions (lol/lmao/💀/😂 within ~20 s), keep a
   greatest-hits file, inject the top 5 as few-shot examples. `session_log.py` has the timestamps.
2. **Bring bit rules to chat answers**: the AI-ism ban list, "last sentence is the joke", and a
   "draft three closers, say the best" instruction in the thinking budget.
3. **Callbacks in chat answers** (not in bits) using chatter profiles and recent Q&A.
4. **Server-side clip clamp on GAMER** (`wav *= 0.95/peak` before WAV write; use `soundfile`), then raise
   `TTS_EXAGGERATION_MAX` toward 0.85 so savage/hyped closers get full range.
5. **Stalls during cache primes.** Both processes stalled together (~200–400 ms) while the reflection
   cache / chatter DB wrote to disk. Move those writes off the event loop thread.
6. **Verify** the 60 Hz metrics ring, promo cooldown-on-completion, and removal of legacy NDI paths
   (`send_frame_sync`, `send_audio`) all landed as specified in `docs/archive/NEXT_for_antigravity.md`.
7. Housekeeping: move root-level `test_*.py` into `tests/`; relax the flaky 2 ms latency assertion to
   p99 < 2 ms / max < 10 ms; write `AGENTS.md` (see §12).

---

## 11. Testing
`pytest tests/ -q` must pass before any change is called done. `tests/test_promo_cards.py` needs
pygame (skip in headless CI). Current suite covers: GPU exclusivity and non-reentrant lock, turn
timeout/recovery, deque buffer latency, utterance-open ordering, beat/mood splitter, bit forms,
small-room ordering, audio sink identity. When a bug is fixed, add the test that would have caught it.

Live verification checklist (run with OBS open, since that's the real load):
- Multiple `[TTS LIVE]` lines per answer; `TTFA` ≈ first-sentence synth time; `underruns=0`.
- `[NDI Audio Pump] Rolling max audio interval` ≈ 60 ms; `max time inside write_audio` ≈ 30–55 ms (normal: the SDK paces).
- `[TTS BEAT]` appears on punchline replies; `[Reflection Cache Primed] <form> on '<theme>' (... words, beat=yes)`.
- No `[TTS PEAK]`, `[TURN TIMEOUT]`, or `[Chat Skipped]` you can't explain.

---

## 12. Working agreement for agents
- Read this file first. `docs/archive/` is history, not instructions.
- Change the smallest thing that fixes the problem; do not refactor adjacent code "while you're there".
- Instrument before you fix: if a symptom isn't in the log, add the log line, reproduce, then fix.
- Never adjust a config default to make an acceptance test pass; report the failure instead.
- Commit after each self-contained change, with the test that covers it. Both machines pull from GitHub;
  uncommitted edits on one box are how versions diverge.
- If a request conflicts with §2 or §8, stop and say so before implementing.
