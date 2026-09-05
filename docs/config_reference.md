# I AM — Configuration Reference

This reference documents every configuration parameter in `config.py`, its environment variable override, default value, type, and the file(s) that read it.

---

## 1. Channel Identity & General Settings

| Key | Environment Variable | Type | Default Value | Description | Read By |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `youtube_channel_handle` | `YOUTUBE_CHANNEL_HANDLE` | `str` | `"@MassiveGodComplex"` | Primary YouTube channel handle | `config.py`, `ai_brain.py`, `app.py` |
| `youtube_channel_id` | `YOUTUBE_CHANNEL_ID` | `str` | `""` | Optional YouTube Channel ID | `config.py` |
| `channel_handles` | `CHANNEL_HANDLES` | `list[str]` | `["MassiveGodComplex", "Massive"]` | Recognized aliases for channel identity | `config.py`, `ai_brain.py` |
| `ai_host_name` | `AI_HOST_NAME` | `str` | `"I Am"` | Spoken AI Host persona name | `ai_brain.py`, `visualizer.py`, `app.py` |
| `ai_system_prompt` | `AI_SYSTEM_PROMPT` | `str` | *(Core Source Persona Prompt)* | Full system instructions for Gemini | `ai_brain.py` |
| `cast_badge_label` | `CAST_BADGE_LABEL` | `str` | `"CAST"` | Text label rendered on synthetic cast badges | `visualizer.py`, `ai_brain.py`, `chatter_db.py` |

---

## 2. Gemini AI Brain & Thinking Configuration

| Key | Environment Variable | Type | Default Value | Description | Read By |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `gemini_api_key` | `GEMINI_API_KEY` | `str` | `""` | Google Gemini API Key | `ai_brain.py` |
| `gemini_model` | `GEMINI_MODEL` | `str` | `"gemini-3.7-flash"` | Primary Gemini LLM model | `ai_brain.py`, `app.py` |
| `gemini_thinking_level` | `GEMINI_THINKING_LEVEL` | `str` | `"LOW"` | Default thinking effort (`LOW` / `HIGH`) | `ai_brain.py` |
| `gemini_fast_thinking_budget` | `GEMINI_FAST_THINKING_BUDGET` | `int` | `0` | Thinking budget for fast conversational banter | `ai_brain.py` |
| `gemini_deep_thinking_budget` | `GEMINI_DEEP_THINKING_BUDGET` | `int` | `512` | Thinking budget for existential inquiries | `ai_brain.py` |
| `gemini_deep_model` | `GEMINI_DEEP_MODEL` | `Optional[str]` | `None` | Optional dedicated model for deep turns | `ai_brain.py` |
| `gemini_max_output_tokens` | `GEMINI_MAX_OUTPUT_TOKENS` | `int` | `1024` | Maximum tokens per Gemini response | `ai_brain.py` |
| `gemini_temperature` | `GEMINI_TEMPERATURE` | `float` | `0.7` | Sampling temperature for LLM generation | `ai_brain.py` |
| `gemini_top_p` | `GEMINI_TOP_P` | `float` | `0.9` | Nucleus sampling probability | `ai_brain.py` |
| `trigger_words` | `TRIGGER_WORDS` | `list[str]` | `["i am", "iam", "ai", ...]` | Keywords triggering direct AI host responses | `ai_brain.py` |
| `chat_sampling_viewer_threshold` | `CHAT_SAMPLING_VIEWER_THRESHOLD` | `int` | `25` | Viewer count above which sampling activates | `ai_brain.py` |
| `chat_sampling_probability` | `CHAT_SAMPLING_PROBABILITY` | `float` | `0.35` | Sampling probability for busy chat streams | `ai_brain.py` |
| `chat_reader_mode` | `CHAT_READER_MODE` | `bool` | `False` | Passively reads chat without commentary | `ai_brain.py`, `app.py` |
| `ignore_peer_replies` | `IGNORE_PEER_REPLIES` | `bool` | `True` | Ignores chatter-to-chatter `@mention` replies | `ai_brain.py` |
| `greet_new_chatters` | `GREET_NEW_CHATTERS` | `bool` | `True` | Warmly greets first-time chatters | `ai_brain.py` |
| `greet_viewer_joins` | `GREET_VIEWER_JOINS` | `bool` | `False` | Greets viewer count increases | `app.py` |
| `viewer_join_cooldown_sec` | `VIEWER_JOIN_COOLDOWN_SEC` | `float` | `120.0` | Cooldown between viewer join greetings | `app.py` |
| `thank_subscribers` | `THANK_SUBSCRIBERS` | `bool` | `True` | Acknowledges new channel subscribers | `app.py` |
| `max_responses_per_minute` | `MAX_RESPONSES_PER_MINUTE` | `int` | `12` | Token protection rate limiter (1 minute) | `ai_brain.py` |
| `max_responses_per_hour` | `MAX_RESPONSES_PER_HOUR` | `int` | `120` | Token protection rate limiter (1 hour) | `ai_brain.py` |

---

## 3. Spontaneous Commentary & Cache Subsystems

| Key | Environment Variable | Type | Default Value | Description | Read By |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `spontaneous_commentary_enabled` | `SPONTANEOUS_COMMENTARY_ENABLED` | `bool` | `True` | Enables unprompted philosophical reflections | `app.py` |
| `spontaneous_require_viewers` | `SPONTANEOUS_REQUIRE_VIEWERS` | `bool` | `False` | Suppresses spontaneous speech if 0 viewers | `app.py` |
| `idle_silence_threshold_sec` | `IDLE_SILENCE_THRESHOLD_SEC` | `float` | `15.0` | Chat quiet threshold before reflection check | `app.py` |
| `spontaneous_min_interval_sec` | `SPONTANEOUS_MIN_INTERVAL_SEC` | `float` | `35.0` | Base interval between spontaneous reflections | `app.py` |
| `spontaneous_max_backoff_sec` | `SPONTANEOUS_MAX_BACKOFF_SEC` | `float` | `180.0` | Max exponential backoff during quiet streams | `app.py` |
| `motto_phrase` | `MOTTO_PHRASE` | `str` | `"Everything is perfect."` | Default subtitle motto during silence | `visualizer.py` |
| `reflection_cache_enabled` | `REFLECTION_CACHE_ENABLED` | `bool` | `True` | Pre-computes spontaneous reflections in bg | `reflection_cache.py`, `ai_brain.py`, `app.py` |
| `reflection_cache_size` | `REFLECTION_CACHE_SIZE` | `int` | `4` | Maximum pre-computed reflections stored | `reflection_cache.py`, `ai_brain.py` |
| `greeting_cache_enabled` | `GREETING_CACHE_ENABLED` | `bool` | `True` | Pre-computes 48kHz audio greetings in bg | `greeting_cache.py`, `app.py` |
| `greeting_cache_size` | `GREETING_CACHE_SIZE` | `int` | `3` | Maximum pre-synthesized greetings stored | `greeting_cache.py` |
| `greeting_cache_poll_interval_sec`| `GREETING_CACHE_POLL_INTERVAL_SEC` | `float` | `15.0` | Greeting replenishment check cadence | `greeting_cache.py`, `app.py` |

---

## 4. Synthetic Cast Subsystem

| Key | Environment Variable | Type | Default Value | Description | Read By |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `cast_enabled` | `CAST_ENABLED` | `bool` | `True` | Enables synthetic cast member inquiries | `cast_engine.py`, `app.py` |
| `cast_require_viewers` | `CAST_REQUIRE_VIEWERS` | `bool` | `False` | Suppresses cast questions if 0 viewers | `app.py` |
| `cast_min_interval_sec` | `CAST_MIN_INTERVAL_SEC` | `float` | `70.0` | Minimum interval between cast questions | `cast_engine.py`, `app.py` |
| `cast_max_interval_sec` | `CAST_MAX_INTERVAL_SEC` | `float` | `130.0` | Maximum interval between cast questions | `cast_engine.py` |
| `cast_quiet_chat_threshold_sec` | `CAST_QUIET_CHAT_THRESHOLD_SEC` | `float` | `40.0` | Chat quiet threshold before cast triggers | `cast_engine.py`, `app.py` |
| `cast_max_per_session` | `CAST_MAX_PER_SESSION` | `int` | `50` | Maximum cast questions per broadcast | `cast_engine.py` |

---

## 5. Neural TTS Engine (ChatterBox Turbo / Edge-TTS)

| Key | Environment Variable | Type | Default Value | Description | Read By |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `tts_backend` | `TTS_BACKEND` | `str` | `"chatterbox"` | Active TTS engine (`chatterbox` / `edge`) | `tts_engine.py`, `app.py` |
| `tts_server_url` | `TTS_SERVER_URL` | `str` | `"http://192.168.0.115:8123"` | LAN endpoint for ChatterBox Turbo server | `tts_engine.py` |
| `tts_reference_voice` | `TTS_REFERENCE_VOICE` | `str` | `"cohost.wav"` | Reference audio file for voice cloning | `tts_engine.py` |
| `tts_request_timeout_floor` | `TTS_REQUEST_TIMEOUT_FLOOR` | `float` | `4.0` | Minimum request timeout for TTS requests | `tts_engine.py` |
| `tts_request_timeout_ceiling` | `TTS_REQUEST_TIMEOUT_CEILING` | `float` | `30.0` | Maximum request timeout for TTS requests | `tts_engine.py` |
| `inter_sentence_gap_sec` | `INTER_SENTENCE_GAP_SEC` | `float` | `0.15` | Natural pause duration between sentences | `tts_engine.py` |
| `max_concurrent_synth` | `MAX_CONCURRENT_SYNTH` | `int` | `2` | Parallel sentence synthesis semaphore limit | `tts_engine.py` |
| `tts_exaggeration_default` | `TTS_EXAGGERATION_DEFAULT` | `float` | `0.5` | Default emotion exaggeration factor | `tts_engine.py` |
| `tts_mood_exaggeration_map` | *(Internal Map)* | `dict` | *(12 mood factors)* | Exact exaggeration per mood keyword | `tts_engine.py` |
| `tts_voice` | `TTS_VOICE` | `str` | `"en-US-ChristopherNeural"` | Voice model for Edge-TTS fallback | `tts_engine.py` |
| `tts_sample_rate` | `TTS_SAMPLE_RATE` | `int` | `48000` | Audio sampling rate in Hz (Broadcast standard)| `tts_engine.py`, `ndi_streamer.py` |
| `tts_pitch` | `TTS_PITCH` | `str` | `"+0Hz"` | Edge-TTS pitch offset | `tts_engine.py` |
| `tts_rate` | `TTS_RATE` | `str` | `"+5%"` | Edge-TTS speed rate adjustment | `tts_engine.py` |

---

## 6. Pygame 1080p60 Visualizer & Promo Cards

| Key | Environment Variable | Type | Default Value | Description | Read By |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `vox_only_mode` | `VOX_ONLY_MODE` | `bool` | `False` | Pinned question remains visible during speech; spoken text is never rendered | `visualizer.py`, `app.py` |
| `visualizer_aspect_ratio` | `VISUALIZER_ASPECT_RATIO` | `str` | `"16:9"` | Aspect ratio (`16:9` landscape / `9:16` vertical) | `visualizer.py`, `app.py` |
| `visualizer_width` | `VISUALIZER_WIDTH` | `int` | `1920` (or `1080`) | Visualizer canvas width in pixels | `visualizer.py`, `ndi_streamer.py`, `render_worker.py` |
| `visualizer_height` | `VISUALIZER_HEIGHT` | `int` | `1080` (or `1920`) | Visualizer canvas height in pixels | `visualizer.py`, `ndi_streamer.py`, `render_worker.py` |
| `visualizer_fps` | `VISUALIZER_FPS` | `int` | `60` | Target render and NDI frame rate | `visualizer.py`, `ndi_streamer.py`, `render_worker.py`, `app.py` |
| `visualizer_headless` | `VISUALIZER_HEADLESS` | `bool` | `False` | Disables operator preview window | `visualizer.py` |
| `visualizer_borderless` | `VISUALIZER_BORDERLESS` | `bool` | `False` | Launches preview window borderless | `visualizer.py` |
| `visualizer_particle_count` | `VISUALIZER_PARTICLE_COUNT` | `int` | `70` | Background ambient particle count | `visualizer.py` |
| `show_top_status_bar` | `SHOW_TOP_STATUS_BAR` | `bool` | `False` | Renders top HUD diagnostics bar | `visualizer.py` |
| `comment_fade_in_sec` | `COMMENT_FADE_IN_SEC` | `float` | `0.6` | Chat card docking fade-in duration | `visualizer.py` |
| `comment_fade_out_sec` | `COMMENT_FADE_OUT_SEC` | `float` | `1.2` | Chat card docking fade-out duration | `visualizer.py` |
| `comment_post_speech_hold_sec` | `COMMENT_POST_SPEECH_HOLD_SEC` | `float` | `15.0` | Duration question is held after speech | `app.py` |
| `comment_active_queue_hold_sec`| `COMMENT_ACTIVE_QUEUE_HOLD_SEC` | `float` | `2.5` | Reduced hold when more comments are queued | `app.py` |
| `question_fade_in_sec` | `QUESTION_FADE_IN_SEC` | `float` | `0.80` | Center question card fade-in duration | `visualizer.py` |
| `question_fade_out_sec` | `QUESTION_FADE_OUT_SEC` | `float` | `0.80` | Center question card fade-out duration | `visualizer.py` |
| `question_min_display_sec` | `QUESTION_MIN_DISPLAY_SEC` | `float` | `2.0` | Minimum duration center card is displayed | `visualizer.py` |
| `motto_fade_in_sec` | `MOTTO_FADE_IN_SEC` | `float` | `1.4` | Motto fade-in duration | `visualizer.py` |
| `motto_fade_out_sec` | `MOTTO_FADE_OUT_SEC` | `float` | `0.6` | Motto fade-out duration | `visualizer.py` |
| `promo_overlay_enabled` | `PROMO_OVERLAY_ENABLED` | `bool` | `True` | Enables promotional callout cards | `visualizer.py`, `app.py` |
| `promo_mode` | `PROMO_MODE` | `str` | `"event"` | Promo trigger mode (`event` / `timer`) | `visualizer.py`, `app.py` |
| `promo_ask_quiet_sec` | `PROMO_ASK_QUIET_SEC` | `float` | `45.0` | Silence threshold for "Ask Anything" promo | `app.py` |
| `promo_sub_after_turn_sec` | `PROMO_SUB_AFTER_TURN_SEC` | `float` | `3.0` | Window after turn for "Like & Sub" promo | `app.py` |
| `promo_sub_min_interval_sec` | `PROMO_SUB_MIN_INTERVAL_SEC` | `float` | `300.0` | Minimum interval between "Like & Sub" promos | `app.py` |
| `promo_overlay_duration_sec` | `PROMO_OVERLAY_DURATION_SEC` | `float` | `10.0` | Display duration of promo callout card | `visualizer.py` |
| `promo_overlay_entrance_sec` | `PROMO_OVERLAY_ENTRANCE_SEC` | `float` | `0.9` | Smooth slide/fade entrance duration | `visualizer.py` |
| `promo_overlay_exit_sec` | `PROMO_OVERLAY_EXIT_SEC` | `float` | `1.15` | Smooth slide/fade exit duration | `visualizer.py` |
| `promo_overlay_hover_amp` | `PROMO_OVERLAY_HOVER_AMP` | `float` | `4.5` | Hover floating oscillation amplitude | `visualizer.py` |

---

## 7. NDI Broadcast & Local WASAPI Audio

| Key | Environment Variable | Type | Default Value | Description | Read By |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `ndi_stream_name` | `NDI_STREAM_NAME` | `str` | `"AI_COHOST_FEED"` | Outbound NDI stream source name | `ndi_streamer.py`, `render_worker.py`, `app.py` |
| `ndi_audio_enabled` | `NDI_AUDIO_ENABLED` | `bool` | `True` | Pumps 48kHz audio into NDI stream | `ndi_streamer.py`, `app.py` |
| `local_audio_enabled` | `LOCAL_AUDIO_ENABLED` | `bool` | `True` | Plays audio locally for OBS WASAPI capture | `app.py` |
| `local_audio_device` | `LOCAL_AUDIO_DEVICE` | `Optional[str]`| `None` | Specific Windows audio device target | `app.py` |
| `local_audio_volume` | `LOCAL_AUDIO_VOLUME` | `float` | `1.0` | Local audio playback volume multiplier | `app.py` |
| `process_priority` | `PROCESS_PRIORITY` | `str` | `"above_normal"` | Windows thread/process scheduling priority | `app.py`, `render_worker.py` |

---

## 8. OBS WebSocket & Session Logging

| Key | Environment Variable | Type | Default Value | Description | Read By |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `obs_ws_host` | `OBS_WS_HOST` | `str` | `"localhost"` | OBS Studio WebSocket server host | `app.py` |
| `obs_ws_port` | `OBS_WS_PORT` | `int` | `4455` | OBS Studio WebSocket server port | `app.py` |
| `obs_ws_password` | `OBS_WS_PASSWORD` | `str` | `""` | OBS Studio WebSocket authentication password | `app.py` |
| `session_logging_enabled` | `SESSION_LOGGING_ENABLED` | `bool` | `True` | Records structured JSONL session transcripts | `session_log.py`, `app.py` |
| `session_log_dir` | `SESSION_LOG_DIR` | `str` | `"logs/sessions"` | Directory path for session logs | `session_log.py`, `app.py` |
