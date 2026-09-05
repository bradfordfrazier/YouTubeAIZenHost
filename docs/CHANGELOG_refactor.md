# I AM AI Host — Refactor Changelog

## Phase 1: Remove Human Host / Co-Host Layer

### Summary of Changes
- **Single Solo Host Architecture**: Completely removed the human host/co-host interaction layer, freeing up CPU cycles, memory, and asyncio event loop tasks.
- **`app.py`**:
  - Removed `transcript_file_task`, `last_transcript_text`, `last_file_position`, `current_host_transcript`.
  - Updated priority map to solo AI host tiers:
    1. `superchat` (Priority 1)
    2. `direct_mention` (Priority 2)
    3. `greeting` (Priority 3)
    4. `chat` (Priority 4)
    5. `cast` (Priority 5)
    6. `spontaneous` / `system` (Priority 6)
  - Simplified `console_chat_task` to inject pure viewer chat messages only (removed all host transcript simulation).
  - Updated `render_frame` calls across all frames to solo AI host signature.
- **`ai_brain.py`**:
  - Removed `transcript_buffer`, `add_transcript`, `last_speech_time`.
  - Removed "Recent Host & Guest Dialogue" from context builder prompt.
  - Simplified channel addressing rules: the AI *is* the channel host and addresses viewers directly.
  - Removed `is_host` parameter and `host_question` branches from `should_trigger_response`.
  - Cleaned up `SPONTANEOUS_THEMES` and removed references to roasting/addressing a second human host.
- **`visualizer.py`**:
  - Removed `_draw_host_transcript_card`, `font_host_transcript`, and `surf_host_card`.
  - Updated `render_frame` signature: `render_frame(self, audio_metrics, chat_messages, ai_subtitle, obs_connected=True, engagement_mode="active", concurrent_viewers=0, is_stream_live=True, pinned_chat_message=None)`.
  - Cleaned top header status to display OBS/live status, viewer count, and engagement mode.
- **`config.py` & `.env.example`**:
  - Removed `host_streamer_name`, `transcript_file_path`, `obs_transcript_source_name`, `show_host_transcript_card`.
  - Renamed `ai_cohost_name` -> `ai_host_name` (with backwards-compatible `@property` fallback for `ai_cohost_name` and startup deprecation log).
  - Unified channel handle identity to `youtube_channel_handle`.
  - Updated default `ai_system_prompt` to define a solo AI live host.
  - Added startup deprecation warnings for any obsolete environment variables.

### Verification & Performance Numbers
- `test_pipeline.py`: **100% Passed** (Config, AI Brain, TTS, Visualizer, Rehearsal).
- `test_pinned_chat.py`: **16/16 Passed** (All layout, animation, word wrapping, and visualizer rendering tests).
- `test_dual_aspect_visualizer.py`: **Passed** (16:9 renders at **147.1 FPS**, 9:16 renders at **134.1 FPS** on preview/NDI test harness).
- App starts up cleanly with 0 API keys in simulation mode, rendering at 60 FPS and accepting viewer console chat.

## Phase 2: Fix Mood Exaggeration Bug & Sentence-Pipeline TTS

### Summary of Changes
- **Mood Exaggeration Fix**:
  - `tts_engine.py`: Fixed `synthesize(text: str, mood: str = "neutral")` to resolve exaggeration from explicit mood argument (deadpan=0.3, calm/wise=0.45, neutral=0.5, energetic/philosophical=0.6, hyped=0.8, savage=0.85) with regex fallback, logging resolved exaggeration on every synthesis call.
  - `greeting_cache.py`: Passes active dynamic mood to `tts.synthesize(..., mood=active_mood)`.
- **Utterance Bookkeeping & Audio Crossfading**:
  - `tts_engine.py`: Added `begin_utterance()`, `end_utterance()`, `clear_audio_buffer()`, and `wait_until_speech_completed()` for clean lifecycle tracking and seamless queue draining.
  - Added 5ms linear crossfades (`apply_chunk_crossfades`) on chunk boundaries (skipping head fade on chunk 1 for crisp onset) and 0.15s prepended silence gaps for sentence chunks N > 1.
  - Added `asyncio.Semaphore(max_concurrent_synth=2)` for safe GPU Chatterbox synthesis with per-sentence timeout fallback to local Edge-TTS without aborting the turn.
- **Sentence-Level LLM Extraction**:
  - `ai_brain.py`: Added `_extract_completed_sentences` with robust regex boundaries and negative lookahead guards against abbreviations (`Dr.`, `Mr.`, `vs.`, `e.g.`, `i.e.`), decimals (`3.14`), ellipses (`...`), and mentions (`@`), enforcing a minimum 3 words & 12 characters.
  - Added end-of-stream sentence repair to append terminal punctuation to any remaining text fragment.
- **Producer / Consumer Pipelining**:
  - `app.py`: Rebuilt `_execute_ai_turn` as an asynchronous producer-consumer pipeline.
  - Sentence 1 is synthesized and queued immediately; while Sentence 1 plays, Sentence 2+ are synthesized concurrently in the background.
  - Pinned question reading hold is strictly preserved before Chunk 1 playback begins.
  - Added detailed telemetry logging for turn performance: TTFT (Time to First Token), TTFS (Time to First Sentence), TTFA (Time to First Audio pushed), and total turn completion time.

### Verification & Performance Numbers
- `test_phase2_pipelining.py`: **100% Passed** (Mood mapping, sentence chunker/abbreviation guards, audio crossfades/silence gap, audio drain synchronization, full pipelined turn flow).
- `test_pipeline.py`: **100% Passed**.
- `test_pinned_chat.py`: **16/16 Passed**.
- `test_dual_aspect_visualizer.py`: **Passed** (16:9 at **150.9 FPS**, 9:16 at **134.8 FPS**).
- Measured live timings: TTFT ~688ms, TTFS ~834ms, TTFA ~4320ms (including question display hold) on Gemini 3.7 Flash + Chatterbox.

## Phase 3: Trigger and Cost Hygiene

### Summary of Changes
- **Tightened Trigger & Addressing Hygiene**:
  - `ai_brain.py`: Cleaned `chat_keywords` to remove single-letter, gaming, and ultra-common casual tokens (`w`, `l`, `gg`, `lol`, `lmao`, `real`, `fake`, `game`, `play`, `win`, `lose`, `trash`, `clutch`, `based`), retaining explicit question words and asks (`roast`, `how`, `why`, `who`, `what`, `when`, `where`, `opinion`, `thoughts`, `explain`, `tell`, `think`, `agree`, `disagree`, `consciousness`, `source`, `truth`).
  - Fixed false-positive substring matches for bare triggers like `ai`, `bot`, `god`, `iam`: now enforced as whole words (`\b...\b`) and only when explicitly addressed to the AI (`@`-prefixed, followed by punctuation/questions, or starting with conversational question verbs). "again lol", "god that game was trash", and "robot" no longer trigger.
  - Precomputed `exempt_names` and `host_entities` sets once in `__init__` (and updated in `update_channel_identity`), eliminating repetitive set constructions per message.
- **Config-Driven Chat Sampling**:
  - `config.py` & `ai_brain.py`: Added `chat_sampling_viewer_threshold` (default 25) and `chat_sampling_probability` (default 0.35). Non-question, non-mention chat is sampled probabilistically under high audience loads to preserve rate limits, while Superchats, direct mentions, new-chatter greetings, and questions (`?`) are never sampled out.
- **Stricter Deep-vs-Fast Classifier**:
  - `ai_brain.py`: Updated `_classify_prompt_depth` to require **both** (a) $\ge 8$ words and (b) a term from the reduced philosophical list (`death, die, dying, grief, loss, meaning, purpose, consciousness, free will, soul, suffering, enlightenment, who am i, what am i, impermanence, forgive`). Dropped noisy casual terms (`mind, real, fear, nothing, truth, universe, reality, ego, exist, god, quantum, void, observer, destiny`).
  - Added turn-level telemetry logging of classification decisions and matched terms.
- **Heap-Backed Priority Queue (`heapq`)**:
  - `app.py`: Replaced manual list sorting with `heapq` keyed on `(priority, created_at, seq_id)`, implementing comparison dunders on `CommentEvent`.
  - Superchats (Prio 1) and Direct Mentions (Prio 2) preemptively jump ahead of regular chat (Prio 4) and synthetic cast filler (Prio 5), while maintaining strict FIFO arrival order within identical priority tiers.
  - Retained TTL pruning and capacity eviction.

## Phase 4: Synthetic Cast Transparency

### Summary of Changes
- **Cast Transparency Pill Badges**:
  - `config.py`: Added `cast_badge_label` (default `"CAST"`, configurable via `CAST_BADGE_LABEL`).
  - `visualizer.py`: Added `_draw_cast_badge` helper rendering a glassmorphic neon-purple pill badge (`[CAST]`) next to author names:
    - In the top pinned card (`_draw_live_chat_card`) when a cast question is docked at top.
    - In the scrolling live chat feed (`_draw_live_chat_card`) for all chronological in-feed cast rows.
    - In the center question card (`_draw_ai_subtitle_card`) during question reading preview hold.
    - Badges are clearly legible in both 16:9 landscape (1920x1080) and 9:16 vertical (1080x1920) modes, while strictly absent for real viewers.
- **Fictional Ensemble Fourth-Wall Guidance**:
  - `ai_brain.py`:
    - Updated `add_chat_message` to record `is_cast: bool` and `cast_persona: Optional[str]`.
    - Recent live chat buffer now renders `Cast @Author [CAST]: message` for synthetic askers and `Viewer @Author: message` for real viewers.
    - Added `Special Mode: SYNTHETIC CAST INTERACTION` with clear prompt guidance instructing Gemini to treat the asker as a recurring fictional cast character with playful fourth-wall breaks while never implying they are a real human viewer.
- **ChatterDB Separation & Relationship Isolation**:
  - `chatter_db.py`:
    - Updated `ChatterProfile.generate_context_snippet()` to produce `[CAST CONTEXT: @handle | Synthetic Cast Member (Recurring Fictional Cast Character) | Persona: ...]` for cast members, omitting "Visit #X" counts.
    - `record_activity` marks cast handles `is_cast=True` and prevents session-based incrementation of `visit_count` so cast members are never treated as real regulars.
    - Added `get_returning_viewers()` which strictly filters out synthetic cast personas, preserving pure human viewer statistics.
    - Pre-seeded all 12 canonical cast archetypes.
  - `app.py`:
    - Updated cast scheduler task to pass `is_cast=True` and `cast_persona` to `add_chat_message`.

### Verification & Performance Numbers
- `test_phase4.py`: **100% Passed** (Config, ChatterDB context snippets & stats isolation, AI Brain prompt formatting, Visualizer 16:9 and 9:16 badge rendering).
- `test_phase3_triggers_and_queue.py`: **100% Passed**.
- `tests/test_triggers.py`: **100% Passed**.
- `test_pipeline.py`: **100% Passed** (Full end-to-end all-local pipeline).
- `test_pinned_chat.py`: **18/18 Passed** (All layout, queue, and transition tests).
- `test_dual_aspect_visualizer.py`: **Passed** (16:9 at **149.4 FPS**, 9:16 at **134.1 FPS**).

## Phase 5: Rendering Performance Decoupling

### Summary of Changes
- **Dedicated 60 FPS Multiprocessing Render Worker (`render_worker.py`)**:
  - Moved Pygame 1080p60 rendering loop and NDI video transmission into a separate dedicated worker process (`render_worker_main`).
  - Implemented `AudioMetricsSharedMemory` with 144-byte zero-copy struct (`rms`, `is_speaking`, 32-bin `spectrum`, `timestamp`), allowing real-time 100 Hz audio metric updates from the main process PortAudio callback and NDI audio pump.
  - Implemented `VisualizerProxy` with identical method signatures (`set_mood`, `set_subtitle`, `fade_out_for_turn`, `fade_out_question`, `clear_subtitle`, `trigger_celebration`, `trigger_promo`, `is_promo_active`, `should_quit`) for transparent integration in `app.py`.
  - Added worker crash resilience: auto-restarts worker process up to 3 times on unexpected failure without dropping audio/chat pipelines.
- **Cheap Rendering Optimizations in `visualizer.py`**:
  - Pre-allocated persistent 600x600 `_surf_god_circles` surface, eliminating per-frame surface allocation/destruction garbage collection churn.
  - Cached `ColorPalette.get(mood)` lookups per frame in `self.current_palette`.
  - Added `_text_cache` in `_render_text` to eliminate redundant font rendering allocations.
  - Throttled operator preview window `pygame.transform.smoothscale` and `flip` to $\le 30$ FPS, freeing GPU/CPU memory bandwidth while broadcast NDI output remains locked at full 60 FPS.
- **Main Event Loop Decoupling in `app.py`**:
  - Converted `video_broadcast_task` into a 20 Hz state synchronizer (`sync_state`) and event loop lag heartbeat monitor.
  - PortAudio callback and NDI audio pump write live audio reactivity metrics directly into `AudioMetricsSharedMemory`.

### Verification & Performance Numbers
- **cProfile 600-Frame Benchmark**: **128.1 FPS** (600 frames rendered in 4.68s at 1080p).
- **Asyncio Event Loop Drift**: **0.35 ms Average, 1.57 ms Maximum** (Target: $< 20$ ms).
- **AudioMetricsSharedMemory**: Exact float precision zero-copy verification passed.
- **Regression Suite**: `test_phase5.py`, `test_phase4.py`, `test_phase3_triggers_and_queue.py` all **100% Passed**.

| Metric | Target | Measured Result |
| :--- | :--- | :--- |
| **Render Frame Rate** | $\ge 58.0$ FPS | **128.1 FPS** |
| **Main Event Loop Lag Drift** | $< 20.0$ ms | **1.57 ms** max (0.35 ms avg) |
| **Shared Memory Audio Latency** | $< 10.0$ ms | **< 0.1 ms** (Zero-copy IPC) |

## Phase 6: Context-Aware Promo Cards

### Summary of Changes
- **Event-Driven Promo Engine (`app.py` & `visualizer.py`)**:
  - Replaced indiscriminate periodic timer rotation with context-aware event triggers:
    - **"Ask Anything" (`ask_god`)**: Triggers only when live chat has been silent for $\ge \text{promo\_ask\_quiet\_sec}$ (default 45s), concurrent viewers $\ge 1$, no AI turn is active, and no pinned question is active.
    - **"Like & Subscribe" (`like_sub`)**: Triggers within $\le \text{promo\_sub\_after\_turn\_sec}$ (default 3s) after a completed non-spontaneous viewer turn, greeting, or celebration, respecting a minimum cooldown interval of $\text{promo\_sub\_min\_interval\_sec}$ (default 300s / 5 min).
    - **Speech & Question Priority**: Promos strictly yield to speech and pinned questions, immediately exiting if speech commences.
- **Config & Backwards Compatibility (`config.py`)**:
  - Added `promo_mode: str = "event"` ("event" | "timer", configurable via `PROMO_MODE`).
  - Added `promo_ask_quiet_sec: float = 45.0` (`PROMO_ASK_QUIET_SEC`).
  - Added `promo_sub_after_turn_sec: float = 3.0` (`PROMO_SUB_AFTER_TURN_SEC`).
  - Added `promo_sub_min_interval_sec: float = 300.0` (`PROMO_SUB_MIN_INTERVAL_SEC`).
  - If `promo_mode == "timer"`, `Visualizer` maintains its legacy periodic rotation fallback.

---

## [Phase 7] - Housekeeping, Config Reference & Pytest Suite
**Date**: 2026-09-05  
**Status**: COMPLETE

### Key Changes
- **Unified Logging (`logging_setup.py`)**:
  - Implemented centralized logging setup via `setup_logging()` and structured `CustomFormatter` (`HH:MM:SS [LEVEL] [MODULE] message`).
  - Added automatic Windows stdout/stderr UTF-8 stream reconfiguration with replace fallback, completely eliminating `UnicodeEncodeError` when emitting emojis on Windows CP1252 consoles.
  - Purged duplicate `logging.basicConfig()` and raw `print()` statements from `ai_brain.py`, `tts_engine.py`, `ndi_streamer.py`, and `app.py`.
- **Config Reference & Attribute Access Cleanup (`config.py`, `docs/config_reference.md`)**:
  - Purged obsolete `tts_engine` (retaining `tts_backend`) and redundant `gemini_thinking_budget` entries.
  - Replaced fragile `getattr(self.cfg, ...)` usages in `tts_engine.py` and `ai_brain.py` with direct type-safe attribute access.
  - Added dedicated `_extract_mood()` helper method in `ai_brain.py` for structured mood parsing.
  - Authored comprehensive configuration reference table in `docs/config_reference.md` covering all 75+ configuration keys across 14 sections with types, environment variable overrides, defaults, and descriptions.
- **Repository Line Endings (`.gitattributes`)**:
  - Created root `.gitattributes` file enforcing consistent LF (`eol=lf`) line endings across Python, Markdown, JSON, YAML, and Shell files.
- **Comprehensive Pytest Suite (`tests/`)**:
  - Established modular unit test suite in `tests/`:
    - `tests/test_triggers.py`: Validates trigger word boundaries, keyword matching, high-viewer chat sampling, and min-heap priority queue ordering.
    - `tests/test_sentence_splitter.py`: Validates first-sentence extraction, sentence boundary splitting, and mood bracket stripping.
    - `tests/test_promo_cards.py`: Validates event vs. timer modes, chat lull triggers, post-turn triggers, and speech interruptions.
    - `tests/test_render_ipc.py`: Validates zero-copy `AudioMetricsSharedMemory` packing/unpacking, `VisualizerProxy` state synchronization, and render worker IPC.

### Verification & Performance Numbers
- `python -m pytest -q tests/`: **13 passed in 6.06s** (100% success).
- Full End-to-End Regression Suite:
  - `test_pipeline.py`: **100% Passed** (TTS, Visualizer, NDI Broadcast, AI Brain streaming & token throttling).
  - `test_pinned_chat.py`: **100% Passed** (Pinned chat rendering, zero-flash transitions, reflection lifecycles, and queue-aware holding).
  - `test_phase6.py`: **100% Passed** (Context-aware promo card triggers and event/timer state machines).
  - `test_phase5.py`: **100% Passed** (600 frames at **131.4 FPS**, asyncio drift **0.41ms avg / 1.28ms max**).
  - `test_phase4.py`: **100% Passed** (Synthetic cast badges in 16:9 and 9:16 aspect ratios).
  - `test_phase3_triggers_and_queue.py`: **100% Passed** (Trigger hygiene, sampling, deep/fast classifier, heapq priority queue).






