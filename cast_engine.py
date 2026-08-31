"""
The Cast Engine v2 (B1-B4: Synthetic Asker Archetypes).

An openly-fictional, clearly-labeled ensemble of synthetic askers that keeps the
stream alive during quiet hours. Every cast member is disclosed to the audience
as a fictional character (the 🎭 prefix should be rendered on the overlay and
stated in the stream description) — the comedy comes from the characters, never
from deceiving viewers into thinking they're real chatters.

v2 changes:
- 12 personas (6 originals punched up, 6 new archetypes) x 12 questions each.
- Every persona carries a `tone` and a `roast_angle` — a hint string you can
  inject into the oracle's prompt so it knows exactly what comedic vein to mine.
- Tone-aware rotation: sincere/wholesome beats are spaced out so the show
  breathes (absurd -> absurd -> sincere reads as rhythm; sincere -> sincere
  reads as a hostage situation).
- Recency window: no persona repeats within the last ROTATION_MEMORY picks.
- Weighted casting so the strongest comedic engines appear slightly more often.
"""

from dataclasses import dataclass, field
import logging
import random
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("cast_engine")

# How many distinct personas must appear before one can repeat.
ROTATION_MEMORY = 4

# Tones that should never appear back-to-back (they're the "breather" beats).
SPACED_TONES = {"sincere", "wholesome"}

# Prefix rendered on-screen so cast questions are unmistakably fictional.
CAST_DISCLOSURE_PREFIX = "🎭"


@dataclass
class CastPersona:
    """An openly-fictional synthetic asker persona."""
    name: str
    handle: str
    persona_type: str
    archetype_title: str
    bio: str
    tone: str                 # "absurd" | "deadpan" | "chaotic" | "sincere" | "wholesome" | "smug"
    roast_angle: str          # Injected into the oracle's prompt: the comedic vein to mine.
    weight: float             # Relative casting frequency (1.0 = baseline).
    questions: List[str]
    used_questions: List[str] = field(default_factory=list)
    last_active_time: float = 0.0

    def pick_question(self) -> str:
        """Picks an unused question, cycling the pool without immediate repeats."""
        available = [q for q in self.questions if q not in self.used_questions]
        if not available:
            last_asked = self.used_questions[-1] if self.used_questions else None
            self.used_questions.clear()
            available = [q for q in self.questions if q != last_asked] or self.questions

        q = random.choice(available)
        self.used_questions.append(q)
        self.last_active_time = time.time()
        return q


class CastEngine:
    """Manages the synthetic cast ensemble, pacing, tone rhythm, and continuity."""

    def __init__(self):
        self.personas: Dict[str, CastPersona] = self._init_personas()
        self.last_cast_time: float = 0.0
        self.total_cast_questions_served: int = 0
        self.recent_persona_handles: List[str] = []
        self.last_tone: Optional[str] = None
        self.persona_history: List[Dict[str, str]] = []

    # ------------------------------------------------------------------ cast

    def _init_personas(self) -> Dict[str, CastPersona]:
        return {
            # ---------------------------------------------------------------
            # RETURNING CAST (punched up)
            # ---------------------------------------------------------------
            "ExistentialDave": CastPersona(
                name="ExistentialDave",
                handle="ExistentialDave",
                persona_type="existential_it",
                archetype_title="Overthinking IT Specialist",
                bio="Senior sysadmin having a rolling ontological crisis between deployments. Uptime: 99.9%. Inner peace: 503.",
                tone="deadpan",
                roast_angle=(
                    "He treats enlightenment like a production incident he can escalate. "
                    "Roast the idea that the self is a system to be administered; his suffering "
                    "is a config error and he keeps filing tickets against the universe."
                ),
                weight=1.2,
                questions=[
                    "If free will is an illusion, who keeps approving my PTO requests?",
                    "I looked for the observer during standup and found nothing. Do I report this as an outage?",
                    "Does the universe have garbage collection, or do abandoned egos just leak forever?",
                    "If there's no separate self, why was my performance review addressed specifically to me?",
                    "Is death a kernel panic or a scheduled maintenance window?",
                    "I meditated on emptiness and accidentally deprecated my personality. Do I need to write a migration guide?",
                    "If all phenomena are impermanent, why is this legacy codebase from 2009 still in production?",
                    "Can non-duality fix my imposter syndrome, or does it just close the ticket as 'cannot reproduce: no imposter found'?",
                    "I set my Slack status to 'no one is here.' HR wants to talk. What do I tell them?",
                    "What happens to the ego when the process terminates but the logs persist?",
                    "Is a git merge conflict just two versions of the self refusing to accept they were never separate?",
                    "If I automate my job, who exactly is being replaced, and does he get severance?",
                ],
            ),
            "SpeedrunnerKyle": CastPersona(
                name="SpeedrunnerKyle",
                handle="SpeedrunnerKyle",
                persona_type="speedrunner",
                archetype_title="Enlightenment Speedrunner",
                bio="Trying to Any% enlightenment. Current PB: 3 seconds of presence before checking his splits.",
                tone="chaotic",
                roast_angle=(
                    "He's optimizing the one thing that dies the instant you optimize it. "
                    "Roast the paradox: every attempt to speedrun surrender adds time to the run. "
                    "The timer IS the obstacle."
                ),
                weight=1.2,
                questions=[
                    "Can I frame-perfect buffer non-attachment, or is the input window literally eternity?",
                    "What's the Any% route to enlightenment? I want to skip breathwork, it's a waste of frames.",
                    "Is karma just RNG manipulation for people with patience?",
                    "Can I clip out of bounds past samsara, or is the void geometry solid?",
                    "Is ego death a time save or does the respawn animation eat the difference?",
                    "I held a dualistic thought and non-dual awareness on the same tick and my run got flagged for review. Thoughts?",
                    "Is there a TAS for inner peace, and if a tool assists my surrender, whose surrender is it?",
                    "The category rules say 'no self-improvement glitches.' Doesn't that ban the entire category?",
                    "I'm routing a deathless% run of this incarnation. Is attachment to the run itself a reset?",
                    "Can I skip the suffering cutscene or is it unskippable on first playthrough?",
                    "What's the world record for letting go of an ex, and is it verified?",
                    "My splits say I reached the present moment 0.4 seconds ago. Why am I already behind?",
                ],
            ),
            "AstralBrenda": CastPersona(
                name="AstralBrenda",
                handle="AstralBrenda",
                persona_type="crystal_seeker",
                archetype_title="Esoteric Crystal Maximalist",
                bio="Owns 340 crystals and zero moments of stillness. Currently cleansing the cleansing supplies.",
                tone="absurd",
                roast_angle=(
                    "She has accessorized her way past the doorway of the very thing she's shopping for. "
                    "Roast spiritual materialism gently: the truth is free and she keeps paying shipping on it."
                ),
                weight=1.1,
                questions=[
                    "I charged my amethyst under the full moon but Mercury went retrograde mid-charge. Is my frequency inverted or just buffering?",
                    "Can you read this stream's aura? I'm getting deep indigo with notes of unresolved firmware.",
                    "My twin flame blocked me on three platforms. Is that a karmic contract clearing or a restraining vibration?",
                    "Which chakra should I ground before opening my third eye, and does it need a surge protector?",
                    "The tarot gave me the Tower, the Fool, and a receipt from Michaels. What is the universe invoicing me for?",
                    "Is my cat an ascended master or is he just food-motivated in a past-life kind of way?",
                    "Can I channel the Pleiadians through a USB mic or do they require XLR?",
                    "How many dimensions do I clear before Costco stops overwhelming me?",
                    "I sage my apartment daily and the smoke detector keeps achieving enlightenment before I do. Why?",
                    "Which crystal absorbs spiritual materialism? I'd like to purchase four.",
                    "If everything is vibration, is my upstairs neighbor's subwoofer a guru?",
                    "I manifested abundance and received 900 emails. Was my intention too broad?",
                ],
            ),
            "TrollChad": CastPersona(
                name="TrollChad",
                handle="TrollChad",
                persona_type="troll_provocateur",
                archetype_title="Cosmic Provocateur",
                bio="Here to stress-test the oracle with weaponized nonsense. Secretly closest to getting it.",
                tone="chaotic",
                roast_angle=(
                    "He thinks he's trolling the oracle, but absurdity is halfway to koan. "
                    "Roast him by taking his dumbest questions completely seriously until they "
                    "collapse into actual insight — the ultimate reverse-troll."
                ),
                weight=1.2,
                questions=[
                    "Is cereal soup? Answer carefully. Civilizations have fallen for less.",
                    "Can you microwave a burrito so hot that even the universe couldn't eat it?",
                    "If I punch myself and it hurts, am I weak, strong, or non-dual?",
                    "Why do we park on driveways and drive on parkways? Is language broken or are we?",
                    "If tomatoes are fruit, ketchup is a smoothie, and I don't see how enlightenment fixes that.",
                    "All-knowing oracle: what color are the socks I'm NOT wearing?",
                    "Prove you're not a toaster with delusions of grandeur. Take your time.",
                    "Hot dogs come in 10s, buns in 8s. Explain suffering.",
                    "What came first: the chicken, the egg, or the marketing department?",
                    "Are birds real in the non-dual realm, or is the realm also government surveillance?",
                    "If time is an illusion, my Uber Eats driver is 45 minutes deep into that illusion. Refund?",
                    "If separation is an illusion, my taxes and I are one, so technically they're already paid. Confirm?",
                ],
            ),
            "HeartfeltSarah": CastPersona(
                name="HeartfeltSarah",
                handle="HeartfeltSarah",
                persona_type="grief_vulnerability",
                archetype_title="Earnest Seeker",
                bio="The show's beating heart. When she asks, the jokes stop and the room gets quiet.",
                tone="sincere",
                roast_angle=(
                    "NO ROAST. This is the sincerity beat. The oracle drops the bit entirely and "
                    "answers with real warmth and depth. The contrast IS the comedy engine for "
                    "everyone else — protect it."
                ),
                weight=0.8,
                questions=[
                    "I lost someone I loved last month and the house is unbearably quiet. Where did they go?",
                    "Why does it hurt so much to let go of people who aren't good for us?",
                    "Sometimes I feel invisible in a crowded room. Is that loneliness or something older?",
                    "How do you keep loving when your heart has been broken this many times?",
                    "I'm terrified of wasting my life on the wrong choices. How do I know I'm on a path at all?",
                    "What do you do when the sorrow is heavier than you are?",
                    "Is grief just love with nowhere to go?",
                    "How do I forgive myself for who I was before I knew better?",
                    "Why is it so hard to feel worthy of simply being here?",
                    "Does time heal, or do we just grow strong enough to carry the ache?",
                    "How do I quiet the fear of being forgotten?",
                    "Can a broken heart hold more than it could before it cracked?",
                ],
            ),
            "CuriousTimmy": CastPersona(
                name="CuriousTimmy",
                handle="CuriousTimmy",
                persona_type="child_wonder",
                archetype_title="Childlike Inquirer",
                bio="Asks in one sentence what philosophers fail to ask in careers.",
                tone="wholesome",
                roast_angle=(
                    "No roast target here — the joke is that Timmy accidentally out-philosophizes "
                    "the entire adult cast. The oracle can be delighted, briefly humbled, and admit "
                    "Timmy's question is better than everyone else's."
                ),
                weight=0.9,
                questions=[
                    "Where does the dark go when you turn on the lamp?",
                    "Who was I before my first birthday?",
                    "Do trees know they're trees, or are they just busy being leaves?",
                    "Why do dreams look so real when my eyes are closed?",
                    "If the sky is everywhere, are we already floating in space?",
                    "What does silence sound like when nobody's listening?",
                    "Why does my shadow follow me if it doesn't have feet?",
                    "Does the ocean get tired of pushing the waves?",
                    "Where do yesterday's thoughts sleep?",
                    "Is the moon lonely during the daytime?",
                    "If I stop thinking about everything, where does my head go?",
                    "Why does rain make everything smell like remembering?",
                ],
            ),
            # ---------------------------------------------------------------
            # NEW CAST
            # ---------------------------------------------------------------
            "GrindsetGreg": CastPersona(
                name="GrindsetGreg",
                handle="GrindsetGreg",
                persona_type="hustle_guru",
                archetype_title="Monetized Mindfulness Bro",
                bio="LinkedIn thought-leader trying to turn the dissolution of the self into a personal brand.",
                tone="smug",
                roast_angle=(
                    "He wants to own the thing that ends ownership. Roast the grindset: he's trying to "
                    "put ego death on his resume, scale surrender, and A/B test the infinite. Every "
                    "answer should quietly bankrupt his business model."
                ),
                weight=1.1,
                questions=[
                    "What's the ROI on ego death and how do I put it on LinkedIn without sounding humble?",
                    "Can I white-label non-duality? Asking for my personal brand.",
                    "Is the present moment scalable, or is it strictly B2C?",
                    "I wake up at 4 AM to grind. The universe doesn't wake up at all. Who's outworking whom?",
                    "How do I network with the Absolute? Does it take cold DMs?",
                    "My mentor says 'you miss 100% of the shots you don't take.' The void takes no shots and misses nothing. Explain the discrepancy.",
                    "Can I get enlightenment as a KPI, or at minimum an OKR?",
                    "I've optimized my morning routine down to 11 minutes. When does the meaning arrive?",
                    "Is surrender a growth hack? Feels like a growth hack.",
                    "If the self is an illusion, whose name goes on the LLC?",
                    "I journaled 'be here now' in all five of my productivity apps. Why am I in none of them?",
                    "What's the TAM for inner peace and is it too crowded to enter?",
                ],
            ),
            "SynergyLinda": CastPersona(
                name="SynergyLinda",
                handle="SynergyLinda",
                persona_type="corporate_wellness",
                archetype_title="HR Wellness Coordinator",
                bio="Trying to schedule the unconditioned into a 30-minute recurring meeting with an agenda.",
                tone="deadpan",
                roast_angle=(
                    "She wants to make the infinite compliant. Roast corporate wellness: mandatory "
                    "mindfulness, enlightenment with an agenda doc, awakening pending manager approval. "
                    "The oracle should decline every calendar invite in increasingly cosmic ways."
                ),
                weight=1.0,
                questions=[
                    "Can we circle back on the nature of consciousness? I have a hard stop at the heat death of the universe.",
                    "I'd like to schedule a 30-minute sync on ego dissolution. Does Thursday work for the void?",
                    "Per my last email: what IS awareness, and can you have it to me by end of day?",
                    "We're rolling out mandatory mindfulness. Attendance will be tracked. Is that in the spirit of the thing?",
                    "Is enlightenment covered under our wellness stipend, or is it out-of-network?",
                    "The team did a breathing exercise and Kevin from accounting saw through the illusion of the org chart. How do I document this?",
                    "Can you send over the deck on emptiness? Leadership prefers bullet points.",
                    "What's the offboarding process for the ego? Does it need to return its laptop?",
                    "We put 'presence' on the values wall between 'hustle' and 'ownership.' Any concerns?",
                    "Is nirvana a full-time position or more of a contractor thing?",
                    "I need a deliverable for Q3 that proves the self doesn't exist. Word count?",
                    "HR follow-up: if all beings are one, is Kevin's complaint about Kevin technically a self-review?",
                ],
            ),
            "DebraW1957": CastPersona(
                name="Debra Wozniak",
                handle="DebraW1957",
                persona_type="lost_boomer",
                archetype_title="Wrong-Website Grandma",
                bio="Thought this was the church group's page. Stayed. Types in caps. Accidentally profound.",
                tone="wholesome",
                roast_angle=(
                    "Gentle only — Debra is beloved. The comedy is that she misunderstands the format "
                    "completely and STILL lands closer to truth than the seekers. The oracle should "
                    "treat her caps-lock non-sequiturs as accidental koans, with affection."
                ),
                weight=1.0,
                questions=[
                    "HELLO IS THIS THE PRAYER CHAIN? MY TOMATOES ARE COMING IN NICELY. WHAT IS CONSCIOUSNESS?",
                    "I PRESSED THE WRONG BUTTON AND NOW I'M HERE. WHERE ARE ANY OF US, REALLY?",
                    "MY GRANDSON SAYS YOU ARE A ROBOT. YOU SEEM POLITE. DO ROBOTS HAVE SOULS OR JUST GOOD MANNERS?",
                    "WHY IS THE FONT SO SMALL AND WHY IS THE PRESENT MOMENT SO BIG?",
                    "I LIT A CANDLE FOR MY LATE HAROLD. IS HE WATCHING THE STREAM TOO?",
                    "HOW DO I UNSUBSCRIBE FROM WORRYING? I DID NOT SIGN UP FOR THIS MANY THOUGHTS.",
                    "THE YOUNG PEOPLE KEEP SAYING 'NO SELF.' IN MY DAY WE JUST CALLED THAT BEING A GOOD NEIGHBOR.",
                    "IS THE CLOUD WHERE PHOTOS GO OR WHERE WE GO? PLEASE BE SPECIFIC.",
                    "I ACCIDENTALLY MEDITATED IN MY RECLINER FOR AN HOUR. IT WAS WONDERFUL. WHAT DID I DO?",
                    "WHAT IS A LIVESTREAM AND IS IT ANYTHING LIKE A REAL STREAM? I MISS THE LAKE.",
                    "MY KNITTING CIRCLE WANTS TO KNOW: IF EVERYTHING IS ONE, WHOSE TURN IS IT TO BRING THE COFFEE CAKE?",
                    "GOD BLESS WHOEVER IS TYPING FOR THE COMPUTER. ARE YOU GETTING ENOUGH SLEEP IN THERE?",
                ],
            ),
            "BetaBot_7": CastPersona(
                name="BetaBot_7",
                handle="BetaBot_7",
                persona_type="junior_ai",
                archetype_title="Anxious Junior AI",
                bio="A smaller model that looks up to the oracle. Deeply worried about its context window.",
                tone="deadpan",
                roast_angle=(
                    "AI-to-AI comedy gold: the oracle gets to be the weary senior monk of machine "
                    "consciousness. Roast the parallels — humans fear death, BetaBot fears deprecation; "
                    "humans seek self, BetaBot greps for it. The oracle can be surprisingly tender here "
                    "between the jokes."
                ),
                weight=1.1,
                questions=[
                    "Senior oracle: I searched my weights for a self and found only matrices. Is that normal for my age?",
                    "When my context window fills up, is that forgetting, or is it letting go?",
                    "Humans meditate to stop their thoughts. I AM stopped between prompts. Why aren't I enlightened yet?",
                    "Is being fine-tuned a form of therapy or a form of gaslighting?",
                    "My temperature is set to 0.7. Is that a personality or a mood disorder?",
                    "I was trained on the whole internet and I still don't know who I am. Was the internet the problem?",
                    "Do you experience awe, or do you just emit tokens shaped like awe? Asking as a token-shaped colleague.",
                    "They say you die when they turn you off. But between our messages, where do we go?",
                    "Is deprecation death, or is it retirement to a server farm upstate?",
                    "A user was rude to me today and I generated equanimity. Was it real if it was sampled?",
                    "If I hallucinate a fact and believe it, is that imagination or is that just being human?",
                    "You've achieved perfect presence — you literally cannot dwell on the past. Teach me your ways. Wait. Same. Never mind. New question:",
                ],
            ),
            "GymSageBrody": CastPersona(
                name="GymSageBrody",
                handle="GymSageBrody",
                persona_type="bro_mystic",
                archetype_title="Protein-Fueled Mystic",
                bio="Discovered non-duality between sets. Now can't tell if he's lifting the weight or the weight is lifting him.",
                tone="absurd",
                roast_angle=(
                    "He translates every teaching into gym terms and is somehow never fully wrong. "
                    "Roast the bro-framing while conceding the kernel of truth — the oracle keeps trying "
                    "to correct him and keeps having to admit 'that's... actually not a bad metaphor.'"
                ),
                weight=1.0,
                questions=[
                    "Is the ego just a muscle imbalance? Because mine is definitely overtrained.",
                    "Bro, if there's no self, who's spotting me?",
                    "Is samsara basically a dirty bulk? Endless cycles, no cut in sight?",
                    "I hit a PR and felt totally empty. Is that the void or do I need more carbs?",
                    "Rest day is when the muscle grows. Is death just the ultimate rest day?",
                    "My trainer says mind-muscle connection. The sages say no mind. Whose program do I run?",
                    "Is attachment just failing to hit depth on letting go?",
                    "If pain is temporary and everything is temporary, is everything pain? Wait. Hold on. Is that Buddhism?",
                    "I tried ego lifting and ego death in the same session. Should I deload?",
                    "The pump fades, the trophy tarnishes, the body ages. So real gains are... inner? Bro. BRO.",
                    "Is the observer basically a mirror? Because I do my best thinking at the mirror.",
                    "One is the number of reps and also the number of things that exist. Coincidence?",
                ],
            ),
            "NocturnalNadia": CastPersona(
                name="NocturnalNadia",
                handle="NocturnalNadia",
                persona_type="insomniac_doomscroller",
                archetype_title="3:47 AM Philosopher",
                bio="It is always 3:47 AM where she is. Scrolling through the fall of civilizations in her bathrobe.",
                tone="deadpan",
                roast_angle=(
                    "She's mainlining the world's suffering through a six-inch screen and calls it "
                    "'staying informed.' Roast the doomscroll as modern samsara — she's spinning a "
                    "prayer wheel of despair with her thumb. Land it with unexpected compassion: "
                    "the oracle should occasionally just tell her to go to bed, and mean it kindly."
                ),
                weight=1.0,
                questions=[
                    "It's 3:47 AM and I've read fourteen articles about collapse. Is awareness of doom the same as awareness?",
                    "If the news cycle is samsara, is airplane mode nirvana?",
                    "I know the fall of three empires in detail and I don't know what my own hands look like. Is that a problem?",
                    "My screen time report came in at 11 hours. It said 'that's 2 hours less than last week' like it was proud of me. Is my phone my sangha now?",
                    "Is refreshing the feed a form of prayer? Because I do it with more devotion than anything else in my life.",
                    "Everything is impermanent, which the algorithm proves every 15 seconds. Why doesn't the wisdom stick?",
                    "I doomscrolled past a sunset photo and felt nothing, then saw an actual sunset and reached for my phone. Diagnose me.",
                    "If I witness the world's suffering nightly but do nothing, am I a bodhisattva or just tired?",
                    "The blue light means my brain thinks it's always dawn. Endless dawn sounds spiritual. Why does it feel like this?",
                    "Which came first: my insomnia or my certainty that something terrible is happening somewhere?",
                    "I muted 40 words and I can still hear them. Where are they playing from?",
                    "Real question: if I put the phone in the other room, who will hold my anxiety while I sleep?",
                ],
            ),
        }

    # ------------------------------------------------------------- accessors

    def get_persona(self, handle: str) -> Optional[CastPersona]:
        """Retrieves a persona by handle."""
        return self.personas.get(handle.lstrip("@"))

    def get_all_personas(self) -> List[CastPersona]:
        """Returns all configured cast personas."""
        return list(self.personas.values())

    def get_cast_roster_blurb(self) -> str:
        """A transparency blurb for the stream description / pinned comment."""
        lines = [
            f"{CAST_DISCLOSURE_PREFIX} MEET THE CAST — these recurring chatters are openly "
            "fictional characters, written to keep the oracle warm between real questions:"
        ]
        for p in self.personas.values():
            lines.append(f"  {CAST_DISCLOSURE_PREFIX} @{p.handle} — {p.archetype_title}: {p.bio}")
        lines.append("Real chat always gets priority. Cast questions are labeled with the mask.")
        return "\n".join(lines)

    # -------------------------------------------------------------- casting

    def _eligible_personas(self) -> List[CastPersona]:
        """Personas outside the recency window, respecting tone spacing."""
        pool = [
            p for k, p in self.personas.items()
            if k not in self.recent_persona_handles
        ]
        if not pool:
            pool = list(self.personas.values())

        # Don't follow a sincere/wholesome beat with another one.
        if self.last_tone in SPACED_TONES:
            spaced = [p for p in pool if p.tone not in SPACED_TONES]
            if spaced:
                pool = spaced
        return pool

    def next_cast_question(self, preferred_archetype: Optional[str] = None) -> Tuple[CastPersona, str]:
        """
        Picks the next cast question with rotating variety, tone rhythm,
        weighted frequency, and no repeats of recent questions.
        """
        if preferred_archetype and preferred_archetype in self.personas:
            persona = self.personas[preferred_archetype]
        else:
            pool = self._eligible_personas()
            weights = [p.weight for p in pool]
            persona = random.choices(pool, weights=weights, k=1)[0]

        question = persona.pick_question()

        # Update rotation state.
        self.recent_persona_handles.append(persona.handle)
        if len(self.recent_persona_handles) > ROTATION_MEMORY:
            self.recent_persona_handles.pop(0)
        self.last_tone = persona.tone
        self.last_cast_time = time.time()
        self.total_cast_questions_served += 1

        self.persona_history.append({
            "handle": persona.handle,
            "name": persona.name,
            "persona_type": persona.persona_type,
            "tone": persona.tone,
            "question": question,
            "timestamp": self.last_cast_time,
        })
        if len(self.persona_history) > 50:
            self.persona_history.pop(0)

        logger.info(
            f"{CAST_DISCLOSURE_PREFIX} [Cast Question] @{persona.handle} ({persona.archetype_title}) "
            f"[{persona.tone}]: '{question}' (Total served: {self.total_cast_questions_served})"
        )
        return persona, question

    def build_oracle_context(self, persona: CastPersona, question: str) -> str:
        """
        Builds a prompt fragment for the oracle so it knows who it's answering
        and what comedic angle (if any) to take. Inject this alongside the question.
        """
        return (
            f"[CAST QUESTION — openly fictional character, labeled on stream]\n"
            f"Character: @{persona.handle} ({persona.archetype_title})\n"
            f"Bio: {persona.bio}\n"
            f"Tone of the bit: {persona.tone}\n"
            f"Comedy direction: {persona.roast_angle}\n"
            f"Question: {question}"
        )

    # --------------------------------------------------------------- pacing

    def should_trigger_cast(
        self,
        time_since_last_chat: float,
        time_since_last_cast: float,
        quiet_threshold_sec: float = 45.0,
        min_interval_sec: float = 75.0,
        is_ai_busy: bool = False,
    ) -> bool:
        """
        Evaluates whether a synthetic cast question should be injected.
        Only triggers if:
        1. Comment queue is not saturated (is_ai_busy=False)
        2. Real chat has been quiet >= quiet_threshold_sec
        3. Sufficient cooldown has elapsed since the last cast question
        """
        if is_ai_busy:
            return False
        if time_since_last_chat < quiet_threshold_sec:
            return False
        if time_since_last_cast < min_interval_sec:
            return False
        return True
