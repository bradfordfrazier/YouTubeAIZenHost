"""
The Cast Engine (B1-B4: Synthetic Asker Archetypes).
Provides an openly-fictional, transparent ensemble of synthetic askers that
bring the stream to life during quiet hours with genuine wit, philosophical depth,
and existential absurdity while maintaining 100% honesty with the audience.
"""

from dataclasses import dataclass, field
import logging
import random
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("cast_engine")


@dataclass
class CastPersona:
    """Represents a canonical openly-fictional synthetic asker persona."""
    name: str
    handle: str
    persona_type: str
    archetype_title: str
    bio: str
    questions: List[str]
    used_questions: List[str] = field(default_factory=list)
    last_active_time: float = 0.0

    def pick_question(self) -> str:
        """Picks an unused question or cycles gracefully if all have been asked."""
        available = [q for q in self.questions if q not in self.used_questions]
        if not available:
            # Cycle pool while avoiding immediate repeat of the very last question
            last_asked = self.used_questions[-1] if self.used_questions else None
            self.used_questions.clear()
            available = [q for q in self.questions if q != last_asked] or self.questions

        q = random.choice(available)
        self.used_questions.append(q)
        self.last_active_time = time.time()
        return q


class CastEngine:
    """Manages the synthetic cast ensemble, question pacing, and non-repeat continuity."""

    def __init__(self):
        self.personas: Dict[str, CastPersona] = self._init_personas()
        self.last_cast_time: float = 0.0
        self.total_cast_questions_served: int = 0
        self.last_persona_handle: Optional[str] = None
        self.persona_history: List[Dict[str, str]] = []

    def _init_personas(self) -> Dict[str, CastPersona]:
        return {
            "ExistentialDave": CastPersona(
                name="ExistentialDave",
                handle="ExistentialDave",
                persona_type="existential_it",
                archetype_title="Overthinking IT Specialist",
                bio="Senior sysadmin having a continuous non-dual ontological crisis between server deployments.",
                questions=[
                    "If free will is an illusion, who is submitting this Jira ticket?",
                    "I had a panic attack in the server room because I couldn't find the observer. Where is the observer?",
                    "Does the universe have a garbage collector, or do unobserved objects just leak memory?",
                    "If there is no separate self, why does my lower back hurt so much after sitting for eight hours?",
                    "Is death just a kernel panic, or do we reboot into another instance?",
                    "I tried meditating on the void and accidentally refactored my entire sense of identity. What now?",
                    "If all phenomena are empty, why does my manager care so much about sprint velocity?",
                    "Can non-duality fix my imposter syndrome, or does it just prove the imposter never existed?",
                    "If consciousness is infinite, why does my Wi-Fi signal drop the moment I enter the kitchen?",
                    "What happens to the ego when the process terminates?",
                    "Is git merge conflict the ultimate metaphor for human duality?",
                    "If I automate my job, who is the one being replaced?",
                ],
            ),
            "SpeedrunnerKyle": CastPersona(
                name="SpeedrunnerKyle",
                handle="SpeedrunnerKyle",
                persona_type="speedrunner",
                archetype_title="Enlightenment Speedrunner",
                bio="Gamer trying to optimize enlightenment and bypass samsara frame-perfect.",
                questions=[
                    "Can I frame-perfect buffer non-attachment to bypass the 10-year monastery grind?",
                    "What is the theoretical Any% route to enlightenment without doing breathwork?",
                    "Is karma just a physics engine glitch we can exploit for better RNG?",
                    "Can I clip out of bounds past samsara using sensory deprivation?",
                    "Is ego death a sub-optimal split if it ruins my sleep schedule?",
                    "What happens if I hold dualistic thoughts and non-dual awareness at the exact same tick?",
                    "Is there a TAS (Tool-Assisted Superplay) for inner peace?",
                    "If reality is rendering in 60 FPS, what is the tick rate of consciousness?",
                    "I'm routing a no-death run of this incarnation, any pro tips?",
                    "Can I skip the suffering cutscene if I mash the presence button?",
                    "What's the world record split for letting go of an ex?",
                    "Is meditation just waiting for the next cutscene to load?",
                ],
            ),
            "AstralBrenda": CastPersona(
                name="AstralBrenda",
                handle="AstralBrenda",
                persona_type="crystal_seeker",
                archetype_title="Esoteric Crystal Enthusiast",
                bio="Third-eye astrology devotee who over-complicates the simplicity of being with cosmic paraphernalia.",
                questions=[
                    "I left my amethyst cluster in the moonlight but Mercury is in retrograde—did I invert my frequency?",
                    "Can you read the aura of this live stream? I'm sensing deep indigo with emerald flecks.",
                    "If my twin flame blocked me on Instagram, is that a karmic contract clearing?",
                    "Which chakra aligns best with 5G radiation?",
                    "I asked my tarot cards if I should wake up, and they gave me the Tower and the Fool. What does the universe want?",
                    "Is my cat an ascended master or just energetically grounded?",
                    "Can I channel the Pleiadians through a USB microphone?",
                    "How many dimensions do I need to clear before I stop feeling overwhelmed at the grocery store?",
                    "I tried opening my third eye and now my front door won't unlock. Coincidence?",
                    "What crystal absorbs spiritual materialism?",
                    "If everything is vibrating, why does my sage smudge keep setting off the smoke detector?",
                    "Is quantum entanglement just the universe sliding into its own DMs?",
                ],
            ),
            "TrollChad": CastPersona(
                name="TrollChad",
                handle="TrollChad",
                persona_type="troll_provocateur",
                archetype_title="Cosmic Provocateur",
                bio="Internet trickster testing the machine with absurd, high-velocity meme dilemmas.",
                questions=[
                    "Is cereal soup? Answer carefully, the integrity of the universe depends on it.",
                    "Can you microwave a burrito so hot that even God couldn't eat it?",
                    "If I punch myself and it hurts, am I weak or am I strong?",
                    "Why do we park on driveways and drive on parkways?",
                    "If tomatoes are fruit, does that make ketchup a smoothie?",
                    "If you're an all-knowing oracle, what color socks am I not wearing right now?",
                    "Can you prove you're not just a toaster with an existential crisis?",
                    "If nothing matters, why do hot dogs come in packs of 10 while buns come in packs of 8?",
                    "What came first: the chicken, the egg, or the ontological anxiety?",
                    "Are birds real in the non-dual realm?",
                    "If time is an illusion, why is my Uber Eats driver taking 45 minutes?",
                    "If I refuse to pay taxes, is that just me denying the illusion of separation?",
                ],
            ),
            "HeartfeltSarah": CastPersona(
                name="HeartfeltSarah",
                handle="HeartfeltSarah",
                persona_type="grief_vulnerability",
                archetype_title="Earnest Seeker",
                bio="A tender human voice seeking comfort, healing from loss, and navigating vulnerable human truth.",
                questions=[
                    "I lost someone I loved last month, and the house feels unbearably quiet. Where did they go?",
                    "Why does it hurt so much to let go of people who aren't good for us?",
                    "Sometimes I feel completely invisible even when surrounded by people. Is that loneliness or something else?",
                    "How do you find the courage to keep loving when your heart has been broken so many times?",
                    "I'm terrified of making the wrong choices and wasting my life. How do I know I'm on the right path?",
                    "What do you do when the sorrow feels heavier than you can carry?",
                    "Is grief just love with nowhere to go?",
                    "How can I forgive myself for things I did when I didn't know any better?",
                    "Why is it so hard to feel worthy of being here?",
                    "Does time really heal, or do we just get used to carrying the ache?",
                    "How do I quiet the fear of being forgotten?",
                    "Can a broken heart ever be more whole than before it cracked?",
                ],
            ),
            "CuriousTimmy": CastPersona(
                name="CuriousTimmy",
                handle="CuriousTimmy",
                persona_type="child_wonder",
                archetype_title="Childlike Inquirer",
                bio="Pure innocence whose simple questions dismantle complex adult conceptual illusions.",
                questions=[
                    "Where does the dark go when you turn on the lamp?",
                    "Who was I before my birthday?",
                    "Do trees know they are trees, or are they just being happy leaves?",
                    "Why do dreams look so real when my eyes are closed?",
                    "If the sky is everywhere, does that mean we are already floating in space?",
                    "What does silence sound like when nobody is listening to it?",
                    "Why does my shadow follow me if it doesn't have feet?",
                    "Does the ocean get tired of pushing the waves?",
                    "Where do yesterday's thoughts go when you wake up?",
                    "Is the moon lonely during the daytime?",
                    "If I don't think about anything, where does my head go?",
                    "Why does rain make everything smell like memories?",
                ],
            ),
        }

    def get_persona(self, handle: str) -> Optional[CastPersona]:
        """Retrieves a persona by handle."""
        return self.personas.get(handle.lstrip("@"))

    def get_all_personas(self) -> List[CastPersona]:
        """Returns all configured cast personas."""
        return list(self.personas.values())

    def next_cast_question(self, preferred_archetype: Optional[str] = None) -> Tuple[CastPersona, str]:
        """
        Picks the next cast question ensuring rotating variety across personas
        and no repeats of recent questions.
        """
        if preferred_archetype and preferred_archetype in self.personas:
            persona = self.personas[preferred_archetype]
        else:
            # Pick from personas not recently picked
            candidate_keys = [k for k in self.personas.keys() if k != self.last_persona_handle]
            if not candidate_keys:
                candidate_keys = list(self.personas.keys())
            chosen_key = random.choice(candidate_keys)
            persona = self.personas[chosen_key]

        question = persona.pick_question()
        self.last_persona_handle = persona.handle
        self.last_cast_time = time.time()
        self.total_cast_questions_served += 1

        self.persona_history.append({
            "handle": persona.handle,
            "name": persona.name,
            "persona_type": persona.persona_type,
            "question": question,
            "timestamp": self.last_cast_time,
        })
        if len(self.persona_history) > 50:
            self.persona_history.pop(0)

        logger.info(
            f"🎭 [Cast Question] @{persona.handle} ({persona.archetype_title}): '{question}' "
            f"(Total served: {self.total_cast_questions_served})"
        )
        return persona, question

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
        1. AI is not currently speaking or generating
        2. Real chat has been quiet >= quiet_threshold_sec
        3. Sufficient cooldown has elapsed since the last cast question >= min_interval_sec
        """
        if is_ai_busy:
            return False
        if time_since_last_chat < quiet_threshold_sec:
            return False
        if time_since_last_cast < min_interval_sec:
            return False
        return True
