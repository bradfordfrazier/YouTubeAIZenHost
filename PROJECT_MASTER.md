# I AM — AI Livestream Host: Project Master Document

**Verified against the running code on 8 September 2026.** Every fact below was checked against
the actual modules, not remembered. This supersedes everything in `docs/archive/`.

**Audience:** Antigravity, any other coding agent, and future-you. Read this before changing code.
Sections 2 and 8 exist because each item was learned by breaking the live stream.

---

## 1. What this is

A single AI host, persona **"I AM"** — universal consciousness in the Alan Watts vein with a
stand-up comedian's timing — running a YouTube live stream in **9:16** for Shorts clipping. Viewers
watch a reactive star/core avatar and hear the host. Chat questions are answered by name; quiet time
is filled with short self-contained comedy **bits**. A separate long-form tool (not in this repo)
clips the best moments into Shorts, keyed on when the avatar speaks and where the music loops.

**The product goal:** every spoken piece should be a tight, well-timed bit that survives being
clipped cold and looped. Comedic timing and time-to-first-audio matter more than anything else.

---

## 2. Non-negotiables (product decisions, not open questions)

1. **The AI's spoken text is never shown on screen.** The subtitle card shows only the pinned chat
   question and the motto. Attention stays on the avatar. No captions, no karaoke text.
2. **Solo host.** The human co-host layer was removed deliberately. Do not reintroduce
   `transcript`, `host_streamer_*`, or `is_host` paths.
3. **The cast is openly fictional.** Cast questions carry a visible `[CAST]` badge and are labelled
   `Cast @Name` in the prompt. Never present a cast character as a real viewer.
4. **Small rooms get full attention.** At or below `SMALL_ROOM_VIEWERS`, every real chat message
   that is not a peer reply gets a response, regardless of keywords.
5. **Bits are cold-open safe.** Spontaneous material never references chat, handles, or earlier
   bits. Chat *answers* may use callbacks; bits may not.
6. **Say "I", never "we".** I AM is not a member of a group; it is the single thing wearing all the
   bodies. "We all…" is the pastoral voice and reads as condescension. See §6.
7. **Never judge the audience.** The bit is "look what I did again", never "look what you people do".
8. **Idle cadence is the operator's choice.** The `.env` timing values are tuned for clip
   harvesting. Do not "fix" cadence in code.

---

## 3. Topology

```
GAMER   192.168.0.115   Chatterbox Turbo TTS server (C:\Services\tts-server), RTX 4070 SUPER.
                        POST /synthesize -> WAV 24 kHz. voice_manager.py lives here.
DESKTOP                 This app (main process + render worker) AND OBS Studio.
                        NDI 'AI_HOST_NAME' goes app -> OBS over loopback (no network hop).
YouTube                 Chat in via pytchat; viewer count via YouTube Data API v3; OBS streams out.
```

Because OBS and the NDI sender share DESKTOP, **CPU contention is the primary audio risk**. Every
audio design choice in §5 follows from that.

---

## 4. Modules

| File | Role |
|---|---|
| `app.py` | Orchestrator: ~12 asyncio tasks, the serialized turn scheduler, chat ingestion |
| `ai_brain.py` | Gemini client, prompt construction, bit forms, trigger rules, favourites, reactions |
| `cast_engine.py` | 18 synthetic personas, 234 questions, rotation + per-session cap |
| `tts_engine.py` | Chatterbox HTTP client, deque audio buffers, fades, beat gaps, GPU exclusivity |
| `render_worker.py` | Separate process: pygame render loop + the NDI audio pump + shared memory |
| `ndi_streamer.py` | cyndilib wrapper; separate audio/video locks; 50 ms SDK-clocked audio blocks |
| `visualizer.py` | 1080×1920 pygame scene, chat card, promo cards, mixed-font emoji rendering |
| `emoji_text.py` | Shortcode → emoji normalization and emoji-font compositing |
| `reflection_cache.py` | 4-slot pre-generated bit cache (text only) |
| `greeting_cache.py` | 3-slot pre-synthesized welcome cache (text + audio) |
| `chatter_db.py` | Persistent viewer/cast profiles; roster derived from `cast_engine` |
| `memory_manager.py` | Canonical rulings, channel lore, cross-session continuity |
| `session_log.py` | JSONL of every turn, chat message, and cast question |
| `turn_guard.py` | `run_guarded_turn()` — hard timeout wrapper for one turn |
| `logging_setup.py` | Single logging configuration for both processes |
| `voice_manager.py` | **On GAMER.** Reference-clip resolution, PCM repair, sentence trimming |
| `bit_lab.py` | Offline A/B harness for bit quality (see §11) |
| `config.py` | Every setting, with defaults |

---

## 5. The audio path (do not change casually)

```
Gemini stream → sentence splitter → per-sentence synth (serial, gpu_lock) → lead gate
   → TTSEngine.push_audio (fades, gaps, beat) → ndi_sink → shm ring → pump (50 ms) → NDI → OBS
```

- **Sentence pipelining is on.** Events are `{"type":"sentence","text":…,"beat_before":bool,"mood":str}`.
  `app.py` reads the `text` key. A `sentence`/`text` key mismatch once disabled the whole pipeline
  silently; `tests/test_beat_pipeline.py` guards it.
- **Lead gate.** Playback starts when buffered audio ≥ estimated remaining synth × `LEAD_SAFETY`,
  or on the sentinel, or when the question hold expires — whichever is first.
- **GPU exclusivity.** Live turns own the GPU (`live_turn_active`, `gpu_lock`). Background work uses
  `synthesize_background`, which waits *outside* the lock. `asyncio.Lock` is not re-entrant.
- **One processed stream.** `push_audio` returns the processed array and feeds the NDI sink itself,
  so the local monitor and NDI get identical audio.
- **50 ms SDK-clocked blocks.** `NDI_AUDIO_BLOCK_SAMPLES` (2400) is read by both the pump and
  `AudioSendFrame`. Audio has its own lock in `NDIStreamer`; it never waits behind the 8 MB frame
  copy. A 30–40 ms scheduling stall from OBS is inside one block and inaudible.
- **The render loop sends video only.** Audio is never tied to frame rate.
- **Diagnostic taps:** `IAM_DUMP_TTS_AUDIO=1` and `IAM_DUMP_NDI_AUDIO=1` write WAVs. Use them to
  split synthesis from transport before changing anything.

---

## 6. The comedy engine

### Turn priority (heap; lower is sooner)
`superchat 1 · direct_mention 2 · greeting 3 · chat 4 · cast 5 · spontaneous 6`

### Trigger rules (`should_trigger_response`), in order
1. **Reaction-only** messages ("lmao", "😂", "ok", "bruh") → scored, never answered.
2. Superchat → always. First message from a new chatter → always. Both bypass the rate limiter.
3. Rate limiter — counts **live** replies only; cache refills are exempt.
4. Direct address: `@channel`, `@I AM`, caps `I AM`, address-position "I am, …". Plain "I am tired"
   does **not** match.
5. Peer-reply detection → ignored.
6. `?` in message → reply. 7. Small-room rule → reply. 8. Eco suppression (only above small-room
   size). 9. Keywords + viewer sampling. 10. Otherwise `no_trigger_keywords`.
**Every skip is logged** as `[Chat Skipped] @name: 'text' -> reason`.

### Bit forms (`BIT_FORMS`)
`observation`, `announcement`, `story`, `address`, `one_liner`. Only `one_liner` has a configured
share (`ONE_LINER_RATIO`); the rest rotate evenly with no immediate repeats.

**Retired, do not reintroduce:** `confession` (first person "I have done this in eight billion
bodies" — consistently read as abstract and esoteric) and `structure` (handing the model an abstract
shape produced textbook examples; A/B-tested and clearly worse).

### Bit quality rules (all forms)
- 10–25 words, 2–3 sentences, drawn from a 112-entry theme deck (`CONCRETE ANCHOR — non-dual angle`).
- **Closer must stay concrete**: no abstract nouns in the final sentence. Overreach is always an
  abstract noun in the last line.
- **Banned images**: the genre's stock metaphors (ocean/wave, mirror, dream, hologram…).
  *The operator has deliberately loosened both lists; over-banning strips out the jokes non-dualists
  enjoy most. Treat their contents as the operator's call, not a rule to tighten.*
- **Drafting rejects, not prefers**: five-point checklist, keep drafting until one survives.
- Generated **offline** into a 4-slot cache with `BIT_THINKING_BUDGET` / `BIT_TEMPERATURE`, so extra
  reasoning costs no stream latency.
- Over-length bits are rejected before caching (`[Bit Rejected]`).

### Delivery markers
- `[MOOD: x]` at the start sets the turn mood (avatar colour, TTS exaggeration, cfg_weight).
- `[BEAT]` before the closer → `TTS_BEAT_GAP_SEC` ± `TTS_BEAT_GAP_JITTER` (jitter stops it becoming
  a metronome). **Earned, not default** — it only works when the closer *reverses* the setup.
- A second `[MOOD: x]` after the beat changes the closer's delivery only.
- Markers are stripped before text reaches logs, memory, subtitles, or the session log.

### Feedback loop
Every chat message is scored for laughter against the line that just aired (`REACTION_WINDOW_SEC`,
decaying with time). Lines crossing `REACTION_PROMOTE_SCORE` are auto-saved to
`data/favorite_bits.jsonl` and become few-shot exemplars. This is the only mechanism that learns
what *this* audience finds funny; everything else is a guess encoded as a rule.

---

## 7. Visuals
- 1080×1920 pygame at 60 fps in a separate process; preview window ≤ 30 fps.
- Mood palette, particle field, audio-reactive star, EQ bars, celebrations, glass chat card with
  `[CAST]` badge, pinned question, motto.
- **Emoji**: pytchat sends `:shortcode:` text; `emoji_text.normalize_chat_text()` converts it at
  ingestion so the prompt, chat card and chatter DB all get real emoji. `_render_text` composites
  emoji runs using a dedicated emoji font (`Segoe UI Emoji` on Windows), scaling them to the line
  height. `font.metrics()` cannot detect missing glyphs — a colour emoji font reports `None` for
  characters it renders fine — so detection compares rendered pixels against `\uFFFF`.
- Subtitle and pinned state are **command-driven**; `SYNC_STATE` carries only chat list, viewers,
  mode, live flag, OBS status.
- Promos are event-driven. `PROMO_OVERLAY_INTERVAL_SEC` is the minimum gap between *any* two promos.

---

## 8. Invariants an agent must not break
- `tts.synthesize()` is called only from the live-turn consumer (`_from_live_turn=True`) and from
  `synthesize_background`. Anything else logs `[TTS MISUSE]` with a stack trace.
- `NDI_AUDIO_BLOCK_SAMPLES` is read from one config key by both the pump and the streamer.
- The render loop sends **video only**. Exactly one writer of avatar metrics: the pump.
- `_execute_ai_turn`'s speech bookkeeping is gated on `pushed_chunks > 0 and clean_speech`; that
  `if` **must** keep its `else`, or a degenerate turn leaves the motto unset forever.
- `_build_context_prompt` must assign `is_spontaneous` before the anti-repetition block reads it.
- Keywords `app.py` passes to `generate_response_stream` must exist in the brain's signature.
- **"Unknown" is not "zero".** An unresolved viewer count must not force ECO mode.
- `data/*.json` and `Media/` are runtime state. Keep them git-ignored;
  `data/favorite_bits.jsonl` is the exception — it is the operator's taste and belongs in git.
- Do not add `getattr(self.cfg, "key", default)`; every key lives in `config.py` with a default.

---

## 9. Configuration — the operator's current values

```ini
# Persona / model
GEMINI_MODEL=gemini-3.7-flash        TTS_REFERENCE_VOICE=pure_oracle
VISUALIZER_ASPECT_RATIO=9:16
# Bit cadence and length (tuned for clip harvesting)
IDLE_SILENCE_THRESHOLD_SEC=25  SPONTANEOUS_MIN_INTERVAL_SEC=10  SPONTANEOUS_MAX_BACKOFF_SEC=45
BIT_WORDS_MIN=10  BIT_WORDS_MAX=25  ONE_LINER_RATIO=0.60  TTS_BEAT_GAP_SEC=0.55
# Clip-friendly spacing
MIN_TURN_GAP_SEC=15  REFLECTION_POST_SPEECH_CHAT_DELAY_SEC=4  COMMENT_POST_SPEECH_HOLD_SEC=3
QUESTION_MIN_DISPLAY_SEC=2.5  MOTTO_PRE_FADE_IN_SEC=2.75  PROMO_OVERLAY_INTERVAL_SEC=240
# Chat
SMALL_ROOM_VIEWERS=5  MAX_RESPONSES_PER_MINUTE=6  READ_QUESTION_ALOUD=all
# Cast
CAST_MIN_INTERVAL_SEC=125  CAST_MAX_INTERVAL_SEC=200  CAST_MAX_PER_SESSION=200
# TTS
TTS_CFG_WEIGHT=0.4  (per-mood overrides in config; deadpan 0.30 … hyped 0.60)
```
Defaults not overridden in `.env`: `NDI_AUDIO_BLOCK_SAMPLES=2400`, `TTS_EXAGGERATION_MAX=0.7`,
`BIT_THINKING_BUDGET=1024`, `BIT_TEMPERATURE=0.85`, `ANTI_REPETITION_WINDOW=20`,
`ANCHOR_BAN_ENABLED=false`, `ASSUMED_VIEWERS_WHEN_UNKNOWN=1`, `TURN_MAX_SEC=75`.

`MIN_INTERJECTION_INTERVAL_SEC` is still in `.env` but no longer read; safe to delete.

---

## 10. Open items
1. **Callbacks in chat answers** (not bits) using `chatter_db` and `recent_qa_threads`. The
   strongest remaining feature and the one only a live show can do.
2. **Server-side clip clamp on GAMER** (`wav *= 0.95/peak` before int16 write), then raise
   `TTS_EXAGGERATION_MAX` toward 0.85 so savage/hyped closers get full range. Currently clamped
   at 0.7 because the source clips.
3. **Cast cross-talk** — a follow-up event type so personas can react to each other.
4. **Escalating runs** — occasionally let 2–3 consecutive bits share a thread.
5. **Room awareness** — the prompt has viewer count, uptime, and time of day but does not use them.
6. **Negative theme deck** — log theme → outcome and prune the duds.
7. Stalls during cache primes: both processes stalled ~200–400 ms while the reflection cache and
   chatter DB wrote to disk. Move those writes off the event-loop thread.

---

## 11. Testing

`pytest tests/ -q --ignore=tests/test_promo_cards.py` → **75 passing**. (The promo test needs a
display; set `SDL_VIDEODRIVER=dummy` to include it.)

Three tests exist specifically because a change broke the live stream and every other test passed:
- `test_call_signatures.py` — keyword mismatch between `app.py` and `ai_brain.py`
- `test_call_signatures.py::test_no_use_before_assignment_in_prompt_builders` — `UnboundLocalError`
- `test_call_signatures.py::test_degenerate_turn_still_restores_the_motto` — the missing `else`

When a bug reaches the stream, add the test that would have caught it.

**`bit_lab.py` — offline A/B for bit quality.** Run with the stream down.
```
python bit_lab.py --n 24 --label baseline
python bit_lab.py --n 24 --b '{"one_liner_ratio": 0.35}'
python bit_lab.py --score bitlab/<timestamp>/blind.md
```
Generates two batches, interleaves them blind with a checkbox each, and hides the key until you have
marked them. The scorer refuses to declare a winner under a 15-point gap because that is noise at
this sample size. **Use this instead of memory.** The project lost its comedic register for a week
because changes were judged against recollection of how bits sounded days earlier.

**Live verification checklist** (run with OBS open — that is the real load):
- Several `[TTS LIVE]` lines per answer; `underruns=0`; pump interval ≈ 60 ms.
- `[TTS BEAT]` on punchline replies, with varying millisecond values.
- `[Reaction] +N` when you type "lmao" in console within 25 s of a line.
- `🔑 [YouTube Data API] Concurrent Viewers detected: N` — if absent, the show will assume
  `ASSUMED_VIEWERS_WHEN_UNKNOWN` rather than idling.
- No `[TTS PEAK]`, `[TURN TIMEOUT]`, `[Degenerate Turn]`, or unexplained `[Chat Skipped]`.

---

## 12. Working agreement for agents
- Read this file first. `docs/archive/` is history, not instructions.
- Change the smallest thing that fixes the problem. Do not refactor adjacent code.
- Instrument before fixing: if a symptom is not in the log, add the log line, reproduce, then fix.
- Never adjust a config default to make an acceptance test pass; report the failure.
- Never judge a comedy change by memory. Use `bit_lab.py`.
- Commit after each self-contained change, with the test that covers it. Both machines pull from
  GitHub; uncommitted edits are how versions diverge.
- If a request conflicts with §2 or §8, stop and say so before implementing.
