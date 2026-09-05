# YouTube AI Zen Host — Configuration Reference

This document provides a complete reference for every configuration option in `AppConfig` (`config.py`). All settings can be specified via environment variables in `.env`.

---

## 1. Channel Identity

| Field Name | Env Variable | Default Value | Type | Readers | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `youtube_channel_handle` | `YOUTUBE_CHANNEL_HANDLE` | `"@MassiveGodComplex"` | `str` | `config.py`, `app.py`, `greeting_cache.py` | Official YouTube channel handle. |
| `youtube_channel_id` | `YOUTUBE_CHANNEL_ID` | `""` | `str` | `config.py`, `app.py` | Optional YouTube channel UC ID. |
| `channel_handles` | `CHANNEL_HANDLES` | `["MassiveGodComplex", "Massive"]` | `List[str]` | `config.py`, `app.py` | Recognized author handles representing the channel owner / self. |

---

## 2. OBS Studio Integration

| Field Name | Env Variable | Default Value | Type | Readers | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `obs_ws_host` | `OBS_WS_HOST` | `"localhost"` | `str` | `app.py` | Hostname or IP of OBS WebSocket v5 server. |
| `obs_ws_port` | `OBS_WS_PORT` | `4455` | `int` | `app.py` | Port of OBS WebSocket v5 server. |
| `obs_ws_password` | `OBS_WS_PASSWORD` | `""` | `str` | `app.py` | Password for OBS WebSocket authentication. |
| `obs_stream_status_poll_interval` | `OBS_STREAM_POLL_INTERVAL` | `2.0` | `float` | `app.py` | Interval (seconds) to poll stream state and scene name. |
| `obs_connect_timeout` | `OBS_CONNECT_TIMEOUT` | `0.2` | `float` | `app.py` | Timeout (seconds) for non-blocking TCP socket probe. |
| `obs_retry_interval_sec` | `OBS_RETRY_INTERVAL` | `5.0` | `float` | `app.py` | Delay (seconds) before reconnecting after connection loss. |
| `obs_celebrate_source_name` | `OBS_CELEBRATE_SOURCE` | `"Celebration FX"` | `str` | `app.py` | Name of OBS source to enable during celebrations. |
| `obs_celebrate_duration_sec` | `OBS_CELEBRATE_DURATION` | `5.0` | `float` | `app.py` | Duration (seconds) of celebration overlay activation. |
| `obs_celebrate_filter_name` | `OBS_CELEBRATE_FILTER` | `""` | `str` | `app.py` | Optional OBS filter name for celebration animations. |

---

## 3. YouTube Live Chat & Viewers

| Field Name | Env Variable | Default Value | Type | Readers | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `youtube_api_key` | `YOUTUBE_API_KEY` | `""` | `str` | `app.py` | YouTube Data API v3 key for viewer counts and chat polling. |
| `youtube_video_id` | `YOUTUBE_VIDEO_ID` | `""` | `str` | `app.py` | Live broadcast video ID. |
| `chat_poll_interval` | `CHAT_POLL_INTERVAL` | `0.5` | `float` | `app.py` | Live chat polling frequency (seconds). |
| `viewer_count_poll_interval` | `VIEWER_POLL_INTERVAL` | `20.0` | `float` | `app.py` | Active stream viewer count polling frequency (seconds). |
| `viewer_0_poll_interval` | `VIEWER_0_POLL_INTERVAL` | `5.0` | `float` | `app.py` | Faster viewer poll interval when 0 viewers are detected. |
| `auto_track_live_viewers` | `AUTO_TRACK_LIVE_VIEWERS` | `True` | `bool` | `app.py` | Automatically poll concurrent viewer count from YouTube API. |
| `chat_idle_timeout_sec` | `CHAT_IDLE_TIMEOUT_SEC` | `120.0` | `float` | `app.py` | Seconds of chat inactivity before declaring chat idle. |

---

## 4. Gemini AI Brain & Persona

| Field Name | Env Variable | Default Value | Type | Readers | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `gemini_api_key` | `GEMINI_API_KEY` | `""` | `str` | `ai_brain.py` | Google Gemini API Key. |
| `gemini_model` | `GEMINI_MODEL` | `"gemini-3.7-flash"` | `str` | `ai_brain.py`, `app.py` | Primary fast LLM model for conversational stream turns. |
| `gemini_thinking_level` | `GEMINI_THINKING_LEVEL` | `"LOW"` | `str` | `ai_brain.py` | Thinking effort level (`"LOW"`, `"HIGH"`). |
| `gemini_fast_thinking_budget` | `GEMINI_FAST_THINKING_BUDGET` | `0` | `int` | `ai_brain.py` | Thinking budget (tokens) for fast conversational turns (0 for instant). |
| `gemini_deep_thinking_budget` | `GEMINI_DEEP_THINKING_BUDGET` | `512` | `int` | `ai_brain.py` | Thinking budget (tokens) for complex or philosophical questions. |
| `gemini_deep_model` | `GEMINI_DEEP_MODEL` | `None` | `Optional[str]` | `ai_brain.py` | Optional fallback model for deep contemplation turns. |
| `gemini_max_output_tokens` | `GEMINI_MAX_OUTPUT_TOKENS` | `1024` | `int` | `ai_brain.py` | Maximum generation tokens per LLM completion. |
| `gemini_temperature` | `GEMINI_TEMPERATURE` | `0.7` | `float` | `ai_brain.py` | LLM sampling temperature. |
| `gemini_top_p` | `GEMINI_TOP_P` | `0.9` | `float` | `ai_brain.py` | Top-p nucleus sampling cutoff. |
| `ai_host_name` | `AI_HOST_NAME` (or `AI_COHOST_NAME`) | `"I Am"` | `str` | `ai_brain.py`, `app.py`, `config.py` | Persona display name for the AI host. |
| `ai_system_prompt` | `AI_SYSTEM_PROMPT` | (Full Persona) | `str` | `ai_brain.py` | System prompt instruction directing tone, brevity, and mood tags. |
| `trigger_words` | `TRIGGER_WORDS` | (Keyword list) | `List[str]` | `app.py` | Direct address keyword triggers for live chat. |
| `celebrate_aliases` | — | (Alias list) | `List[str]` | `app.py` | Aliases that trigger celebration FX (`!celebrate`, etc.). |
| `min_interjection_interval_sec`| `MIN_INTERJECTION_INTERVAL_SEC`| `5.0` | `float` | `app.py` | Minimum cooldown between consecutive conversational interjections. |
| `auto_chat_response_probability`| `AUTO_CHAT_RESPONSE_PROB` | `0.60` | `float` | `app.py` | Probability of answering general questions in active chat. |
| `chat_sampling_viewer_threshold`| `CHAT_SAMPLING_VIEWER_THRESHOLD`| `25` | `int` | `app.py` | Concurrent viewer threshold above which probabilistic sampling engages. |
| `chat_sampling_probability` | `CHAT_SAMPLING_PROBABILITY` | `0.35` | `float` | `app.py` | Reduced response probability during high-traffic chat floods. |
| `cast_badge_label` | `CAST_BADGE_LABEL` | `"CAST"` | `str` | `visualizer.py` | Badge label rendered next to synthetic cast members. |
| `chat_reader_mode` | `CHAT_READER_MODE` | `False` | `bool` | `app.py` | Strict chat reading mode (disables spontaneous commentary). |
| `ignore_peer_replies` | `IGNORE_PEER_REPLIES` | `True` | `bool` | `app.py` | Suppresses responses when viewers tag each other in chat. |
| `greet_new_chatters` | `GREET_NEW_CHATTERS` | `True` | `bool` | `app.py` | Greets first-time chatters when they post their first message. |
| `greet_viewer_joins` | `GREET_VIEWER_JOINS` | `False` | `bool` | `app.py` | Pre-synthesizes and plays greetings when viewer count increments. |
| `viewer_join_cooldown_sec` | `VIEWER_JOIN_COOLDOWN_SEC` | `120.0` | `float` | `app.py` | Cooldown between viewer join greeting audio events. |
| `chat_encouragement_enabled` | `CHAT_ENCOURAGEMENT_ENABLED` | `False` | `bool` | `app.py` | Enables host call-to-action when viewers watch in silence. |
| `chat_encouragement_interval_sec`| `CHAT_ENCOURAGEMENT_INTERVAL_SEC`| `300.0` | `float` | `app.py` | Base interval for chat encouragement triggers. |
| `thank_subscribers` | `THANK_SUBSCRIBERS` | `True` | `bool` | `app.py` | Acknowledges new subscriptions on air. |

---

## 5. Token Efficiency & Engagement State Controls

| Field Name | Env Variable | Default Value | Type | Readers | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `obs_require_stream_active` | `OBS_REQUIRE_STREAM_ACTIVE` | `False` | `bool` | `app.py` | Requires OBS to be actively streaming before answering chat. |
| `min_concurrent_viewers_active`| `MIN_CONCURRENT_VIEWERS_ACTIVE`| `1` | `int` | `app.py` | Minimum viewers required to enter ACTIVE engagement mode. |
| `eco_mode_enabled` | `ECO_MODE_ENABLED` | `False` | `bool` | `app.py` | Pauses idle background generation when 0 viewers are present. |
| `max_responses_per_minute` | `MAX_RESPONSES_PER_MINUTE` | `12` | `int` | `app.py` | Rate limiter ceiling per minute. |
| `max_responses_per_hour` | `MAX_RESPONSES_PER_HOUR` | `120` | `int` | `app.py` | Rate limiter ceiling per hour. |
| `max_comment_queue_size` | `MAX_COMMENT_QUEUE_SIZE` | `5` | `int` | `app.py` | Maximum capacity of the priority comment queue. |
| `spontaneous_commentary_enabled`| `SPONTANEOUS_COMMENTARY_ENABLED`| `True` | `bool` | `app.py` | Enables spontaneous reflections during chat silence. |
| `spontaneous_require_viewers` | `SPONTANEOUS_REQUIRE_VIEWERS` | `False` | `bool` | `app.py` | Suppresses spontaneous reflections when 0 viewers are present. |
| `idle_silence_threshold_sec` | `IDLE_SILENCE_THRESHOLD_SEC` | `15.0` | `float` | `app.py` | Seconds of silence before checking spontaneous commentary eligibility. |
| `spontaneous_min_interval_sec`| `SPONTANEOUS_MIN_INTERVAL_SEC` | `35.0` | `float` | `app.py` | Base cooldown between spontaneous reflections. |
| `spontaneous_max_backoff_sec` | `SPONTANEOUS_MAX_BACKOFF_SEC` | `180.0` | `float` | `app.py` | Maximum exponential backoff ceiling during extended quiet periods. |
| `motto_phrase` | `MOTTO_PHRASE` | `"Everything is perfect."` | `str` | `visualizer.py`, `app.py` | Default motto displayed on screen during ambient state. |

---

## 6. Neural TTS Settings

| Field Name | Env Variable | Default Value | Type | Readers | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `tts_backend` | `TTS_BACKEND` | `"chatterbox"` | `str` | `tts_engine.py`, `app.py` | Primary TTS backend (`"chatterbox"` or `"edge"`). |
| `tts_server_url` | `TTS_SERVER_URL` | `"http://192.168.0.115:8123"` | `str` | `tts_engine.py` | LAN URL of Chatterbox Turbo synthesis server. |
| `tts_reference_voice` | `TTS_REFERENCE_VOICE` | `"cohost.wav"` | `str` | `tts_engine.py` | Voice reference WAV filename for Chatterbox cloning. |
| `tts_request_timeout_floor` | `TTS_REQUEST_TIMEOUT_FLOOR` | `4.0` | `float` | `tts_engine.py` | Minimum timeout for HTTP TTS synthesis requests. |
| `tts_request_timeout_ceiling` | `TTS_REQUEST_TIMEOUT_CEILING` | `30.0` | `float` | `tts_engine.py` | Maximum timeout ceiling for long synthesis requests. |
| `inter_sentence_gap_sec` | `INTER_SENTENCE_GAP_SEC` | `0.15` | `float` | `tts_engine.py` | Silence insertion (seconds) between pipelined sentences. |
| `max_concurrent_synth` | `MAX_CONCURRENT_SYNTH` | `2` | `int` | `tts_engine.py` | Semaphore limit for concurrent sentence synthesis requests. |
| `tts_exaggeration_default` | `TTS_EXAGGERATION_DEFAULT` | `0.5` | `float` | `tts_engine.py`, `app.py` | Default expressive exaggeration for Chatterbox TTS. |
| `tts_mood_exaggeration_map` | — | (Mood dict) | `Dict[str, float]` | `tts_engine.py`, `app.py` | Mapping of 12 mood tags to specific exaggeration levels. |
| `tts_voice` | `TTS_VOICE` | `"en-US-ChristopherNeural"` | `str` | `tts_engine.py`, `app.py` | Voice identifier for Microsoft Edge TTS fallback. |
| `tts_sample_rate` | `TTS_SAMPLE_RATE` | `48000` | `int` | `tts_engine.py`, `app.py`, `render_worker.py` | Master audio sample rate (48000 Hz broadcast standard). |
| `tts_pitch` | `TTS_PITCH` | `"+0Hz"` | `str` | `tts_engine.py` | Edge-TTS pitch modifier string. |
| `tts_rate` | `TTS_RATE` | `"+5%"` | `str` | `tts_engine.py` | Edge-TTS speech rate modifier string. |

---

## 7. Visualizer & Display Layout Settings

| Field Name | Env Variable | Default Value | Type | Readers | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `vox_only_mode` | `VOX_ONLY_MODE` | `False` | `bool` | `app.py`, `visualizer.py` | Keeps pinned question permanently visible without fading out during speech. |
| `visualizer_aspect_ratio` | `VISUALIZER_ASPECT_RATIO` | `"16:9"` | `str` | `config.py`, `visualizer.py` | Aspect ratio layout: `"16:9"` (horizontal) or `"9:16"` (vertical). |
| `visualizer_width` | `VISUALIZER_WIDTH` | `1920` (or `1080`) | `int` | `config.py`, `visualizer.py`, `render_worker.py`, `app.py` | Canvas width in pixels. |
| `visualizer_height` | `VISUALIZER_HEIGHT` | `1080` (or `1920`) | `int` | `config.py`, `visualizer.py`, `render_worker.py`, `app.py` | Canvas height in pixels. |
| `visualizer_window_width` | `VISUALIZER_WINDOW_WIDTH` | Auto | `Optional[int]` | `config.py`, `visualizer.py` | Pygame preview window width. |
| `visualizer_window_height` | `VISUALIZER_WINDOW_HEIGHT` | Auto | `Optional[int]` | `config.py`, `visualizer.py` | Pygame preview window height. |
| `visualizer_window_x` | `VISUALIZER_WINDOW_X` | `None` | `Optional[int]` | `visualizer.py` | OS window position X coordinate. |
| `visualizer_window_y` | `VISUALIZER_WINDOW_Y` | `None` | `Optional[int]` | `visualizer.py` | OS window position Y coordinate. |
| `visualizer_native_window` | `VISUALIZER_NATIVE_WINDOW` | `False` | `bool` | `config.py`, `visualizer.py` | Opens preview window at full 100% canvas resolution. |
| `visualizer_fps` | `VISUALIZER_FPS` | `60` | `int` | `render_worker.py`, `visualizer.py` | Target rendering frame rate (60 FPS). |
| `visualizer_headless` | `VISUALIZER_HEADLESS` | `False` | `bool` | `visualizer.py` | Runs visualizer with dummy video driver (no window). |
| `visualizer_borderless` | `VISUALIZER_BORDERLESS` | `False` | `bool` | `visualizer.py` | Borderless preview window mode. |
| `show_top_status_bar` | `SHOW_TOP_STATUS_BAR` | `False` | `bool` | `visualizer.py` | Renders developer debug overlay bar at top of visualizer. |
| `comment_fade_in_sec` | `COMMENT_FADE_IN_SEC` | `0.6` | `float` | `visualizer.py` | Fade-in animation duration for subtitle text. |
| `comment_fade_out_sec` | `COMMENT_FADE_OUT_SEC` | `1.2` | `float` | `visualizer.py` | Fade-out animation duration for subtitle text. |
| `comment_post_speech_hold_sec` | `COMMENT_POST_SPEECH_HOLD_SEC` | `15.0` | `float` | `app.py` | Seconds to hold question/answer card on screen after speech completes. |
| `comment_active_queue_hold_sec`| `COMMENT_ACTIVE_QUEUE_HOLD_SEC`| `2.5` | `float` | `app.py` | Reduced hold duration when pending comments are queued. |
| `reflection_post_speech_chat_delay_sec` | `REFLECTION_POST_SPEECH_CHAT_DELAY_SEC` | `3.0` | `float` | `app.py` | Peaceful stillness duration after spontaneous reflection before next turn. |
| `question_fade_in_sec` | `QUESTION_FADE_IN_SEC` | `0.80` | `float` | `visualizer.py`, `app.py` | Pinned question fade-in animation duration. |
| `question_fade_out_sec` | `QUESTION_FADE_OUT_SEC` | `0.80` | `float` | `visualizer.py`, `app.py` | Pinned question fade-out animation duration. |
| `question_min_display_sec` | `QUESTION_MIN_DISPLAY_SEC` | `2.0` | `float` | `app.py` | Minimum hold time before fading out pinned question preview. |
| `question_read_word_rate_sec` | `QUESTION_READ_WORD_RATE_SEC` | `0.25` | `float` | `app.py` | Dynamic reading hold per word of question text. |
| `motto_pre_fade_in_sec` | `MOTTO_PRE_FADE_IN_SEC` | `0.0` | `float` | `visualizer.py` | Pause duration between subtitle dissolve and motto emergence. |
| `motto_fade_in_sec` | `MOTTO_FADE_IN_SEC` | `1.4` | `float` | `visualizer.py` | Motto fade-in animation duration. |
| `motto_fade_out_sec` | `MOTTO_FADE_OUT_SEC` | `0.6` | `float` | `visualizer.py` | Motto fade-out animation duration. |

---

## 8. Promotional Overlays

| Field Name | Env Variable | Default Value | Type | Readers | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `promo_overlay_enabled` | `PROMO_OVERLAY_ENABLED` | `True` | `bool` | `app.py`, `visualizer.py` | Master switch for on-screen graphic callouts. |
| `promo_mode` | `PROMO_MODE` | `"event"` | `str` | `app.py` | Promo scheduling mode (`"event"` or `"timer"`). |
| `promo_ask_quiet_sec` | `PROMO_ASK_QUIET_SEC` | `45.0` | `float` | `app.py` | Chat silence required before showing "Ask Anything" callout. |
| `promo_sub_after_turn_sec` | `PROMO_SUB_AFTER_TURN_SEC` | `3.0` | `float` | `app.py` | Time window after a completed interaction to show "Like & Subscribe". |
| `promo_sub_min_interval_sec` | `PROMO_SUB_MIN_INTERVAL_SEC` | `300.0` | `float` | `app.py` | Minimum cooldown between "Like & Subscribe" callouts. |
| `promo_overlay_interval_sec` | `PROMO_OVERLAY_INTERVAL_SEC` | `75.0` | `float` | `visualizer.py` | Periodic interval when using timer mode. |
| `promo_overlay_duration_sec` | `PROMO_OVERLAY_DURATION_SEC` | `10.0` | `float` | `visualizer.py` | On-screen display duration for promotional graphics. |
| `promo_overlay_entrance_sec` | `PROMO_OVERLAY_ENTRANCE_SEC` | `0.9` | `float` | `visualizer.py` | Promo slide-in animation duration. |
| `promo_overlay_exit_sec` | `PROMO_OVERLAY_EXIT_SEC` | `1.15` | `float` | `visualizer.py` | Promo slide-out animation duration. |
| `promo_overlay_hover_amp` | `PROMO_OVERLAY_HOVER_AMP` | `4.5` | `float` | `visualizer.py` | Subtle floating hover oscillation amplitude (pixels). |

---

## 9. Audio Sinks & OS Priority

| Field Name | Env Variable | Default Value | Type | Readers | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `local_audio_enabled` | `LOCAL_AUDIO_ENABLED` | `True` | `bool` | `app.py`, `tts_engine.py` | Enables Windows WASAPI / DirectSound audio monitor. |
| `local_audio_device` | `LOCAL_AUDIO_DEVICE` | `None` | `Optional[str]` | `app.py` | Substring match for audio output device (or `None` for default). |
| `local_audio_volume` | `LOCAL_AUDIO_VOLUME` | `1.0` | `float` | `app.py` | Master volume multiplier for local audio playback. |
| `local_audio_latency` | `LOCAL_AUDIO_LATENCY` | `"high"` | `str` | `app.py` | PortAudio latency mode (`"high"` prevents underruns on Windows). |
| `process_priority` | `PROCESS_PRIORITY` | `"above_normal"` | `str` | `app.py` | Windows OS process priority class (`"above_normal"` or `"high"`). |

---

## 10. NDI Streamer Settings

| Field Name | Env Variable | Default Value | Type | Readers | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `ndi_stream_name` | `NDI_STREAM_NAME` | `"AI_COHOST_FEED"` | `str` | `app.py`, `ndi_streamer.py`, `render_worker.py` | NDI source name broadcast on LAN for OBS Studio. |
| `ndi_audio_enabled` | `NDI_AUDIO_ENABLED` | `True` | `bool` | `app.py`, `render_worker.py` | Master switch for NDI audio channel broadcasting. |

---

## 11. Hardware Performance Profile

| Field Name | Env Variable | Default Value | Type | Readers | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `performance_mode` | `PERFORMANCE_MODE` | `"balanced"` | `str` | `visualizer.py` | Graphics profile (`"ultra"`, `"balanced"`, `"eco_low_spec"`). |
| `low_spec_mode` | `LOW_SPEC_MODE` | `False` | `bool` | `visualizer.py` | Enables lightweight shader passes for integrated GPUs. |
| `visualizer_particle_count` | `VISUALIZER_PARTICLE_COUNT` | `70` | `int` | `visualizer.py` | Total ambient particle count in background visualization. |

---

## 12. Session Logging Subsystem

| Field Name | Env Variable | Default Value | Type | Readers | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `session_logging_enabled` | `SESSION_LOGGING_ENABLED` | `True` | `bool` | `app.py`, `session_logger.py` | Structured JSONL session event logging switch. |
| `session_log_dir` | `SESSION_LOG_DIR` | `"logs/sessions"` | `str` | `session_logger.py` | Output directory for structured session logs. |

---

## 13. Synthetic Cast Subsystem

| Field Name | Env Variable | Default Value | Type | Readers | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `cast_enabled` | `CAST_ENABLED` | `True` | `bool` | `app.py` | Master switch for synthetic cast ensemble questions. |
| `cast_require_viewers` | `CAST_REQUIRE_VIEWERS` | `False` | `bool` | `app.py` | Suppresses cast questions in ECO / Standby mode (0 viewers). |
| `cast_min_interval_sec` | `CAST_MIN_INTERVAL_SEC` | `70.0` | `float` | `app.py` | Minimum interval between synthetic cast questions. |
| `cast_max_interval_sec` | `CAST_MAX_INTERVAL_SEC` | `130.0` | `float` | `app.py` | Maximum interval before scheduling next synthetic cast question. |
| `cast_quiet_chat_threshold_sec` | `CAST_QUIET_CHAT_THRESHOLD_SEC` | `40.0` | `float` | `app.py` | Seconds of chat silence before a cast question is triggered. |
| `cast_max_per_session` | `CAST_MAX_PER_SESSION` | `50` | `int` | `app.py` | Maximum synthetic cast questions per livestream session. |

---

## 14. Reflection & Greeting Caches

| Field Name | Env Variable | Default Value | Type | Readers | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `reflection_cache_enabled` | `REFLECTION_CACHE_ENABLED` | `True` | `bool` | `app.py`, `ai_brain.py` | Background pre-generation of spontaneous reflections. |
| `reflection_cache_size` | `REFLECTION_CACHE_SIZE` | `4` | `int` | `app.py`, `ai_brain.py` | Maximum pre-generated reflections held in cache. |
| `greeting_cache_enabled` | `GREETING_CACHE_ENABLED` | `True` | `bool` | `app.py`, `greeting_cache.py` | Background pre-synthesis of welcome greetings with audio. |
| `greeting_cache_size` | `GREETING_CACHE_SIZE` | `3` | `int` | `app.py`, `greeting_cache.py` | Maximum pre-synthesized greetings held in cache. |
| `greeting_cache_poll_interval_sec` | `GREETING_CACHE_POLL_INTERVAL_SEC` | `15.0` | `float` | `app.py`, `greeting_cache.py` | Idle poll interval for greeting cache replenishment worker. |
