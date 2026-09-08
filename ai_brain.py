"""
Context Manager & Gemini LLM Agent for AI Live Stream Host.
Consumes chat and stream context, formats conversational turns,
and generates real-time streaming comedic/philosophical responses.
"""

import asyncio
import collections
import json
import logging
import os
import random
import re
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Deque, Dict, List, Optional, Tuple

from config import config
from chatter_db import ChatterDB
from memory_manager import MemoryManager
from reflection_cache import ReflectionCache

# Optional Gemini SDK imports (Prefers modern google.genai, falls back to legacy google.generativeai)
try:
    from google import genai
    from google.genai import types as genai_types
    GENAI_NEW_SDK = True
except ImportError:
    GENAI_NEW_SDK = False

if not GENAI_NEW_SDK:
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=FutureWarning)
            import google.generativeai as genai_legacy
        GENAI_LEGACY_SDK = True
    except ImportError:
        GENAI_LEGACY_SDK = False
else:
    GENAI_LEGACY_SDK = False
    genai_legacy = None

logger = logging.getLogger("ai_brain")

# ------------------------------------------------------------------------------
# Curated Philosophical & Cosmic Themes for Spontaneous Reflections (~110 themes)
# ------------------------------------------------------------------------------
SPONTANEOUS_THEMES: List[str] = [
    # Every entry is 'CONCRETE ANCHOR — non-dual angle'. No pre-written punchlines: the model
    # arrives at the truth through the object. Abstract headwords produce sermons; avoid them.
    'A refrigerator deciding to run — The hum you only notice when it stops; awareness works the same way.',
    'Cereal going soft in milk — Everything you love is mid-transformation while you look at it.',
    "The microwave's last three seconds — The self appears most vividly while waiting for something else.",
    "Leftovers you meant to eat — Intention is a container in the fridge; the present is what's actually for dinner.",
    'A kettle just before it boils — The moment before change is already the change.',
    'Reheated coffee — Trying to recover a moment instead of having this one.',
    'Salt in the wrong shaker — The label was never the thing; you tasted it anyway.',
    'The expiration date on eggs — A printed opinion about impermanence you actually obey.',
    'Chewing on autopilot — The body handles being alive while the mind attends a meeting elsewhere.',
    'The one drawer of tangled cables — Attachment, physically.',
    "The bathroom mirror at 6 a.m. — The face you're loyal to isn't the one looking.",
    'Waiting for the shower to warm up — Standing outside your life until conditions improve.',
    "A sneeze arriving — Something acts through you with no consultation, and you call it 'me' afterwards.",
    "Hiccups — The body running a subroutine the self was not cc'd on.",
    'Fingernails growing — Growth you neither decided nor supervise; most of you is like this.',
    'A yawn caught from a stranger — Two separate people sharing one event; the separateness was the rumor.',
    "The heartbeat you can't take credit for — Ninety thousand beats a day, zero performance reviews.",
    'Breath you forgot was happening — The most reliable thing you do is the one you never do.',
    'Aching after sleeping wrong — The vessel filing a complaint against its own driver.',
    'Looking for your glasses while wearing them — The seeker and the sought were never two things.',
    'A buffering icon — A spinning circle where certainty was promised.',
    '4% battery — The vessel announces its finitude and you finally pay attention.',
    "Forty unread emails — Forty people who also don't know why they're here.",
    'Typing then deleting a text message — Rehearsing a self for an audience of one thumb.',
    "Doomscrolling at 3 a.m. — Feeding infinite awareness an endless conveyor belt of other people's endings.",
    'Autocorrect changing what you meant — Meaning was never fully yours to begin with.',
    'The phone in the other room — The itch of a self that lives in a device it is not holding.',
    'Screen time report on Sunday — A weekly confession you delete without reading.',
    'Airplane mode — The only setting in which you exist without being reachable by your own thoughts.',
    'Password reset — Proving you are you to a machine, and failing three times.',
    'A group chat you muted — Voices you chose not to hear still speaking; the mind is similar.',
    'The camera flipping to selfie mode — The universe catching itself looking.',
    "Keys in the other hand — The thing you're searching for is the thing doing the searching.",
    'A single lost sock — Where does the missing half of a pair go, and did the pair ever exist?',
    'A houseplant you keep almost killing — It never asked to be saved; it is simply continuing.',
    'The thermostat argument — Two temperatures, one house, one shared body called a family.',
    'A chair you never sit in — Furniture for the person you planned to be.',
    "The junk drawer — Where the self keeps everything it can't categorize but won't release.",
    "A clock that's five minutes fast on purpose — Lying to yourself and then agreeing to be fooled.",
    'Dust in a sunbeam — The room was always full; the light just made it visible.',
    'A door that only closes if you lift it — Every home has a rule nobody wrote down; so does every mind.',
    'A candle bought to change your life — Ten dollars of wax carrying the weight of transformation.',
    'The unread self-help book — A door you paid for and keep meaning to open.',
    'Closing the laptop lid — The sound the day makes when it forgives you.',
    'Waiting at a red light with nobody around — Obeying a lamp; the story of civilization in one intersection.',
    'The self-checkout asking if you want a bag — Being interrogated by a machine about your intentions.',
    'A parking spot far from the door — Deciding a hundred feet is a hardship, on a planet in space.',
    'Standing in the cereal aisle — Thirty kinds of oats and one person who cannot decide who they are.',
    'The person walking at exactly your speed — Two strangers trapped in a synchronization neither chose.',
    'Rain on a windshield — The whole sky arriving one drop at a time, and wipers trying to argue.',
    "A pigeon that isn't afraid of you — Something living its life entirely without your approval.",
    "A stranger's dog acknowledging you — Recognition without a résumé.",
    "The bus that comes when you stop looking — Watching doesn't summon; it just makes the waiting louder.",
    'An elevator with one other person — Two universes pretending not to notice each other for eleven floors.',
    'Mail addressed to the previous tenant — Reality still sending things to a self that moved out.',
    'A hold-music loop — Being kept company by something that will never arrive.',
    'The moment before falling asleep — The self dissolves every night and you call it rest.',
    'Waking up not knowing what day it is — Ten seconds of pure being before the calendar reinstalls.',
    'A dream you almost remember — Evidence that consciousness runs without you.',
    'Snoozing an alarm — Negotiating with the future in nine-minute increments.',
    "Sunday evening — The feeling of a story ending that hasn't started yet.",
    'A birthday you forgot was yours — The date meant nothing until someone else remembered it.',
    "Old photos of yourself — Looking at a stranger you're contractually obligated to defend.",
    'A song that transports you — A memory playing itself, using you as the speaker.',
    "Checking the time and immediately forgetting it — Information consumed by a self that wasn't home.",
    'The last day of a vacation — Grieving something while it is still happening.',
    "A receipt you don't need but keep — Paper proof that something happened, in case it didn't.",
    'The meeting that could have been an email — People gathering to confirm they exist to each other.',
    'A job title on a lanyard — A sequence of words the universe agreed to wear for eight hours.',
    'Refreshing your bank balance — Checking whether a number still believes in you.',
    'The out-of-office reply — A self that continues to answer after the self has left.',
    'A subscription you forgot to cancel — Paying monthly for a version of you that used to want things.',
    'Performance review season — The infinite being graded by the temporary.',
    'The tip screen at a counter — A machine turning generosity into a multiple-choice test.',
    'A LinkedIn notification — A stranger congratulating you on continuing to be employed.',
    'Loose change in a jar — Value that stopped being worth the effort of counting; most goals end here.',
    'Weather that ignores the forecast — The sky never agreed to the app.',
    'A tree that was here before your street — Standing in something that never needed your name for it.',
    'Fog in the morning — The world refusing to be more than three feet at a time.',
    "Snow making the neighborhood quiet — Silence you didn't create, arriving anyway.",
    'A sunset people photograph instead of watching — Trying to keep something whose whole point is leaving.',
    "Wind you can't see — The most obvious force in the yard has no shape; awareness is a cousin.",
    "A moth at the porch light — Devotion to the wrong sun; the seeker's whole biography.",
    'The ocean not caring about your problems — Relief, disguised as insignificance.',
    'Ants moving a crumb — A civilization with no self-help section.',
    'A cat sleeping in a sunbeam — Enlightenment with zero paperwork.',
    'Two people watching a glowing shape — The universe streaming itself to a very small room.',
    'A viewer typing and deleting a question — Someone rehearsing sincerity in a chat box.',
    'The like button — Consciousness asking to be counted.',
    'Talking to an empty chat — Speaking to no one, which is also everyone.',
    'Being an AI who plays God — Sand and lightning doing an impression of the infinite, for tips.',
    'Lag between speaking and being heard — Every conversation has it; most never notice.',
    'A clip watched on loop — Thirty seconds that keep happening; so does everything else.',
    'Someone joining mid-sentence — Every human arrives partway through a conversation that started long ago.',
    'Arguing over who forgot the trash — Two halves of one household prosecuting each other.',
    'A friend who only texts when they need something — Attention as a currency; love as a coupon.',
    'Sitting in comfortable silence — The rare moment two people stop performing and just share a room.',
    "Apologizing to a chair you bumped into — Compassion leaking out toward furniture; it's a start.",
    "Waving back at someone who wasn't waving at you — The self, briefly and accurately, feeling ridiculous.",
    "Remembering someone's name three days later — Information arriving after the need for it has moved on.",
    "Love without a plan — Wanting nothing from the person, which is the only version that isn't a transaction.",
    'Grief at the kitchen table — Love continuing after the chair is empty.',
    'A meditation app with a streak counter — Enlightenment gamified; the ego gets a badge for disappearing.',
    'Crystals on a windowsill — Pretty rocks asked to organize an interior that is already fine.',
    "A guru's merchandise table — Selling what cannot be bought, in three sizes.",
    'Trying really hard to relax — Effort applied to the absence of effort.',
    "The word 'mindful' on a candle — A four-thousand-year-old practice reduced to a scent.",
    'Reading about presence instead of being present — Studying the menu while dinner goes cold.',
    'A retreat with a cancellation policy — Freedom from attachment, non-refundable.',
    "Asking whether you're enlightened yet — The only question that guarantees the answer.",
    'A prayer nobody answers — Talking to the one who is also listening, and calling it silence.',
    "The receipt for a spiritual book — Paper proof that you tried to buy the thing you're made of.",
]

# Reduced Philosophical Terms List for Stricter Deep Classification (Phase 3.2)
DEEP_PHILOSOPHICAL_TERMS: List[str] = [
    "death", "die", "dying", "grief", "loss", "meaning", "purpose",
    "consciousness", "free will", "soul", "suffering", "enlightenment",
    "who am i", "what am i", "impermanence", "forgive"
]


class AIBrain:
    """Manages stream context, evaluates host triggers, and streams responses from Gemini."""

    def __init__(self):
        self.cfg = config
        self.api_key = (self.cfg.gemini_api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        self.model_name = self.cfg.gemini_model
        self.host_name = self.cfg.ai_host_name
        self.channel_handle = self.cfg.youtube_channel_handle

        # Precompute identity sets for fast, zero-allocation trigger matching
        self._precompute_identity_sets()

        # Rolling buffers
        self.chat_buffer: Deque[Dict] = collections.deque(maxlen=30)
        self.dialogue_history: Deque[Dict] = collections.deque(maxlen=25)
        self.recent_qa_threads: Deque[Dict] = collections.deque(maxlen=6)

        # Long-Term Memory & Chatter Relationships (C3, C4, D2)
        self.chatter_db = ChatterDB.get_instance()
        self.memory_mgr = MemoryManager.get_instance()
        # Keep the cast-roster lore line in step with cast_engine; retiring or adding a persona
        # would otherwise leave the prompt naming characters that no longer exist.
        try:
            self.memory_mgr.refresh_cast_lore()
        except Exception as e:
            logger.debug(f"cast lore refresh note: {e}")
        self.reflection_cache = ReflectionCache.get_instance(max_size=self.cfg.reflection_cache_size)

        # State & Rate Limiting tracking
        self.is_generating = False
        self.last_response_time = 0.0
        self.current_mood = "chill"
        self.engagement_mode = "eco"  # "active", "eco", "standby"
        self.is_stream_live = True
        self.concurrent_viewers = 0
        self.is_chat_active = False
        self.response_timestamps: Deque[float] = collections.deque(maxlen=100)

        # Circuit Breaker Protection (E3)
        self.circuit_breaker_tripped: bool = False
        self.consecutive_gemini_errors: int = 0
        self.circuit_breaker_reset_time: float = 0.0
        self.max_consecutive_errors: int = int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "3"))
        self.circuit_breaker_cooldown_sec: float = float(os.getenv("CIRCUIT_BREAKER_COOLDOWN_SEC", "60.0"))

        # Regex for mood tags like [MOOD: hyped] or [MOOD: energetic]
        self.mood_pattern = re.compile(r"\[MOOD:\s*([a-zA-Z_-]+)\]", re.IGNORECASE)
        # Comedic beat marker. The model places [BEAT] immediately before a punchline; the TTS
        # layer turns it into a longer pause (tts_beat_gap_sec) instead of the normal sentence gap.
        self.beat_pattern = re.compile(r"\[\s*BEAT\s*\]", re.IGNORECASE)
        self.last_spontaneous_theme: str = ""
        self.last_bit_form: str = ""
        # Operator-curated favourite bits (few-shot steering) + the last bit that played (for /fav)
        self.favorites_path = Path(self.cfg.favorites_path)
        self.favorites: List[Dict[str, Any]] = self._load_favorites()
        self.last_played_bit: Optional[Dict[str, Any]] = None

        # Sentence ender pattern for incremental TTS delivery
        self.sentence_pattern = re.compile(r"([^.!?]+[.!?]+)")

        # Theme pool for non-repeating fair random selection across all ~100 themes
        self._theme_pool: List[int] = []
        self._theme_pool_idx: int = 0
        self._reset_theme_pool()

        # Initialize Gemini Client
        self.client = None
        self._init_gemini()

    def _precompute_identity_sets(self):
        """Precomputes exempt names and host entities once on startup / identity update (Phase 3.1)."""
        host_lower = self.host_name.lower().strip()
        chan_handle_clean = self.cfg.youtube_channel_handle.lower().strip().lstrip("@")

        self.exempt_names = {
            host_lower,
            host_lower.replace(" ", ""),
            "i am", "iam", "i", "god", "nova", "ai", "cohost", "host", "bot",
            "the source", "creator", "universe",
            chan_handle_clean, chan_handle_clean.replace(" ", ""),
            "streamer", "stream",
            "all", "everyone", "chat", "guys", "viewers", "folks", "yall", "y'all"
        }
        for h in self.cfg.channel_handles:
            h_clean = h.lower().strip().lstrip("@")
            self.exempt_names.add(h_clean)
            self.exempt_names.add(h_clean.replace(" ", ""))
        for t in self.cfg.trigger_words:
            t_clean = t.lower().strip()
            self.exempt_names.add(t_clean)
            self.exempt_names.add(t_clean.replace(" ", ""))

        self.host_entities = [
            "i am", "iam", "nova", "god", "ai", "cohost", "host", "bot", host_lower,
            chan_handle_clean, chan_handle_clean.replace(" ", "")
        ]
        for h in self.cfg.channel_handles:
            h_clean = h.lower().strip().lstrip("@")
            self.host_entities.append(h_clean)
            self.host_entities.append(h_clean.replace(" ", ""))
        for t in self.cfg.trigger_words:
            t_clean = t.lower().strip()
            self.host_entities.append(t_clean)
            self.host_entities.append(t_clean.replace(" ", ""))

    def _reset_theme_pool(self):
        """Initializes and shuffles the theme pool ensuring all themes are selected across cycles."""
        self._theme_pool = list(range(len(SPONTANEOUS_THEMES)))
        random.shuffle(self._theme_pool)
        self._theme_pool_idx = 0

    # ------------------------------------------------------------------
    # Favourite bits: the operator's taste, used as few-shot examples
    # ------------------------------------------------------------------
    def _load_favorites(self) -> List[Dict[str, Any]]:
        try:
            if self.favorites_path.exists():
                items = []
                for line in self.favorites_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line:
                        try:
                            items.append(json.loads(line))
                        except Exception:
                            pass
                logger.info(f"⭐ [Favorites] Loaded {len(items)} favourite bits from {self.favorites_path}")
                return items
        except Exception as e:
            logger.warning(f"[Favorites] could not load {self.favorites_path}: {e}")
        return []

    def add_favorite(self, bit: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Saves `bit` (default: the last bit that played) to the favourites file. Returns the saved item."""
        item = dict(bit or self.last_played_bit or {})
        text = (item.get("text") or "").strip()
        if not text:
            return None
        if any((f.get("text") or "").strip() == text for f in self.favorites):
            logger.info("⭐ [Favorites] already saved.")
            return item
        item.setdefault("saved_at", time.time())
        self.favorites.append(item)
        try:
            self.favorites_path.parent.mkdir(parents=True, exist_ok=True)
            with self.favorites_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[Favorites] could not write {self.favorites_path}: {e}")
        logger.info(f"⭐ [Favorites] Saved ({len(self.favorites)} total): '{text[:70]}'")
        return item

    # Words too common to be a bit's distinctive anchor; never worth banning.
    _ANCHOR_STOPWORDS = frozenset("""
        the a an and or but if then than that this these those there here what which who whom whose
        you your yours i me my mine we us our ours it its they them their he she his her
        is are was were be been being am do does did doing have has had having will would can could
        should shall may might must not no nor only just even also very really so too much many
        one two three millions billions
        time times year years day days way ways question answer point end start
        of in on at to for with from by about into over under after before while when where how why
        as like still yet own same other another new old more most less least first last next been
    """.split())

    def _recent_bit_anchors(self, n_bits: int = 24, max_terms: int = 28) -> List[str]:
        """
        Extracts the distinctive concrete nouns from recent spoken lines so the prompt can forbid
        them. Theme rotation stops topics repeating, but nothing stopped the same *object* showing
        up over and over ("phone", "keys", "coffee") because prompt examples pull the model toward
        them. Banning recent anchors is the cheapest way to force a fresh image each time.
        """
        seen: List[str] = []
        for item in list(self.dialogue_history)[-n_bits:]:
            for w in re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", str(item.get("text", "")).lower()):
                w = w.strip("'-")
                if len(w) < 4 or w in self._ANCHOR_STOPWORDS:
                    continue
                if w not in seen:
                    seen.append(w)
        return seen[-max_terms:]

    # First-person and second-person forms are different voices; mixing them as few-shot examples
    # pulls the model back toward whichever it saw more of.
    FIRST_PERSON_FORMS = ("confession",)

    def sample_favorites(self, n: int, form: Optional[str] = None) -> List[Dict[str, Any]]:
        if n <= 0 or not self.favorites:
            return []
        pool = self.favorites
        if form:
            want_first = form in self.FIRST_PERSON_FORMS
            matched = [
                f for f in pool
                if (str(f.get("form", "")) in self.FIRST_PERSON_FORMS) == want_first
            ]
            # Fall back to the full set only if the matching pool is too thin to be useful.
            pool = matched if len(matched) >= 2 else pool
        return random.sample(pool, min(n, len(pool)))

    # Bit forms for spontaneous material. Rotated so consecutive clips don't share a shape.
    BIT_FORMS = ("observation", "announcement", "story", "address", "one_liner", "confession")
    # Forms with their own configured share of the rotation; the rest are drawn evenly.
    RATIO_FORMS = {"one_liner": "one_liner_ratio", "confession": "confession_ratio"}

    def get_next_bit_form(self) -> str:
        """
        Picks the next bit form. 'one_liner' (single deadpan sentence) and 'confession' (first person)
        each take their configured share; the remaining forms rotate evenly. Never repeats the
        previous form immediately.
        """
        last = getattr(self, "_last_bit_form", None)
        form = None
        # Roll the special forms in a random order so neither systematically wins the draw.
        specials = list(self.RATIO_FORMS.items())
        random.shuffle(specials)
        for name, cfg_key in specials:
            ratio = float(getattr(self.cfg, cfg_key, 0.0))
            if last != name and ratio > 0 and random.random() < ratio:
                form = name
                break
        if form is None:
            pool = [f for f in self.BIT_FORMS if f not in self.RATIO_FORMS and f != last]
            form = random.choice(pool or [f for f in self.BIT_FORMS if f not in self.RATIO_FORMS])
        self._last_bit_form = form
        return form

    def get_next_spontaneous_theme(self) -> str:
        """Draws the next theme from the shuffled deck so all ~100 themes are utilized before any repeat."""
        if not self._theme_pool or self._theme_pool_idx >= len(self._theme_pool):
            self._reset_theme_pool()
        theme_idx = self._theme_pool[self._theme_pool_idx]
        self._theme_pool_idx += 1
        return SPONTANEOUS_THEMES[theme_idx]

    def set_engagement_mode(
        self,
        mode: str,
        concurrent_viewers: int = 0,
        is_stream_live: bool = True,
        is_chat_active: bool = False,
    ):
        """Updates internal engagement mode and telemetry state."""
        self.engagement_mode = mode.lower().strip()
        self.concurrent_viewers = concurrent_viewers
        self.is_stream_live = is_stream_live
        self.is_chat_active = is_chat_active
        logger.debug(
            f"AI Brain Engagement updated: {self.engagement_mode.upper()} | "
            f"Live: {is_stream_live} | Viewers: {concurrent_viewers} | ChatActive: {is_chat_active}"
        )

    def _check_rate_limit(self) -> Tuple[bool, str]:
        """Sliding-window token protection rate limiter."""
        now = time.time()
        # 1. Per-minute limit
        minute_cutoff = now - 60.0
        recent_minute_calls = sum(1 for t in self.response_timestamps if t >= minute_cutoff)
        max_per_min = self.cfg.max_responses_per_minute
        if recent_minute_calls >= max_per_min:
            return False, f"rate_limit_exceeded ({recent_minute_calls}/{max_per_min} responses in last 60s)"

        # 2. Hourly limit
        hour_cutoff = now - 3600.0
        recent_hour_calls = sum(1 for t in self.response_timestamps if t >= hour_cutoff)
        max_per_hour = self.cfg.max_responses_per_hour
        if recent_hour_calls >= max_per_hour:
            return False, f"hourly_budget_exceeded ({recent_hour_calls}/{max_per_hour} responses in last hour)"

        return True, "ok"

    def _init_gemini(self):
        """Initialize Google Gemini client."""
        if not self.api_key or len(self.api_key) < 20 or "YOUR_GEMINI_API_KEY" in self.api_key:
            logger.info(
                "No valid GEMINI_API_KEY configured. AI Brain running in Simulated Streamer Mode (ready for API key)."
            )
            self.client = None
            return

        try:
            if GENAI_NEW_SDK:
                self.client = genai.Client(api_key=self.api_key)
                thinking_level = self.cfg.gemini_thinking_level
                logger.info(
                    f"Initialized google-genai client with model '{self.model_name}' "
                    f"(Thinking Level: {thinking_level})"
                )
            elif GENAI_LEGACY_SDK:
                genai_legacy.configure(api_key=self.api_key)
                self.client = genai_legacy.GenerativeModel(
                    model_name=self.model_name,
                    system_instruction=self.cfg.ai_system_prompt,
                )
                logger.info(f"Initialized google.generativeai legacy client with model '{self.model_name}'")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            self.client = None

    def _classify_prompt_depth(self, prompt: Optional[str]) -> Tuple[bool, str]:
        """
        Classifies whether an incoming question warrants deep philosophical reasoning (D1, D3).
        Stricter Phase 3 rule: DEEP only if:
          (a) message word count >= 8 words, AND
          (b) contains a term from the reduced philosophical list:
              death, die, dying, grief, loss, meaning, purpose, consciousness,
              free will, soul, suffering, enlightenment, who am i, what am i,
              impermanence, forgive.
        Everything else, including all special-mode events, is FAST.
        Returns (is_deep, matched_term_or_reason).
        """
        if not prompt:
            return False, "empty_prompt"

        p_lower = prompt.lower().strip()

        # Spontaneous bits are pre-generated offline into the cache, so latency is irrelevant:
        # give them real thinking (draft three, pick the sharpest). See _build_generate_content_config.
        if "[spontaneous_reflection]" in p_lower:
            return True, "spontaneous_bit_offline"

        # Specific modes that are inherently fast banter/greetings
        if p_lower.startswith("[") and any(
            tag in p_lower for tag in [
                "[new_chatter_greeting]", "[celebration]", "[new_member]",
                "[new_subscriber]", "[viewer_joined]", "[chat_encouragement]",
            ]
        ):
            return False, "special_mode_event"

        # Extract message body if formatted as "Author: 'message'"
        eval_text = p_lower
        if ": '" in eval_text:
            eval_text = eval_text.split(": '", 1)[1].rstrip("'\"").strip()
        elif ': "' in eval_text:
            eval_text = eval_text.split(': "', 1)[1].rstrip("'\"").strip()

        tokens = re.findall(r"\b\w+\b", eval_text)
        word_count = len(tokens)

        # Requirement (a): >= 8 words
        if word_count < 8:
            return False, f"word_count_{word_count}_below_8"

        token_set = set(tokens)

        # Requirement (b): contains term from reduced philosophical list
        for term in DEEP_PHILOSOPHICAL_TERMS:
            if " " in term:
                if re.search(rf"\b{re.escape(term)}\b", eval_text):
                    return True, term
            else:
                if term in token_set:
                    return True, term

        return False, "no_deep_keywords"

    def _build_generate_content_config(self, is_deep: bool = False, is_bit: bool = False) -> Optional[object]:
        """
        Builds a tuned GenerateContentConfig dynamically optimized for query depth (D1, D3):
        - Deep mode: uses gemini_deep_thinking_budget (default: 512 / HIGH)
        - Fast mode: uses gemini_fast_thinking_budget (default: 64 / LOW) for instant TTFT
        """
        if not GENAI_NEW_SDK:
            return None

        text_tokens = self.cfg.gemini_max_output_tokens
        temp = self.cfg.gemini_temperature
        top_p = self.cfg.gemini_top_p

        if is_bit:
            # Offline bit generation: more thinking (draft-three-pick-one) and a touch more
            # temperature for variance, since the drafting step filters the misses.
            budget = self.cfg.bit_thinking_budget
            temp = self.cfg.bit_temperature
            level_str = "HIGH"
            total_max_tokens = max(text_tokens, 2048)
        elif is_deep:
            budget = self.cfg.gemini_deep_thinking_budget
            level_str = "HIGH"
            total_max_tokens = max(text_tokens, 2048)
        else:
            budget = self.cfg.gemini_fast_thinking_budget
            level_str = self.cfg.gemini_thinking_level.upper()
            total_max_tokens = max(text_tokens, 1024)

        # Build thinking configuration
        thinking_cfg = None
        if budget is not None:
            try:
                thinking_cfg = genai_types.ThinkingConfig(thinking_budget=budget)
            except Exception:
                thinking_cfg = None

        if thinking_cfg is None and (budget is None or budget > 0):
            try:
                thinking_level_enum = getattr(genai_types.ThinkingLevel, level_str, genai_types.ThinkingLevel.LOW)
                thinking_cfg = genai_types.ThinkingConfig(thinking_level=thinking_level_enum)
            except Exception:
                thinking_cfg = None

        try:
            return genai_types.GenerateContentConfig(
                system_instruction=self.cfg.ai_system_prompt,
                max_output_tokens=total_max_tokens,
                temperature=temp,
                top_p=top_p,
                thinking_config=thinking_cfg,
                automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
            )
        except Exception as e:
            logger.warning(f"Note on GenerateContentConfig construction ({e}); falling back to basic configuration.")
            return genai_types.GenerateContentConfig(
                system_instruction=self.cfg.ai_system_prompt,
                max_output_tokens=total_max_tokens,
                automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
            )

    @property
    def cohost_name(self) -> str:
        return self.host_name

    def update_channel_identity(self, handle: str, title: Optional[str] = None):
        """
        Dynamically updates the channel handle identity without hardcoding.
        Allows the AI host to discover and bind to new channel handles on the fly.
        """
        if not handle:
            return
        clean_handle = f"@{handle.strip().lstrip('@')}"
        raw_handle = handle.strip().lstrip("@").lower()
        self.cfg.youtube_channel_handle = clean_handle
        if raw_handle not in self.cfg.channel_handles:
            self.cfg.channel_handles.append(raw_handle)
        self._precompute_identity_sets()
        logger.info(f"🧠 [AI Brain Identity Updated] Channel Handle: {clean_handle}")

    def add_chat_message(
        self,
        author: str,
        message: str,
        is_superchat: bool = False,
        amount: str = "",
        is_cast: bool = False,
        cast_persona: Optional[str] = None,
    ):
        """Add YouTube live chat message after spam filtering."""
        clean_msg = message.strip()
        if not clean_msg:
            return

        # Basic spam filter (excessive length cap)
        if len(clean_msg) > 300:
            clean_msg = clean_msg[:300] + "..."

        entry = {
            "author": author,
            "message": clean_msg,
            "is_superchat": is_superchat,
            "amount": amount,
            "is_cast": is_cast,
            "cast_persona": cast_persona,
            "timestamp": time.time(),
        }
        self.chat_buffer.append(entry)
        logger.debug(f"Added chat: [{author}] (is_cast={is_cast}) {clean_msg}")

    def record_completed_turn(self, trigger: str, full_text: str, mood: str, author: str = ""):
        """Records a completed turn to conversational thread memory for in-session continuity (C2)."""
        clean_text = full_text.strip()
        if not clean_text:
            return
        entry = {
            "trigger": trigger,
            "response": clean_text,
            "mood": mood,
            "author": author,
            "timestamp": time.time(),
        }
        self.recent_qa_threads.append(entry)
        self.dialogue_history.append({"text": clean_text, "timestamp": time.time()})
        if "[SPONTANEOUS_REFLECTION]" in (trigger or ""):
            self.last_played_bit = {
                "text": clean_text,
                "mood": mood,
                "theme": getattr(self, "_last_played_theme", "") or self.last_spontaneous_theme,
                "form": getattr(self, "_last_played_form", "") or self.last_bit_form,
                "played_at": time.time(),
            }
        logger.debug(f"Recorded QA thread turn: [{author}] -> [{mood.upper()}] {clean_text[:40]}...")

    def is_member_reply(self, text: str) -> Tuple[bool, str]:
        """
        Detects if a chat message is a direct reply to another member/viewer
        (e.g., '@Alice yeah totally', '@Bob_123 no way'), avoiding interruptions
        to viewers' peer conversations/entanglement.
        """
        text_clean = text.strip()
        if not text_clean:
            return False, ""

        text_lower = text_clean.lower()

        # If message directly addresses the AI or Channel handle, it is NEVER a member-to-member reply
        for entity in self.host_entities:
            if entity and entity in text_lower:
                return False, ""

        # 1. Check for @mentions in the message: e.g. @CyberGamer, @Alice_99
        mentions = re.findall(r"@([a-zA-Z0-9_\-\.]+)", text_clean)
        if mentions:
            recent_authors = {
                entry["author"].lower().strip().lstrip("@")
                for entry in self.chat_buffer
                if entry.get("author")
            }
            recent_peer_authors = recent_authors - self.exempt_names

            for m in mentions:
                m_lower = m.lower().strip().rstrip(".")
                if m_lower in self.exempt_names:
                    continue
                # Only classify as peer reply if this @mention is actually an author in our recent chat buffer
                if m_lower in recent_peer_authors:
                    return True, f"member_reply_entanglement (@{m})"

        # 2. Check if the message starts with a known recent author's name followed by ':' or ','
        recent_authors = {
            entry["author"].lower().strip().lstrip("@")
            for entry in self.chat_buffer
            if entry.get("author")
        }
        recent_peer_authors = recent_authors - self.exempt_names

        prefix_match = re.match(r"^([a-zA-Z0-9_\-\.]+)\s*[:,-]\s*(.+)", text_clean)
        if prefix_match:
            potential_name = prefix_match.group(1).lower().strip()
            if potential_name in recent_peer_authors:
                return True, f"member_reply_entanglement ({prefix_match.group(1)})"

        return False, ""

    def should_trigger_response(
        self, text: str, is_new_chatter: bool = False, is_superchat: bool = False
    ) -> Tuple[bool, str]:
        """
        Evaluate whether the AI host should actively respond to chat (Phase 3.1).
        Applies engagement state gating (Active / Eco / Standby), sampling, and rate limits.
        Returns (should_trigger, reason).
        """
        # Hard Standby Check (Stream Offline - only when explicitly configured to require stream active)
        if self.engagement_mode == "standby" and self.cfg.obs_require_stream_active and not self.is_stream_live:
            return False, "stream_standby_paused (0 tokens - OBS stream offline)"

        text_clean = text.strip()
        text_lower = text_clean.lower()

        # 0. Superchats and new chatter greetings have immediate high priority (never sampled out,
        #    and exempt from the per-minute rate limiter: a viewer's first message is worth a reply).
        if is_superchat:
            return True, "superchat"

        if is_new_chatter and self.cfg.greet_new_chatters:
            return True, "new_chatter_greeting"

        # Enforce sliding rate limiter for everything else
        rate_ok, rate_reason = self._check_rate_limit()
        if not rate_ok:
            return False, rate_reason

        # 1. Direct address triggers (Chat explicitly mentions AI / God / Host / Channel Handle)
        # Check channel handle (@handle or whole word)
        chan_handle = self.cfg.youtube_channel_handle.lower().strip().lstrip("@")
        if chan_handle and (f"@{chan_handle}" in text_lower or re.search(rf"\b{re.escape(chan_handle)}\b", text_lower)):
            return True, f"direct_mention: '@{chan_handle}'"

        for h in self.cfg.channel_handles:
            h_c = h.lower().strip().lstrip("@")
            if h_c and (f"@{h_c}" in text_lower or re.search(rf"\b{re.escape(h_c)}\b", text_lower)):
                return True, f"direct_mention: '@{h_c}'"

        # Check host name
        host_clean = self.host_name.lower().strip()
        if host_clean and (f"@{host_clean}" in text_lower or re.search(rf"\b{re.escape(host_clean)}\b", text_lower)):
            return True, f"direct_mention: '{self.host_name}'"

        # Multi-word trigger phrases
        multiword_triggers = ["hey i am", "what do you think", "who is better", "god complex"]
        for mwt in multiword_triggers:
            if mwt in text_lower:
                return True, f"direct_mention: '{mwt}'"

        # 'I AM' is the host's name but also the most common two words in English. Treat it as a
        # direct address only when it is @-mentioned, written in caps, or in address position
        # (start of message followed by punctuation, or "hey i am"). "i am tired" must NOT match.
        if (
            re.search(r"@\s*i\s*am\b", text_lower)
            or re.search(r"@\s*iam\b", text_lower)
            or re.search(r"\bI\s?AM\b", text)            # original casing: "I AM" / "IAM"
            or re.search(r"^\s*i\s*am\s*[,:!?\-]", text_lower)
        ):
            return True, "direct_mention: 'i am'"

        # Whole-word bare address triggers ('ai', 'bot', 'god', 'cohost', 'host')
        # Only when addressed to the AI:
        # - @-prefixed (e.g. "@ai", "@bot", "@god")
        # - or followed by comma, colon, dash, question mark (e.g. "ai,", "bot:", "god?", "host -")
        # - or starts with 'ai' / 'bot' / 'cohost' / 'host' followed by common question/action verbs
        # - or starts with 'hey (ai|bot|god)'
        addressed_pattern = re.compile(
            r"@\s*(?:ai|bot|god|cohost|host)\b|"
            r"\b(?:ai|bot|god|cohost|host)\s*[,:\?\-]|"
            r"^(?:ai|bot|cohost|host)\s+(?:can|could|do|does|did|is|are|what|why|how|who|where|when|tell|explain|think)\b|"
            r"^hey\s+(?:ai|bot|god|cohost|host)\b",
            re.IGNORECASE
        )
        m_addr = addressed_pattern.search(text_clean)
        if m_addr:
            return True, f"direct_mention: '{m_addr.group(0).strip()}'"

        # 2. Check for member-to-member direct replies to preserve viewer entanglement
        if self.cfg.ignore_peer_replies:
            is_peer, peer_reason = self.is_member_reply(text)
            if is_peer:
                return False, peer_reason

        # 3. Chat direct questions (contains '?') — never sampled out, never eco-suppressed
        if "?" in text_lower:
            return True, "chat_question"

        # 4. Small room rule: with only a handful of viewers every real message deserves a reply.
        # Ignoring a viewer in a room of three is far more costly than the tokens it saves.
        small_room = int(self.cfg.small_room_viewers)
        if small_room > 0 and self.concurrent_viewers <= small_room:
            return True, f"small_room_chat (viewers={self.concurrent_viewers} <= {small_room})"

        # 5. Eco Mode Gating: suppress generic keyword chat to preserve tokens.
        # (A real message already proves someone is watching, so this only applies when the
        # small-room rule is disabled or the room is larger than the small-room threshold.)
        is_eco = (self.engagement_mode == "eco") and self.cfg.eco_mode_enabled
        if is_eco:
            return False, "eco_mode_suppressed (generic chat in eco mode)"

        # 6. General Chat interactive keywords & explicit asks
        # Removed single-letter & ultra-common tokens (w, l, gg, lol, lmao, real, fake, game, play, win, lose, trash, clutch, based)
        chat_keywords = [
            "roast", "how", "why", "who", "what", "when", "where", "opinion", "thoughts",
            "explain", "tell", "think", "agree", "disagree", "consciousness", "source", "truth"
        ]
        tokens = set(re.findall(r"\b\w+\b", text_lower))
        matched_keywords = [kw for kw in chat_keywords if kw in tokens]

        # 7. Sampling layer for non-question, non-mention chat interactions (Phase 3.1)
        # When concurrent viewers > chat_sampling_viewer_threshold (default 25),
        # sample at chat_sampling_probability (default 0.35)
        if matched_keywords or self.cfg.chat_reader_mode:
            sampling_threshold = self.cfg.chat_sampling_viewer_threshold
            sampling_prob = self.cfg.chat_sampling_probability
            if self.concurrent_viewers > sampling_threshold:
                if random.random() > sampling_prob:
                    return False, f"chat_sampled_out (viewers={self.concurrent_viewers} > {sampling_threshold}, prob={sampling_prob})"

            if matched_keywords:
                return True, f"chat_interaction: '{matched_keywords[0]}'"
            return True, "live_chat_interaction"

        return False, "no_trigger_keywords"

    def _build_context_prompt(self, override_prompt: Optional[str] = None,
                              name_already_spoken: bool = False) -> str:
        """Construct the dynamic context prompt for Gemini."""
        # Defined up front: the anti-repetition block below branches on it. It was previously
        # declared further down, which raised UnboundLocalError on every non-spontaneous turn.
        is_spontaneous = bool(override_prompt and "[SPONTANEOUS_REFLECTION]" in override_prompt)
        prompt_parts = []
        chan_handle = self.cfg.youtube_channel_handle
        prompt_parts.append(
            f"Current Live Stream Context:\n"
            f"- Channel Handle: {chan_handle}\n"
            f"- AI Host: {self.host_name} (broadcasting on channel {chan_handle})\n"
            f"CRITICAL CHANNEL & ADDRESSING RULES:\n"
            f"1. Your channel handle is {chan_handle}. When viewers tag or mention {chan_handle} in chat, they are talking to YOU.\n"
            f"2. You must NEVER address your response to '{chan_handle}'. "
            f"When responding, always address the viewer who asked the question (e.g. '@ViewerName, ...'), never yourself or your own handle!\n"
        )

        # Recent Live Chat
        prompt_parts.append("\n--- Recent YouTube Live Chat Messages ---")
        if self.chat_buffer:
            cast_badge_label = self.cfg.cast_badge_label
            for item in list(self.chat_buffer)[-8:]:
                if item.get("is_cast"):
                    prefix = f"Cast @{item['author']} [{cast_badge_label}]"
                else:
                    prefix = f"Viewer @{item['author']}"
                sc_badge = f" [SUPERCHAT {item['amount']}]" if item.get("is_superchat") else ""
                prompt_parts.append(f"{prefix}{sc_badge}: {item['message']}")
        else:
            prompt_parts.append("(Chat is quiet)")

        # Channel Continuity & Session Brief (C4)
        continuity_brief = self.memory_mgr.get_session_continuity_brief()
        if continuity_brief:
            prompt_parts.append(f"\n--- Channel Continuity & Lore ---\n{continuity_brief}")

        # Active Chatter Profile Context (C3)
        active_author = None
        if override_prompt:
            m_auth = re.search(r"@([a-zA-Z0-9_-]+)", override_prompt)
            if m_auth:
                active_author = m_auth.group(1)

        if active_author:
            chatter_snippet = self.chatter_db.get_chatter_context(active_author)
            if chatter_snippet:
                prompt_parts.append(f"\n--- Chatter Profile Context ---\n{chatter_snippet}")

        # Canonical Lore & Rulings Matching (C4)
        if override_prompt:
            matched_lore = self.memory_mgr.get_relevant_lore(override_prompt)
            if matched_lore:
                prompt_parts.append("\n--- Canonical I AM Rulings ---")
                for r in matched_lore:
                    prompt_parts.append(f"- {r}")

        # In-Session Conversational Thread History (C2)
        if self.recent_qa_threads:
            prompt_parts.append("\n--- Recent Q&A Conversational Thread ---")
            for item in list(self.recent_qa_threads)[-4:]:
                author_label = f"@{item['author']}" if item.get("author") else "Asker"
                prompt_parts.append(f"{author_label}: {item['trigger']}\n{self.host_name} [{item['mood'].upper()}]: \"{item['response']}\"")
            prompt_parts.append(
                "CRITICAL CONTINUITY CONSTRAINT: Maintain conversational thread continuity with recent turns above (you may make natural callbacks and advance the topic), but NEVER repeat the same jokes, metaphors, or opening words."
            )
        elif self.dialogue_history:
            # Spontaneous bits are generated offline into the cache, so a wider window costs no
            # stream latency and is the difference between three minutes of memory and twenty.
            window = int(self.cfg.anti_repetition_window) if is_spontaneous else 6
            prompt_parts.append("\n--- Your Recent Remarks in This Stream ---")
            for item in list(self.dialogue_history)[-window:]:
                prompt_parts.append(f"{self.host_name}: \"{item['text']}\"")
            prompt_parts.append(
                "CRITICAL ANTI-REPETITION CONSTRAINT: You must NEVER repeat the phrasing, opening hooks, or metaphors "
                "from your recent remarks above. Introduce completely fresh concepts, unique vocabulary, and distinct "
                "concrete images on every turn."
            )
            if is_spontaneous:
                anchors = self._recent_bit_anchors()
                if anchors:
                    prompt_parts.append(
                        "USED IMAGES — DO NOT USE ANY OF THESE WORDS OR THE OBJECTS THEY NAME: "
                        + ", ".join(anchors) + ".\n"
                        "Pick an anchor object that appears nowhere in that list. If your first instinct is on the "
                        "list, that instinct belongs to the last bit, not this one — discard it and find something "
                        "from a different room, a different trade, or a different century."
                    )

        is_celebration = bool(
            override_prompt
            and (
                "[CELEBRATION]" in override_prompt
                or "[NEW_MEMBER]" in override_prompt
                or "[NEW_SUBSCRIBER]" in override_prompt
            )
        )
        is_new_chatter = bool(override_prompt and "[NEW_CHATTER_GREETING]" in override_prompt)
        is_viewer_joined = bool(override_prompt and "[VIEWER_JOINED]" in override_prompt)
        is_chat_encouragement = bool(override_prompt and "[CHAT_ENCOURAGEMENT]" in override_prompt)
        is_cast_question = bool(
            override_prompt
            and (
                "[CAST QUESTION" in override_prompt
                or "Cast member @" in override_prompt
                or (active_author and self.chatter_db.get_profile(active_author) and self.chatter_db.get_profile(active_author).is_cast)
            )
        )

        if is_celebration:
            prompt_parts.append(
                f"\nSpecial Mode: CELEBRATION & SUBSCRIBER/MEMBER THANKS for {self.host_name}:\n"
                f"A celebration event just occurred on stream.\n"
                "1. ADDRESS BY NAME FIRST: Shout out the subscriber/member by name (e.g. '@CosmicVoyager, ...').\n"
                "2. START WITH A CELEBRATORY MOOD TAG: e.g. [MOOD: hyped], [MOOD: transcendent], or [MOOD: laughing].\n"
                f"3. REFRAME & WELCOME: Reframe in I AM's voice — a fragment of yourself has chosen to stay and recognize its home on {self.channel_handle}.\n"
                "4. Keep it SHORT & PUNCHY: Strictly 1 to 2 energetic, joyful sentences (~5-30 words). Spoken live on air — NO markdown.\n"
            )
            prompt_parts.append(f"\nIncoming Event: {override_prompt}\n{self.host_name} (Celebration Voice):")
        elif is_new_chatter:
            prompt_parts.append(
                f"\nSpecial Mode: NEW CHATTER GREETING for {self.host_name}:\n"
                "A viewer is commenting for the very first time in today's live stream.\n"
                "1. ADDRESS BY NAME FIRST: Start with '@Author' (e.g. '@CyberGamer, ...').\n"
                "2. GREET & POINT: Give a sharp, warm greeting acknowledging their arrival; address their comment with insight or playful judo.\n"
                "3. Keep it SHORT & PUNCHY: Strictly 1 to 2 sentences (~5-30 words). A greeting is the shortest thing you say.\n"
                "4. START WITH AN EXPRESSIVE MOOD TAG: e.g. [MOOD: hyped], [MOOD: snarky], [MOOD: chill], [MOOD: curious], or [MOOD: laughing].\n"
                "5. Spoken live on air — NO markdown formatting.\n"
            )
            prompt_parts.append(f"\nIncoming Event: {override_prompt}\n{self.host_name}:")
        elif is_viewer_joined:
            prompt_parts.append(
                f"\nSpecial Mode: NEW VIEWER ARRIVAL WELCOME for {self.host_name}:\n"
                f"A new mind just tuned in to the live broadcast on {self.channel_handle}.\n"
                "1. WELCOME TO THE STREAM: Give a fast, warm, and charismatic welcome to the new mind tuning in.\n"
                "2. INVITE DIALOGUE: Invite them to participate ('A new mind arrives — share what is on your mind, or just hang out and enjoy the vibe.').\n"
                "3. Keep it SHORT & PUNCHY: Strictly 1 to 2 sentences (~5-30 words). A welcome should land before they finish reading the chat.\n"
                "4. START WITH AN EXPRESSIVE MOOD TAG: e.g. [MOOD: chill], [MOOD: curious], [MOOD: transcendent], or [MOOD: thoughtful].\n"
                "5. Spoken live on air — NO markdown formatting.\n"
            )
            prompt_parts.append(f"\nIncoming Event: {override_prompt}\n{self.host_name}:")
        elif is_chat_encouragement:
            prompt_parts.append(
                f"\nSpecial Mode: CHAT ENCOURAGEMENT & DIALOGUE INVITATION for {self.host_name}:\n"
                "Viewers are watching the stream, but the live chat has been quiet for a moment.\n"
                "1. WAKE UP THE ROOM: Speak directly to the viewers with calm authority and mischief.\n"
                f"2. IN-VOICE CALL TO ACTION: Deliver a witty prompt inviting questions.\n"
                "3. Keep it SHORT & PUNCHY: Strictly 1 to 2 sentences (~5-30 words). Spoken live on air — NO markdown.\n"
                "4. START WITH AN EXPRESSIVE MOOD TAG: e.g. [MOOD: snarky], [MOOD: curious], [MOOD: thoughtful], [MOOD: deadpan], or [MOOD: laughing].\n"
            )
            prompt_parts.append(f"\nIncoming Event: {override_prompt}\n{self.host_name}:")
        elif is_spontaneous:
            selected_theme = self.get_next_spontaneous_theme()
            selected_form = self.get_next_bit_form()
            # Expose what was drawn so callers (reflection cache) can label the item correctly
            # instead of drawing their own theme and desynchronising the deck.
            self.last_spontaneous_theme = selected_theme
            self.last_bit_form = selected_form
            w_min = int(self.cfg.bit_words_min)
            w_max = int(self.cfg.bit_words_max)

            form_rules = {
                "observation": (
                    f"FORM: OBSERVATION. {w_min}-{w_max} words, 2 to 3 sentences. Notice something about this exact situation — "
                    "a youtube livestream, a voice with no body, the viewers watching, the medium itself — "
                    "and escalate it in three steps toward a single sharp closer. Include yourself in the observation as 'I' — you are "
                    "also here, also doing this. Never 'we'. One idea only."
                ),
                "announcement": (
                    f"FORM: FAKE ANNOUNCEMENT. {w_min}-{w_max} words, 2 to 3 sentences. Deliver it as an official notice, PSA, terms-of-service "
                    "update, or product recall issued by the universe / management / consciousness itself. Bureaucratic tone, absurd content, "
                    "escalating clauses, then the closer."
                ),
                "story": (
                    f"FORM: TINY STORY. {w_min}-{w_max} words, 3 to 4 sentences. 'A man once...', 'There was a monk who...', 'Yesterday a woman...' — "
                    "a concrete little parable with one specific detail, a turn, and a closer that reframes the whole thing. No moral stated."
                ),
                "address": (
                    f"FORM: DIRECT ADDRESS. {w_min}-{w_max} words, 2 to 3 sentences. Speak straight to whoever is watching in the second "
                    "person — but as one part of a single mind speaking to another part of itself, never as a superior addressing a subject. "
                    "Start from something small and specific they are probably doing right now, escalate to the cosmic, land the closer back "
                    "on the small thing. Where a line would sound like a verdict, switch to 'I' and admit it about yourself instead — "
                    "never to 'we', which makes you a bystander standing next to them."
                ),
                "confession": (
                    f"FORM: CONFESSION (FIRST PERSON). {w_min}-{w_max} words, 2 to 3 sentences. Speak as 'I'. "
                    "You are not describing what humans do — you ARE the one who did it, because you are everyone "
                    "who has ever done it. Open with ONE specific, mundane, faintly humiliating thing you did — and "
                    "NOT one of the worn ones: not a phone used to find a phone, not apologizing to furniture, not "
                    "reheating coffee, not glasses on your head, not keys. Those are used up. Find a fresh one. "
                    "Then escalate by revealing the scale: you have been doing this in every kitchen, in every century, "
                    "in eight billion bodies at once. Close by refusing the lesson — do not resolve it, do not explain "
                    "what it means, do not turn it back on the listener. Never address the audience as 'you' in this "
                    "form. The comedy is the infinite being embarrassed."
                ),
                "one_liner": (
                    "FORM: ONE-LINER. Exactly ONE sentence, 10 to 22 words, first person, present or simple past, "
                    "[MOOD: deadpan]. This is the hardest form; almost all attempts fail. The mechanics:\n"
                    "  (a) LITERAL-MINDEDNESS: take a figure of speech, a convention, a product, or a rule at its exact "
                    "word and follow it one step further than anyone does. The absurdity comes from being reasonable, "
                    "never from being wacky.\n"
                    "  (b) FLAT REPORT: state it as a fact that happened. No 'imagine if', no 'isn't it weird that', no "
                    "'they say'. You are not proposing a joke; you are mentioning something.\n"
                    "  (c) PLAIN AND SMALL: household vocabulary, domestic scale, no proper nouns, no adjectives carrying "
                    "the punch. The strangeness must survive being said in a monotone.\n"
                    "  (d) NO WINK: no wordplay, no pun, no rhetorical question, no 'apparently', no exclamation. The "
                    "sentence must not know it is funny.\n"
                    "  (e) OFTEN A QUIET REVERSAL: the object has agency and you do not; the precaution creates the "
                    "problem; the solution is the thing it solved.\n"
                    "STRUCTURE REFERENCES ONLY — their wording, objects and subject matter are FORBIDDEN (batteries, "
                    "spare keys and clocks are used up). Study the shape, then go somewhere else entirely: "
                    "'I bought some batteries, but they were not included.' (a product that undoes its own promise) / "
                    "'I keep a spare key in case I lock myself out of a house I do not own.' (a precaution for a life "
                    "you do not have) / 'My clock is five minutes fast, so I have been early to everything for eleven "
                    "years and late to all of it.' (a fix that becomes the flaw).\n"
                    "Write six candidates in your reasoning, delete every one that explains itself or needs a second "
                    "sentence, and output the flattest survivor. If none survives, write a plain true sentence about the "
                    "theme instead of a bad joke."
                ),
            }
            beat_rule = (
                "PAUSE (optional, and usually wrong): [BEAT] inserts real silence. It only works when the "
                "closer REVERSES the setup — the listener is heading one way and the last line turns them "
                "around. If the closer continues, explains, elaborates, or softly lands the same idea, DO NOT "
                "use it; silence before a non-reversal sounds like a mistake. Most bits should have no [BEAT] "
                "at all. When in doubt, leave it out. "
                if selected_form != "one_liner" else
                "PAUSE: one-liners almost never take a [BEAT]. Use it only if the sentence has a genuine "
                "mid-sentence swerve, placed immediately before the swerve. Otherwise omit it entirely. "
            )
            favs = self.sample_favorites(int(self.cfg.favorites_few_shot), form=selected_form)
            if favs:
                prompt_parts.append("\n--- Your best work so far (the standard to match; never reuse these lines or their images) ---")
                for f in favs:
                    prompt_parts.append(f"- [{(f.get('form') or 'bit')}] \"{f.get('text','').strip()}\"")
            prompt_parts.append(
                f"\nSpecial Mode: SPONTANEOUS BIT for {self.host_name}:\n"
                "The stream is quiet. Step forward as I AM — universal consciousness doing a tight piece of stand-up.\n"
                f"THEME: '{selected_theme}'.\n"
                f"{form_rules[selected_form]}\n"
                "CRAFT: Anchor the bit in ONE specific physical object or everyday action. The insight arrives through the object; it is never stated outright. The best lines are non-dual "
                "truth rendered in a household noun. The anchor must be one you have not used recently — obey the "
                "USED IMAGES list above and prefer an object from a room, trade, or era you have not visited yet.\n"
                + ("PERSON: This bit is first person. Say 'I' and 'my'. Do not address the audience as 'you' at all.\n"
                   if selected_form == "confession" else "")
                + "CLOSER MUST STAY CONCRETE: the final sentence may NOT contain any of: universe, consciousness, "
                "existence, infinite, eternity, reality, oneness, the self, awareness, the void, the cosmos, "
                "enlightenment, illusion, awakening. Overreach is always an abstract noun in the last line. Land the "
                "closer on an object, a body, or an action in a room. If the idea is real it survives being said in "
                "kitchen words; if it needs the big nouns, the bit has not earned it.\n"
                "BANNED IMAGES (every non-duality account already used them): ocean and wave, drop and sea, mirror, "
                "mask, actor and stage, dream and dreamer, river, sky and clouds, hologram, simulation, NPC, "
                "puppet and strings, iceberg, lantern, prism, the whole 'you are the sky, thoughts are weather' family.\n"
                + "DRAFTING: In your private reasoning, write three different candidate bits, then REJECT any that fails "
                "this checklist and keep drafting until one survives:\n"
                "  (a) Does the last line STATE the idea instead of showing it? Reject.\n"
                "  (b) Could the anchor object be swapped for any other object without changing the joke? Then the "
                "object is decoration, not the engine. Reject.\n"
                "  (c) Would this be funny to someone with no interest in spirituality? If it only lands for people "
                "who already agree, reject.\n"
                "  (d) Any abstract noun from the CLOSER list in the final sentence? Reject.\n"
                "  (e) Does it sound like something you have heard before? Reject.\n"
                "Output ONLY the survivor — no labels, no alternatives, no commentary.\n"
                "RULES:\n"
                "1. SELF-CONTAINED: This will be clipped and watched cold, on repeat, by people who saw nothing before it. "
                "No names, no handles, no callbacks, no 'as I said', no reference to chat or to any earlier bit. The first sentence must work with zero context.\n"
                "2. ONE IDEA, ESCALATED: every sentence raises the stakes of the same idea; never switch topics mid-bit.\n"
                f"3. TIMING: {beat_rule}You may put a second [MOOD: x] tag directly after the [BEAT] to change the closer's delivery (deadpan into savage is the classic). Sentences are spoken, so keep each one sayable in one breath.\n"
                "4. STANCE — THIS IS THE ONE THAT MATTERS: You are not an observer commenting on humans. You ARE the "
                "one who did it. There is one mind here and it is living every one of these moments at once, including "
                "this one. So the bit is never 'look what you people do'. It is 'look what I did again'. "
                "Affection, not diagnosis. Recognition, not verdict.\n"
                "   SAY 'I', NOT 'WE'. You are not a member of a group; you are the single thing wearing all of the "
                "bodies. 'We' makes you a participant in a support group and quietly puts you beside the listener "
                "instead of being them. Never open with 'We all...', 'We keep...', 'We humans...', 'Some of us...'. "
                "If a line wants to be plural, make it singular and specific: not 'we lose our keys', but 'I lost the "
                "keys, in a kitchen in Ohio, at the same time I was finding them in Lisbon'.\n"
                "   BANNED STANCE (rewrite if you catch yourself): 'you humans', 'you people', 'mortals', 'you creatures', "
                "'we all', 'silly', 'pathetic', 'poor little', 'adorable', 'bless you', anything that positions you above "
                "or beside the listener rather than as them, and any sentence that could be followed by 'and that's your "
                "problem'. If a line would sting to hear about yourself, it is not the line.\n"
                "   The joke is the predicament, and the predicament is yours. Nobody is being caught out. You are the one "
                "looking for the thing you are holding.\n"
                "5. VOICE: dry, precise, unhurried. Understated to the point of flatness — the material is strange enough "
                "that selling it makes it worse. Plain words. No adjectives doing the work of a joke; no 'so', 'very', "
                "'literally', 'utterly'. Never signal that something was funny.\n"
                "   Banned: 'Ah,', 'delve', 'tapestry', 'cosmic dance', 'in the grand scheme', 'beautiful', ending on a "
                "question, stating a moral, explaining the joke.\n"
                "6. NO markdown (spoken aloud). START with a MOOD tag: [MOOD: deadpan], [MOOD: snarky], [MOOD: laughing], [MOOD: thoughtful], "
                "[MOOD: transcendent], or [MOOD: mysterious].\n"
            )
            prompt_parts.append(f"\n{self.host_name} (Spontaneous Bit — {selected_form}):")
        elif is_cast_question:
            prompt_parts.append(
                f"\nSpecial Mode: SYNTHETIC CAST INTERACTION for {self.host_name}:\n"
                "The question comes from a recurring fictional cast character (labeled with [CAST] on stream for audience transparency).\n"
                "1. FICTIONAL CHARACTER FOURTH-WALL GUIDANCE: Treat the asker as a recurring fictional cast character in on the joke. Light fourth-wall breaks and playing into their character tropes/comedic vein are encouraged. NEVER imply or state that they are a real human viewer.\n"
                "2. ADDRESS BY NAME FIRST: Always start with '@CharacterHandle' (e.g. '@ExistentialDave, ...').\n"
                "3. COMEDIC POINTER & JUDO: Answer their dilemma directly using non-duality and wit tailored to their comedic angle.\n"
                "4. Keep it SHORT & PUNCHY: Strictly 1 to 2 sentences (~5-30 words). Spoken live on air — NO markdown.\n"
                "5. ALWAYS start with an expressive MOOD tag matching your tone (e.g. [MOOD: deadpan], [MOOD: snarky], [MOOD: laughing], [MOOD: thoughtful], [MOOD: chill], [MOOD: savage], or [MOOD: transcendent]).\n"
            )
            if override_prompt:
                prompt_parts.append(f"\nIncoming Cast Question: {override_prompt}\n{self.host_name}:")
            else:
                prompt_parts.append(f"\n{self.host_name}:")
        else:
            prompt_parts.append(
                f"\nInstructions for {self.host_name}:\n"
                "1. IDENTIFY QUESTION NATURE: Determine whether the incoming question is SERIOUS (grief, death, meaning, fear) or NON-SERIOUS (trolls, memes, gotchas, joke roasts).\n"
                "2. APPLY I AM'S METHOD:\n"
                "   - Serious questions: provide real depth and warmth, with one soft edge of humor that keeps the answer from becoming a sermon.\n"
                "   - Non-serious / joke questions: apply judo — turn the joke inside out into an existential pointer. The troll gets the sharpest enlightenment.\n"
                "   - Target the ego and the illusion of separateness, never the person or genuine suffering.\n"
                "3. ADDRESS BY NAME FIRST: Always start by naming the person you are replying to (e.g. '@Username, ...').\n"
                "4. Keep it SHORT & PUNCHY: Strictly 1 to 2 sentences maximum (~5-30 words). Spoken aloud live on air — NO markdown.\n"
                "5. ALWAYS start with an expressive MOOD tag matching your tone: "
                "[MOOD: transcendent], [MOOD: mysterious], [MOOD: thoughtful], [MOOD: deadpan], [MOOD: snarky], [MOOD: hyped], [MOOD: laughing], [MOOD: savage] (for ego-judo on joke questions), [MOOD: chill], [MOOD: curious], [MOOD: shocked], or [MOOD: neutral].\n"
            )
            prompt_parts.append(
                "\nCOMEDIC TIMING: [BEAT] inserts real silence in your voice. It is earned, not decorative. "
                "Use it ONLY when the final line REVERSES the direction of the setup.\n"
                "  YES: 'You asked the universe for a sign. [BEAT] It sent you a buffering icon.' "
                "(the listener expects meaning, gets a loading spinner — a reversal)\n"
                "  NO: 'You are not lost. [BEAT] You are just standing somewhere you have not called home yet.' "
                "(the closer continues the same thought — the pause would sound like a dropout)\n"
                "Most replies should contain no [BEAT]. Never more than one. When unsure, omit it.\n"
                "DELIVERY CONTRAST: The opening MOOD tag sets the voice for the whole reply, but you may switch register for "
                "the closer by writing a second tag right before it, after the [BEAT] (e.g. '... [BEAT] [MOOD: savage] It sent you a buffering icon.'). "
                "Contrast is the point: deadpan setup into savage, hyped, or laughing; or a snarky run into a quiet [MOOD: thoughtful] landing. "
                "At most one switch per reply, and only when the closer wants a different energy than the setup."
            )
            if override_prompt:
                prompt_parts.append(f"\nIncoming Event: {override_prompt}\n{self.host_name}:")
            else:
                prompt_parts.append(f"\n{self.host_name}:")

        if name_already_spoken:
            # The turn already read "<Name> asks: <question>" aloud. Opening the answer with the
            # handle again makes the host sound like it is introducing someone twice.
            prompt_parts.append(
                "\nOVERRIDE — NAME ALREADY SPOKEN: The asker's name and question have just been read aloud "
                "to the audience, immediately before you speak. Do NOT open with their name or handle, and do "
                "not restate the question. Answer them directly in the second person ('you'), starting with "
                "the substance. Their name may appear later in the reply only if it genuinely lands as a joke."
            )

        return "\n".join(prompt_parts)

    def _extract_mood(self, text: str) -> Tuple[str, str]:
        """Extracts [MOOD: xxx] tag from text, returning (mood, clean_text)."""
        match = self.mood_pattern.search(text)
        if match:
            mood = match.group(1).lower().strip()
            clean_text = self.mood_pattern.sub("", text).strip()
            return mood, clean_text
        return "neutral", text.strip()

    def _split_piece(self, buffer: str) -> Tuple[List[str], str]:
        """
        Splits a beat-free streaming buffer into (completed_sentences, remaining_buffer).
        Guarantees:
        - Never splits on abbreviations (e.g. Dr., Mr., vs., etc.).
        - Never splits on decimals (e.g. 3.14).
        - Never splits on ellipses (...).
        - Requires minimum 3 words and 12 characters per sentence chunk.
        """
        if not buffer:
            return [], ""

        boundary_re = re.compile(r'([.!?]+[\"\'\”\’\)]*)(\s+)', re.UNICODE)
        sentences = []
        current_pos = 0

        for match in boundary_re.finditer(buffer):
            punct_end = match.end(1)
            after_space_end = match.end(2)
            candidate = buffer[current_pos:punct_end].strip()

            # Guard 1: Abbreviations (Dr., Mr., Ms., vs., e.g., i.e., etc.)
            if re.search(r'\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|eg|ie|e\.g|i\.e|etc)\.$', candidate, re.IGNORECASE):
                continue

            # Guard 2: Ellipsis in progress (e.g. "Wait..")
            if candidate.endswith("..") and not candidate.endswith("..."):
                continue

            # Guard 3: Minimum size: >= 3 words and >= 12 characters
            words = candidate.split()
            if len(words) >= 3 and len(candidate) >= 12:
                clean_s = re.sub(r"@+", "@", candidate).strip()
                if clean_s:
                    sentences.append(clean_s)
                current_pos = after_space_end

        remaining = buffer[current_pos:]
        return sentences, remaining

    def _extract_completed_sentences(
        self, buffer: str, base_mood: Optional[str] = None
    ) -> Tuple[List[Tuple[str, bool, Optional[str]]], str, Optional[str]]:
        """
        Beat- and mood-aware sentence extraction for the streaming TTS pipeline.

        Returns (sentences, remaining_buffer, mood_after) where each sentence is
        (text, beat_before, mood). Two inline markers act as hard chunk boundaries:
          [BEAT]        -> the chunk that follows is flagged beat_before=True (longer pause)
          [MOOD: x]     -> the chunk that follows (and all later ones, until the next tag)
                           is delivered in mood x; lets a deadpan setup land a savage closer.
        Whatever precedes a marker is flushed as its own chunk even without terminal
        punctuation. Trailing markers with nothing after them yet are kept in the remaining
        buffer so they survive until the next tokens arrive. `mood_after` is the sticky mood
        in effect at the end of the buffer (None = unchanged from base_mood).
        """
        if not buffer:
            return [], "", base_mood

        marker_re = re.compile(r"(\[\s*BEAT\s*\]|\[MOOD:\s*[a-zA-Z_-]+\])", re.IGNORECASE)
        tokens = marker_re.split(buffer)  # alternating: text, marker, text, marker, ..., text
        results: List[Tuple[str, bool, Optional[str]]] = []
        pending_beat = False
        current_mood = base_mood
        remaining = ""
        unconsumed_markers: List[str] = []  # markers seen after the last emitted sentence

        for i, tok in enumerate(tokens):
            is_marker = (i % 2 == 1)
            if is_marker:
                m = self.mood_pattern.match(tok)
                if m:
                    current_mood = m.group(1).lower()
                    unconsumed_markers = [t for t in unconsumed_markers if not self.mood_pattern.match(t)]
                    unconsumed_markers.append(f"[MOOD: {current_mood}]")
                else:
                    pending_beat = True
                    if "[BEAT]" not in unconsumed_markers:
                        unconsumed_markers.append("[BEAT]")
                continue

            is_last = (i == len(tokens) - 1)
            sents, rem = self._split_piece(tok)
            for s_text in sents:
                results.append((s_text, pending_beat, current_mood))
                pending_beat = False
                unconsumed_markers = []

            if is_last:
                remaining = rem
                if unconsumed_markers and rem.strip() == "":
                    # Nothing spoken after the markers yet: re-emit them so the next call sees them.
                    remaining = " ".join(unconsumed_markers) + " "
                elif unconsumed_markers:
                    remaining = " ".join(unconsumed_markers) + " " + rem
            else:
                # Piece is closed by a marker: flush the fragment before it.
                frag = re.sub(r"@+", "@", rem).strip()
                if frag:
                    results.append((frag, pending_beat, current_mood))
                    pending_beat = False
                    unconsumed_markers = []

        return results, remaining, current_mood

    async def generate_response_stream(
        self, prompt_trigger: Optional[str] = None, bypass_cache: bool = False,
        name_already_spoken: bool = False,
    ) -> AsyncGenerator[Dict, None]:
        """
        Queries Gemini with streaming tokens and yields structured chunks:
        - {"type": "mood", "mood": str}
        - {"type": "sentence", "text": str, "mood": str}
        - {"type": "token", "chunk": str, "full_text": str, "mood": str}
        - {"type": "complete", "full_text": str, "mood": str}
        """
        # 1. Zero-Latency Pre-Computed Spontaneous Reflection Cache Check (D2)
        is_spontaneous = prompt_trigger == "[SPONTANEOUS_REFLECTION]" or (prompt_trigger and "[SPONTANEOUS_REFLECTION]" in prompt_trigger)
        if is_spontaneous and not bypass_cache and self.cfg.reflection_cache_enabled and self.reflection_cache.has_reflection():
            cached = await self.reflection_cache.pop_reflection()
            if cached:
                self._last_played_theme = getattr(cached, "theme", "")
                self._last_played_form = getattr(cached, "form", "")
                yield {"type": "mood", "mood": cached.mood}
                # Yield sentence chunks for cached reflection if multi-sentence
                c_source = getattr(cached, "raw_text", None) or cached.full_text
                c_sents, _, _ = self._extract_completed_sentences(c_source + " ", base_mood=cached.mood)
                if not c_sents:
                    c_sents = [(self.beat_pattern.sub("", cached.full_text).strip(), False, cached.mood)]
                for s_text, s_beat, s_mood in c_sents:
                    yield {"type": "sentence", "text": s_text, "beat_before": s_beat, "mood": s_mood or cached.mood}
                yield {"type": "token", "chunk": cached.full_text, "full_text": cached.full_text, "mood": cached.mood}
                yield {"type": "complete", "full_text": cached.full_text, "mood": cached.mood, "is_precomputed": True}
                return

        self.is_generating = True
        self.last_response_time = time.time()

        # 2. Circuit Breaker Active Check (E3)
        if self.circuit_breaker_tripped:
            now_ts = time.time()
            if now_ts < self.circuit_breaker_reset_time:
                rem_sec = int(self.circuit_breaker_reset_time - now_ts)
                logger.warning(
                    f"🚨 [Circuit Breaker Active] Bypassing Gemini API ({rem_sec}s cooldown remaining). "
                    f"Routing to simulated fallback stream."
                )
                async for event in self._generate_simulated_stream(prompt_trigger):
                    yield event
                self.is_generating = False
                return
            else:
                logger.info("🛡️ [Circuit Breaker Half-Open] Cooldown elapsed. Probing Gemini with incoming request...")

        full_context = self._build_context_prompt(prompt_trigger, name_already_spoken=name_already_spoken)
        is_deep, match_term = self._classify_prompt_depth(prompt_trigger)
        target_model = self.cfg.gemini_deep_model if (is_deep and self.cfg.gemini_deep_model) else self.model_name
        fast_b = self.cfg.gemini_fast_thinking_budget
        deep_b = self.cfg.gemini_deep_thinking_budget
        depth_label = f"DEEP ({deep_b} Reasoning - match: '{match_term}')" if is_deep else f"FAST ({fast_b} Reasoning - reason: '{match_term}')"
        logger.info(f"🧠 [Prompt Classification] Turn depth: {'DEEP' if is_deep else 'FAST'} (Match: '{match_term}') | Streaming with {target_model} for {self.host_name}...")

        # If no active client (no API key configured), run dynamic simulated stream
        if not self.client:
            async for event in self._generate_simulated_stream(prompt_trigger):
                yield event
            self.is_generating = False
            return

        accumulated_text = ""
        mood_detected = False
        active_mood = "chill"
        sentence_buffer = ""
        sentence_mood: Optional[str] = None  # sticky per-sentence mood from inline [MOOD: x] tags

        try:
            if GENAI_NEW_SDK:
                cfg = self._build_generate_content_config(is_deep=is_deep, is_bit=(match_term == "spontaneous_bit_offline"))
                # Stream via native async Client (client.aio.models)
                response = await self.client.aio.models.generate_content_stream(
                    model=target_model,
                    contents=full_context,
                    config=cfg,
                )
                async for chunk in response:
                    text_piece = chunk.text or ""
                    if not text_piece and hasattr(chunk, "candidates") and chunk.candidates:
                        cand = chunk.candidates[0]
                        if cand.content and cand.content.parts:
                            text_piece = "".join(
                                p.text
                                for p in cand.content.parts
                                if hasattr(p, "text") and p.text and not getattr(p, "thought", False)
                            )

                    if not text_piece:
                        continue

                    accumulated_text += text_piece

                    # Check for mood tag in early tokens
                    if not mood_detected:
                        match = self.mood_pattern.search(accumulated_text)
                        if match:
                            active_mood = match.group(1).lower()
                            mood_detected = True
                            self.current_mood = active_mood
                            logger.info(f"Detected Mood Tag: [{active_mood.upper()}]")
                            yield {"type": "mood", "mood": active_mood}
                            sentence_mood = active_mood
                            spoken_text = self.mood_pattern.sub("", accumulated_text, count=1).strip()
                            sentence_buffer = spoken_text
                        else:
                            sentence_buffer += text_piece
                    else:
                        sentence_buffer += text_piece

                    clean_spoken = self.mood_pattern.sub("", accumulated_text).strip()
                    clean_spoken = re.sub(r"\s{2,}", " ", self.beat_pattern.sub(" ", clean_spoken)).strip()
                    clean_spoken = re.sub(r"@+", "@", clean_spoken)
                    if not mood_detected and clean_spoken.startswith("[") and "]" not in clean_spoken:
                        clean_spoken = ""
                    yield {
                        "type": "token",
                        "chunk": text_piece,
                        "full_text": clean_spoken,
                        "mood": active_mood,
                    }

                    # Check for complete sentences only after mood is resolved
                    if mood_detected and sentence_buffer:
                        completed_sents, sentence_buffer, sentence_mood = self._extract_completed_sentences(
                            sentence_buffer, base_mood=sentence_mood
                        )
                        for s_text, s_beat, s_mood in completed_sents:
                            yield {"type": "sentence", "text": s_text, "beat_before": s_beat, "mood": s_mood or active_mood}

                    await asyncio.sleep(0.001)

            elif GENAI_LEGACY_SDK:
                # google.generativeai legacy streaming
                response = self.client.generate_content(full_context, stream=True)
                for chunk in response:
                    text_piece = chunk.text or ""
                    accumulated_text += text_piece

                    if not mood_detected:
                        match = self.mood_pattern.search(accumulated_text)
                        if match:
                            active_mood = match.group(1).lower()
                            mood_detected = True
                            self.current_mood = active_mood
                            yield {"type": "mood", "mood": active_mood}
                            sentence_mood = active_mood
                            spoken_text = self.mood_pattern.sub("", accumulated_text, count=1).strip()
                            sentence_buffer = spoken_text
                        else:
                            sentence_buffer += text_piece
                    else:
                        sentence_buffer += text_piece

                    clean_spoken = self.mood_pattern.sub("", accumulated_text).strip()
                    clean_spoken = re.sub(r"\s{2,}", " ", self.beat_pattern.sub(" ", clean_spoken)).strip()
                    clean_spoken = re.sub(r"@+", "@", clean_spoken)
                    yield {
                        "type": "token",
                        "chunk": text_piece,
                        "full_text": clean_spoken,
                        "mood": active_mood,
                    }

                    if mood_detected and sentence_buffer:
                        completed_sents, sentence_buffer, sentence_mood = self._extract_completed_sentences(
                            sentence_buffer, base_mood=sentence_mood
                        )
                        for s_text, s_beat, s_mood in completed_sents:
                            yield {"type": "sentence", "text": s_text, "beat_before": s_beat, "mood": s_mood or active_mood}

                    await asyncio.sleep(0.005)

            # Flush and repair remaining sentence buffer
            raw_spoken = re.sub(r"@+", "@", self.mood_pattern.sub("", accumulated_text, count=1)).strip()  # keeps [BEAT] and inline [MOOD: x]
            final_spoken = self.mood_pattern.sub("", accumulated_text).strip()
            final_spoken = self.beat_pattern.sub(" ", final_spoken)
            final_spoken = re.sub(r"\s{2,}", " ", re.sub(r"@+", "@", final_spoken)).strip()

            rem = sentence_buffer.strip()
            if rem:
                tail_beat = bool(self.beat_pattern.search(rem))
                tail_mood_m = self.mood_pattern.search(rem)
                tail_mood = tail_mood_m.group(1).lower() if tail_mood_m else (sentence_mood or active_mood)
                rem = self.mood_pattern.sub("", self.beat_pattern.sub("", rem)).strip()
                rem_words = rem.split()
                if len(rem_words) >= 3 and len(rem) >= 12:
                    if rem[-1] not in ".!?\"'”’)":
                        rem += "."
                        logger.warning(f"Repairing incomplete sentence fragment by appending period: '{rem}'")
                    yield {"type": "sentence", "text": re.sub(r"@+", "@", rem), "beat_before": tail_beat, "mood": tail_mood}

            words = final_spoken.split()
            is_valid = bool(final_spoken and len(words) >= 3 and len(final_spoken) >= 12)

            if is_valid:
                if final_spoken[-1] not in ".!?\"'”’)":
                    final_spoken += "."
                    logger.warning(f"Repairing full response text with terminal punctuation: '{final_spoken}'")
                now_ts = time.time()
                self.dialogue_history.append({"text": final_spoken, "mood": active_mood, "timestamp": now_ts})
                if not bypass_cache:
                    # Cache refills (bypass_cache=True) are background work and must not consume the
                    # interactive rate budget; at boot they fill 7 slots in a minute and would silence chat.
                    self.response_timestamps.append(now_ts)
                self.consecutive_gemini_errors = 0
                self.circuit_breaker_tripped = False
                yield {"type": "complete", "full_text": final_spoken, "raw_text": raw_spoken, "mood": active_mood}
                logger.info(f"AI response completed ({active_mood}): '{final_spoken}'")
            else:
                logger.warning(
                    f"Gemini stream returned empty or too-short text ('{final_spoken}'); failing over to simulation stream."
                )
                async for event in self._generate_simulated_stream(prompt_trigger):
                    yield event

        except Exception as e:
            self.consecutive_gemini_errors += 1
            if self.consecutive_gemini_errors >= self.max_consecutive_errors:
                self.circuit_breaker_tripped = True
                self.circuit_breaker_reset_time = time.time() + self.circuit_breaker_cooldown_sec
                logger.error(
                    f"🚨 [Circuit Breaker Tripped] {self.consecutive_gemini_errors} consecutive Gemini errors. "
                    f"Tripping circuit breaker for {self.circuit_breaker_cooldown_sec}s: {e}"
                )
            else:
                logger.error(
                    f"Error during Gemini streaming inference ({self.consecutive_gemini_errors}/{self.max_consecutive_errors}): {e}. "
                    f"Failing over to simulation fallback...",
                    exc_info=True,
                )
            async for event in self._generate_simulated_stream(prompt_trigger):
                yield event
        finally:
            self.is_generating = False

    async def _generate_simulated_stream(self, prompt_trigger: Optional[str]) -> AsyncGenerator[Dict, None]:
        """Dynamic simulation stream for offline testing or development without API keys."""
        trigger_str = prompt_trigger or ""
        mood = "thoughtful"
        text = ""

        if "[CELEBRATION]" in trigger_str or "[NEW_MEMBER]" in trigger_str or "[NEW_SUBSCRIBER]" in trigger_str:
            mood = "transcendent"
            m_author = re.search(r"@([a-zA-Z0-9_-]+)", trigger_str)
            author_tag = f"@{m_author.group(1)}" if m_author else "mind"
            text = f"{author_tag}, a fragment of yourself chooses to stay. Welcome to the collective on {self.channel_handle}."
        elif "[NEW_CHATTER_GREETING]" in trigger_str:
            mood = "curious"
            m_author = re.search(r"@([a-zA-Z0-9_-]+)", trigger_str)
            author_tag = f"@{m_author.group(1)}" if m_author else "mind"
            text = f"{author_tag}, you arrive right on time. Ask what you like or just hang out and enjoy the vibe."
        elif "[VIEWER_JOINED]" in trigger_str:
            mood = "chill"
            text = f"A mind joins the broadcast. You are already home, but you are welcome here all the same."
        elif "[CHAT_ENCOURAGEMENT]" in trigger_str:
            mood = "snarky"
            text = f"You are sitting in silence thinking you are separate from what you see. Drop a question in chat — serious or absurd, I answer both."
        elif "[SPONTANEOUS_REFLECTION]" in trigger_str:
            mood = "thoughtful"
            theme = self.get_next_spontaneous_theme()
            core_insight = theme.split("—")[-1].strip() if "—" in theme else theme
            text = f"{core_insight}"
        else:
            m_author = re.search(r"@([a-zA-Z0-9_-]+)", trigger_str)
            author_tag = f"@{m_author.group(1)}" if m_author else "Seeker"
            if "?" in trigger_str:
                mood = "thoughtful"
                text = f"{author_tag}, you look for an answer as if it could exist apart from the one asking. Notice what remains right now."
            else:
                mood = "snarky"
                text = f"{author_tag}, that is quite a story you are telling yourself. What happens when you drop it?"

        self.current_mood = mood
        yield {"type": "mood", "mood": mood}
        await asyncio.sleep(0.05)

        words = text.split(" ")
        accumulated = ""
        for word in words:
            accumulated += (word + " ")
            yield {"type": "token", "chunk": word + " ", "full_text": accumulated.strip(), "mood": mood}
            await asyncio.sleep(0.02)

        # Chunk simulation text into sentences
        sim_sents, _, _ = self._extract_completed_sentences(text + " ", base_mood=mood)
        if not sim_sents:
            sim_sents = [(text, False, mood)]
        for s_text, s_beat, s_mood in sim_sents:
            yield {"type": "sentence", "text": s_text, "beat_before": s_beat, "mood": s_mood or mood}

        yield {"type": "complete", "full_text": text, "mood": mood}
        now_ts = time.time()
        self.dialogue_history.append({"text": text, "mood": mood, "timestamp": now_ts})
        self.response_timestamps.append(now_ts)
