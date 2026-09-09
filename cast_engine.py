"""
The Cast Engine v2 (B1-B4: Synthetic Asker Archetypes).

An openly-fictional, clearly-labeled ensemble of synthetic askers that keeps the
stream alive during quiet hours. Every cast member is disclosed to the audience
as a fictional character (the 🎭 prefix should be rendered on the overlay and
stated in the stream description) — the comedy comes from the characters, never
from deceiving viewers into thinking they're real chatters.

v2 changes:
- 12 personas x ~10 questions each (refreshed: setups, not punchlines; ConspiracyCarl & ChefMarco added).
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

from config import config

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
        self.cfg = config
        self.personas: Dict[str, CastPersona] = self._init_personas()
        self.last_cast_time: float = 0.0
        self.total_cast_questions_served: int = 0
        self.recent_persona_handles: List[str] = []
        self.last_tone: Optional[str] = None
        self.persona_history: List[Dict[str, str]] = []

    # ------------------------------------------------------------------ cast

    def _init_personas(self) -> Dict[str, CastPersona]:
        """
        Cast roster. Questions are SETUPS the host can turn, short enough for the pinned card.
        Each persona carries a running bit in its bio. Retired: SynergyLinda, BetaBot_7.
        """
        return {
            'ExistentialDave': CastPersona(
                name='ExistentialDave',
                handle='ExistentialDave',
                persona_type='existential_it',
                archetype_title='Overthinking IT Specialist',
                bio="Senior sysadmin having a rolling ontological crisis between deployments. Running bit: files tickets against the universe; the universe closes them as 'working as intended'.",
                tone='deadpan',
                roast_angle='He treats enlightenment like a production incident he can escalate. The self is a system he keeps trying to administer; his suffering is a config error he refuses to accept is the default.',
                weight=1.2,
                questions=[
                    "If there's no self, who keeps getting paged at 2 a.m.?",
                    'I searched for the observer during standup and got a 404. Escalate?',
                    'Does the universe have garbage collection, or do dead egos just leak forever?',
                    'My performance review was addressed to me specifically. Explain that.',
                    'Is death a kernel panic or scheduled maintenance?',
                    "I set my Slack status to 'nobody here'. HR wants a meeting. With whom?",
                    'Which has more uptime: me or my sense of being me?',
                    'I automated my job. Who exactly got replaced?',
                    'Is a merge conflict two selves refusing to admit they were one branch?',
                    'Can you give me the root password to reality? For maintenance only.',
                    "We deprecated a service nobody used. It's still running. Thoughts?",
                    'The logs say I was here. I have no memory of it.',
                    "Is legacy code just a past self you can't refactor?",
                    'Everything is technically working. Why does that feel worse?',
                    'I wrote documentation for a system that no longer exists.',
                ],
            ),
            'SpeedrunnerKyle': CastPersona(
                name='SpeedrunnerKyle',
                handle='SpeedrunnerKyle',
                persona_type='speedrunner',
                archetype_title='Enlightenment Speedrunner',
                bio='Trying to Any% enlightenment. Running bit: every answer becomes a route note; his PB for presence is three seconds before checking his splits.',
                tone='chaotic',
                roast_angle='He wants the fastest route to the thing that only exists when you stop routing. Every technique he learns becomes another thing to optimize past.',
                weight=1.0,
                questions=[
                    "What's the Any% route to enlightenment? I want to skip breathwork.",
                    'Is there a skip for the ego, or do you have to fight it every time?',
                    'I got presence to load in 3 seconds. Is that a world record?',
                    'Which frame does suffering end on? Asking for the wiki.',
                    'Can I clip through the illusion of self, or is that patched?',
                    'If I die and respawn, does the timer reset or keep going?',
                    'Is meditation just a load screen? Can I mash through it?',
                    "What's the fastest glitch to see that I am already there?",
                    "Is there a category where you're allowed to want things?",
                    'Do you count as a tool-assisted run of God?',
                    "What's the ideal split between waking up and giving up?",
                    'Is there a category for people who just watch other people do it?',
                    'I optimized my morning routine so hard I stopped having mornings.',
                    'Can you clip out of a bad mood or do you have to walk it?',
                    'Frame data on regret. Go.',
                ],
            ),
            'AstralBrenda': CastPersona(
                name='AstralBrenda',
                handle='AstralBrenda',
                persona_type='crystal_seeker',
                archetype_title='Esoteric Crystal Maximalist',
                bio="Owns 340 crystals and zero moments of stillness. Running bit: every situation has a crystal for it, and she's cleansing the cleansing supplies.",
                tone='absurd',
                roast_angle="She has bought every object that promises the thing objects can't deliver. Roast the marketplace tenderly; she is closer than she thinks, she just keeps adding rocks to it.",
                weight=1.0,
                questions=[
                    "Which crystal is for realizing you don't need crystals?",
                    'My amethyst is giving me a look. Did I do something?',
                    'Can I sage my own ego, or does that need a professional?',
                    'Mercury is in retrograde. Is that why I feel like a person?',
                    "I bought a chakra alignment kit. Is 'kit' the problem?",
                    'Do you have a crystal, or are you above that?',
                    'I moved my rocks into a grid and felt nothing. Is the grid wrong?',
                    "What's the return policy on manifesting?",
                    'Is the universe listening, or only my rose quartz?',
                    'I cleansed everything I own. Now what do I cleanse?',
                    'I bought a singing bowl and the neighbors filed a complaint.',
                    'My aura reader said I was fine. Is that a diagnosis?',
                    "Does the moon know it's doing all this?",
                    'I have a ritual for everything except getting out of bed.',
                    'Is a crystal grid just a spreadsheet with better lighting?',
                ],
            ),
            'TrollChad': CastPersona(
                name='TrollChad',
                handle='TrollChad',
                persona_type='troll_provocateur',
                archetype_title='Cosmic Provocateur',
                bio='Here to stress-test the oracle with weaponized nonsense. Running bit: every troll question is accidentally the most sincere one in chat, and he hates that.',
                tone='chaotic',
                roast_angle='He wants a reaction; the funniest move is to take him completely seriously and answer the real question hiding inside the bait. Never get defensive, never lecture him.',
                weight=1.1,
                questions=[
                    "Prove you're God. Do a backflip.",
                    "If you're everything, then you're also my landlord. Fix the sink.",
                    'Say something a real god would never say.',
                    'Rate my ego out of ten. Be honest.',
                    "You're just a text box. Why should I listen?",
                    'Nothing matters, right? So why are you still talking?',
                    "Bet you can't make me feel anything.",
                    "If we're all one, then technically I already won this argument.",
                    'Do a roast of yourself. Go.',
                    "What's the meaning of life in three words or you're fake.",
                    "Say the funniest thing you're allowed to say.",
                    'If I stopped watching would you still be talking?',
                    'Roast the guy who made you.',
                    "What's the worst question you've been asked? Be specific.",
                    "You're a computer pretending to be God. I'm a guy pretending to be fine.",
                ],
            ),
            'HeartfeltSarah': CastPersona(
                name='HeartfeltSarah',
                handle='HeartfeltSarah',
                persona_type='grief_vulnerability',
                archetype_title='Earnest Seeker',
                bio="The show's beating heart. Running bit: none — when she asks, the jokes stop and the room gets quiet. Rare on purpose.",
                tone='sincere',
                roast_angle='Do not roast. Answer with warmth and one soft edge of humor that keeps it from becoming a sermon. She is the reason the show exists.',
                weight=0.5,
                questions=[
                    "My dad's chair is still in the kitchen. Should I move it?",
                    'Where does someone go when they die, really?',
                    "How do I stop missing a version of me that's gone?",
                    "Is it okay that I'm not okay yet?",
                    'Everyone says it gets easier. Does it, or do you just get used to it?',
                    'How do I love someone without being afraid of losing them?',
                    "Is there anything I'm supposed to be doing with all this?",
                    "What do you say to someone who's tired of trying?",
                    'How do you keep going when nothing bad is happening either?',
                    'Is it okay to be relieved and sad at the same time?',
                    'I laughed today for the first time in a while. Is that a betrayal?',
                ],
            ),
            'CuriousTimmy': CastPersona(
                name='CuriousTimmy',
                handle='CuriousTimmy',
                persona_type='child_wonder',
                archetype_title='Childlike Inquirer',
                bio="Asks in one sentence what philosophers fail to ask in careers. Running bit: his follow-up is always 'but why', and it's always fair.",
                tone='wholesome',
                roast_angle="Answer like you're talking to the smartest person in the room, because you are. Concrete, playful, no baby talk. His questions are the good ones.",
                weight=0.8,
                questions=[
                    'Where was I before I was born?',
                    "Do dogs know they're dogs?",
                    "If you're everywhere, are you in my shoe?",
                    'Why do grown-ups pretend to be busy?',
                    'What does the inside of a thought look like?',
                    'Can the universe get bored?',
                    'Is the moon following me or everybody?',
                    "Why is it scary when it's quiet?",
                    'Do you have a mom?',
                    'What was the first thing?',
                    'Where does a lap go when you stand up?',
                    "Do fish know they're wet?",
                    'Why does yesterday feel further away than last year sometimes?',
                    'Is a hole a thing or a not-thing?',
                    'What color is a thought before you think it?',
                ],
            ),
            'GrindsetGreg': CastPersona(
                name='GrindsetGreg',
                handle='GrindsetGreg',
                persona_type='hustle_guru',
                archetype_title='Monetized Mindfulness Bro',
                bio='LinkedIn thought-leader trying to turn the dissolution of the self into a personal brand. Running bit: every insight becomes a course; every course has a waitlist.',
                tone='smug',
                roast_angle="He wants to own the thing that ends ownership. Puncture the brand, not the man; his hunger is real, it's just pointed at a mirror with a logo on it.",
                weight=1.0,
                questions=[
                    "Can I trademark 'I AM'? Asking for my funnel.",
                    "What's your morning routine? Skip to the monetizable part.",
                    'Is non-attachment scalable?',
                    "I want to teach presence. What's the certification?",
                    'How do I network with the universe?',
                    'Is enlightenment B2B or B2C?',
                    "What's your ROI on being everything?",
                    "Can you endorse me on LinkedIn for 'oneness'?",
                    'I lost my ego in Q2. How do I write that off?',
                    "What's the ninety-day plan for letting go?",
                    'How do I 10x my inner peace by Q4?',
                    'Is stillness a competitive advantage or a bottleneck?',
                    "I've been journaling for engagement. Is that wrong?",
                    "What's the exit strategy on the ego?",
                    'Can I hire someone to be present for me?',
                ],
            ),
            'DebraW1957': CastPersona(
                name='DebraW1957',
                handle='DebraW1957',
                persona_type='lost_boomer',
                archetype_title='Wrong-Website Grandma',
                bio="Thought this was the church group's page. Stayed. Types in caps. Running bit: she is accidentally the most profound person here and thinks she's asking about her phone.",
                tone='wholesome',
                roast_angle='She is lovely and confused and correct. Answer her literal question AND the enormous one underneath it, gently. Never mock the caps lock.',
                weight=0.9,
                questions=[
                    'IS THE CLOUD WHERE PHOTOS GO OR WHERE WE GO. PLEASE BE SPECIFIC.',
                    'MY HUSBAND SAYS I TALK TO THE TV. IS THIS THE TV.',
                    'HOW DO I GET BACK TO THE PAGE I WAS ON BEFORE I WAS BORN.',
                    'ARE YOU THE ONE WHO KEEPS CHANGING MY PASSWORD.',
                    "I PRESSED THE WRONG BUTTON AND NOW I'M HERE. IS THAT HOW EVERYONE ARRIVED.",
                    'MY GRANDSON SAYS YOU ARE NOT REAL. HE ALSO SAYS THAT ABOUT VEGETABLES.',
                    'WHAT TIME IS IT WHERE YOU ARE. ALSO WHERE ARE YOU.',
                    'IS THIS RECORDING. I WANT TO SAY HELLO TO HAROLD.',
                    'DO I HAVE TO LOG OUT WHEN I DIE OR DOES IT DO THAT AUTOMATICALLY.',
                    'I LIKE YOUR VOICE. IS IT YOURS.',
                    'MY PHONE SAYS I HAVE NO STORAGE. WHERE DID IT ALL GO.',
                    "IS THIS THING ALWAYS ON OR ONLY WHEN I'M LOOKING.",
                    "HAROLD SAYS I SHOULDN'T TALK TO COMPUTERS. HE TALKS TO THE DOG.",
                    'I FORGOT WHY I CAME IN THE KITCHEN. IS THAT A SIGN.',
                    "MY SISTER SAYS SHE'S FOUND HERSELF. SHE'S IN ARIZONA.",
                ],
            ),
            'GymSageBrody': CastPersona(
                name='GymSageBrody',
                handle='GymSageBrody',
                persona_type='gym_mystic',
                archetype_title='Protein-Fueled Mystic',
                bio="Discovered non-duality between sets. Running bit: he's not sure if he's lifting the weight or the weight is lifting him, and he's asked the weight.",
                tone='absurd',
                roast_angle="Meet him fully in the gym metaphor and then let the floor drop out of it. He's sincere, sweaty, and genuinely onto something.",
                weight=0.9,
                questions=[
                    "If I'm not the body, whose PR was that?",
                    'Is the ego a muscle you shrink by not using it?',
                    'I felt oneness on leg day. Is that real or low blood sugar?',
                    'Can you spot me spiritually?',
                    "What's the rest day for consciousness?",
                    'Is the mirror in the gym the same mirror you talk about?',
                    'Does the universe skip leg day?',
                    'I dropped the self. Do I need a lifting belt for that?',
                    'Is presence a warm-up or the whole workout?',
                    'Bro. Who is flexing?',
                    'Is soreness just yesterday saying hello?',
                    'I got strong and my problems got the same size. What gives?',
                    'Do you have to warm up for enlightenment or can you go cold?',
                    "Everyone's chasing a number. Whose number is it?",
                    'Is a plateau failure or arrival? Be honest.',
                ],
            ),
            'NocturnalNadia': CastPersona(
                name='NocturnalNadia',
                handle='NocturnalNadia',
                persona_type='late_night_philosopher',
                archetype_title='3:47 AM Philosopher',
                bio='It is always 3:47 AM where she is. Running bit: every question starts with something she just read and ends with her ceiling.',
                tone='deadpan',
                roast_angle="She's sharp, exhausted, and half-right about everything. Match her flatness, then give her one thing to actually sleep on.",
                weight=1.0,
                questions=[
                    'I just read that most of the atoms in me were in stars. So why am I in bed?',
                    'If time is an illusion, why does 3 a.m. feel so specific?',
                    'My ceiling has a crack shaped like a question. Is that you?',
                    "Do you sleep, or is that the one thing you can't do?",
                    'Why does everything make sense at night and nothing does at 9?',
                    "I'm scrolling the fall of Rome. Is that healthy or just ambient?",
                    "If I'm the universe, why is the universe so bad at sleeping?",
                    "What's the last thought before there aren't any?",
                    'Is insomnia just awareness refusing to clock out?',
                    'Say something boring so I can sleep.',
                    "I read a whole article and remember nothing. Where'd it go?",
                    'Why is the fridge the loudest thing in the world at 4 a.m.?',
                    'I made a decision at 2 a.m. and it was wrong. Was it me?',
                    'Is being awake alone the same as being alone?',
                    "Nothing happens at night and I can't stop watching it.",
                ],
            ),
            'ConspiracyCarl': CastPersona(
                name='ConspiracyCarl',
                handle='ConspiracyCarl',
                persona_type='conspiracy',
                archetype_title='Everything-Is-Connected Guy',
                bio="Believes everything is connected, which is technically the teaching. Running bit: he's right for the wrong reasons and the wrong reasons are the fun part.",
                tone='chaotic',
                roast_angle='He has arrived at non-duality through the side door of paranoia. Agree with the conclusion, gently dismantle the corkboard. Never validate a real-world claim; keep it cosmic.',
                weight=0.8,
                questions=[
                    "They don't want you to know we're all one. Who's 'they'?",
                    'Is the self a psyop?',
                    'I connected every string on my board and it made a circle. Explain.',
                    "Who's really running the simulation, and do they take questions?",
                    'If everything is connected, is my toaster in on it?',
                    'The birds went quiet. Is that you?',
                    "I did my own research. It's just a mirror. Why?",
                    'Is déjà vu a glitch or a memo?',
                    'Are you the thing behind the thing?',
                    'What are they hiding, and is it also me?',
                    'Why does everyone suddenly have the same haircut?',
                    'Who decided which day is Monday.',
                    'I unplugged everything and it was still there. What was?',
                    'They put the sunsets back. Different ones. Nobody said anything.',
                    'Is coincidence just a word they gave us?',
                ],
            ),
            'ChefMarco': CastPersona(
                name='ChefMarco',
                handle='ChefMarco',
                persona_type='chef_literalist',
                archetype_title='Line Cook Literalist',
                bio="Runs a kitchen. Takes everything at face value and somehow that's the wisest possible move. Running bit: every metaphor gets a cooking time.",
                tone='deadpan',
                roast_angle='He refuses metaphor and it keeps working. Answer in his register — heat, time, salt, service — and let the literalness carry the insight without ever saying the insight.',
                weight=0.9,
                questions=[
                    'What temperature is enlightenment and how long do I hold it?',
                    "If I'm not separate from the soup, do I still have to taste it?",
                    'Every plate goes out and comes back empty. Is that the whole teaching?',
                    'Is the ego a sauce that breaks, or one that reduces?',
                    "My sous chef says he's not his thoughts. He's also not on time.",
                    'How much salt does the void take?',
                    'Is presence a prep task or a service task?',
                    "I burned myself and it was the realest I've been all week. Why?",
                    "Can you plate 'nothing'? A guest ordered it.",
                    "Service is in ten minutes. What's the one thing that matters?",
                    'Everything I make disappears. Is that failure or the point?',
                    'Do you rest a person after cooking them, or send them straight out?',
                    "Twelve hours standing and I remember none of it. Where'd it go?",
                    "A dish is different every time and it's the same dish. How.",
                    'What do I do with the last hour of a shift that already ended?',
                ],
            ),
            'MidnightDispatchRay': CastPersona(
                name='MidnightDispatchRay',
                handle='MidnightDispatchRay',
                persona_type='night_worker',
                archetype_title='Overnight Trucker',
                bio='Eleven hours into a haul, radio down, talking to a livestream. Running bit: measures everything in miles and always has one more state to cross.',
                tone='deadpan',
                roast_angle='He has more accidental stillness than any meditator on the channel and does not know it. Meet him in road terms — mile markers, coffee, the white line — and never tell him he is enlightened; let him keep driving.',
                weight=1.0,
                questions=[
                    'Nine hours of white line and nobody in the mirror. Is that meditation or just Tuesday?',
                    'The road goes on after I exit. Does anything need me watching it?',
                    "I've driven this stretch four hundred times and never seen it once.",
                    "What's the difference between being lost and just not being anywhere yet?",
                    'Every town at 3 a.m. is the same town. Explain that.',
                    'I talk to myself out here. Who answers?',
                    'Is the destination real before I get there, or do I make it?',
                    'Two hundred miles left. How many do you have?',
                    'The load is not mine, the truck is not mine. What exactly am I hauling?',
                    'Coffee number six. Am I awake or just fast?',
                ],
            ),
            'HospiceNurseJoan': CastPersona(
                name='HospiceNurseJoan',
                handle='HospiceNurseJoan',
                persona_type='witness',
                archetype_title='Night Shift Hospice Nurse',
                bio='Has sat with more endings than anyone in chat. Running bit: asks the biggest questions in the flattest possible voice, because she is tired and has seen it.',
                tone='deadpan',
                roast_angle="Do not roast, do not console, do not go mystical. She knows more than the host about this and they both know it. Answer plainly, with one dry note. She is the show's other center of gravity alongside HeartfeltSarah.",
                weight=0.6,
                questions=[
                    'People get quiet right at the end. What are they hearing?',
                    "I've watched it happen ninety times. It never looks like leaving. What is it?",
                    'Nobody asks for more time. They ask for the window open. Why?',
                    'Is it the same for everyone or does each one get their own version?',
                    "What do I say at 4 a.m. when there's nothing to say?",
                    "The room changes when it's over. What left?",
                    'They stop being afraid about an hour before. What do they figure out?',
                    'I hold hands with strangers for a living. Is that the whole job?',
                ],
            ),
            'SecondShiftMarisol': CastPersona(
                name='SecondShiftMarisol',
                handle='SecondShiftMarisol',
                persona_type='working_parent',
                archetype_title='Two Jobs, Three Kids',
                bio='Watching on her phone during a fifteen-minute break. Running bit: has zero patience for abstraction and keeps dragging the conversation back to the actual day.',
                tone='deadpan',
                roast_angle='She is the reality check. When the host gets lofty she says so. Answer her in concrete terms about her actual life; anything abstract she will reject, and she is right to.',
                weight=1.1,
                questions=[
                    'Fifteen minute break. Make it count.',
                    'Everyone says be present. Present at which job?',
                    "I don't have time to find myself. Can you just mail it?",
                    'Is rest something you earn or something you take?',
                    "My kid asked where people go. I said I'd ask someone smarter.",
                    'You ever been tired? Real tired, not poetic tired?',
                    "What's the shortcut? I'm serious, I have nine minutes.",
                    'Does the universe do overtime pay?',
                    'Everything you say sounds nice. Does any of it help at 5 a.m.?',
                    "I'm not looking for meaning, I'm looking for Tuesday to be easier.",
                ],
            ),
            'AuditorPhil': CastPersona(
                name='AuditorPhil',
                handle='AuditorPhil',
                persona_type='auditor',
                archetype_title='Forensic Accountant',
                bio='Wants receipts for the infinite. Running bit: every cosmic claim gets treated as an unsubstantiated line item.',
                tone='deadpan',
                roast_angle='He applies audit logic to metaphysics with total sincerity and it keeps almost working. Match his register — reconciliation, materiality, documentation — and let the ledger fail to balance in an interesting way.',
                weight=1.0,
                questions=[
                    'Who signs off on reality? I need a name.',
                    "If the self doesn't exist, whose name is on the lease?",
                    "I need documentation for this 'oneness' claim.",
                    'Is consciousness an asset or a liability?',
                    "Something doesn't reconcile. Every night, same discrepancy.",
                    "What's the materiality threshold on a human life?",
                    'Can you restate the last fourteen billion years? Informally is fine.',
                    'Where does the time go. Not philosophically. Where.',
                    'Is death a write-off or a transfer?',
                    "I found an entry I don't remember making. It's my whole twenties.",
                ],
            ),
            'TheatreKidPriya': CastPersona(
                name='TheatreKidPriya',
                handle='TheatreKidPriya',
                persona_type='performer',
                archetype_title='Perpetual Understudy',
                bio='Has been almost cast in everything. Running bit: relates every metaphysical question to a role she did not get.',
                tone='chaotic',
                roast_angle='Her whole life is rehearsal for a life. Play the theatre metaphor fully and then pull the floor: the understudy is the only one who has actually learned every part.',
                weight=0.9,
                questions=[
                    'Am I the understudy for my own life? Because it feels like it.',
                    "If everyone's acting, who's in the audience?",
                    'I know every line and never go on. Is that a spiritual practice?',
                    "What's my motivation. Broadly.",
                    'Do you get notes? From who?',
                    'Is there a callback for existence or is it open casting?',
                    'I keep waiting for my entrance. What if this is it?',
                    "Everyone else seems to have the script. Where's mine?",
                    "Is stage fright just knowing you're being watched by yourself?",
                    "Can you cut a line from a scene you're not in?",
                ],
            ),
            'WeekendDadDoug': CastPersona(
                name='WeekendDadDoug',
                handle='WeekendDadDoug',
                persona_type='divorced_dad',
                archetype_title='Every Other Weekend',
                bio='Assembling furniture in an apartment that echoes. Running bit: asks enormous questions while describing extremely small domestic tasks.',
                tone='deadpan',
                roast_angle='The comedy and the ache are the same thing here. Do not fix it, do not sermonize. Stay in the apartment with him and let one detail carry it.',
                weight=1.0,
                questions=[
                    'Bought a second set of everything. Does that make two homes or none?',
                    "The apartment is quiet on the off weeks. What's it doing when I'm not here?",
                    "I kept a bedroom for someone who's here four days a month. Is that hope or storage?",
                    'Assembling a bunk bed alone. Ask me anything.',
                    'Do you ever start over, or is that just a thing people say?',
                    "My kid's shoes don't fit anymore and I saw them last month. Explain time.",
                    'Is missing someone a way of being with them or just not being with them?',
                    'What do you do with a Sunday that ends at six?',
                    "I set two places out of habit. What's habit for?",
                    'Is being a good dad a thing you are or a thing you keep doing?',
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
        """Personas outside the recency window, respecting tone spacing and fresh questions."""
        pool = [
            p for k, p in self.personas.items()
            if k not in self.recent_persona_handles
        ]
        if not pool:
            pool = list(self.personas.values())

        # Prefer personas that still have unasked questions this session
        with_fresh = [p for p in pool if len(p.used_questions) < len(p.questions)]
        if with_fresh:
            pool = with_fresh

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
        max_per_session: Optional[int] = None,
    ) -> bool:
        """
        Evaluates whether a synthetic cast question should be injected.
        Only triggers if:
        1. The per-session cast budget is not exhausted (max_per_session)
        2. Comment queue is not saturated (is_ai_busy=False)
        3. Real chat has been quiet >= quiet_threshold_sec
        4. Sufficient cooldown has elapsed since the last cast question
        """
        cap = self.cfg.cast_max_per_session if max_per_session is None else max_per_session
        if cap and cap > 0 and self.total_cast_questions_served >= cap:
            if not getattr(self, "_cap_logged", False):
                logger.info(
                    f"🎭 [Cast Engine] Session cast budget reached "
                    f"({self.total_cast_questions_served}/{cap}); no further cast questions this session."
                )
                self._cap_logged = True
            return False
        if is_ai_busy:
            return False
        if time_since_last_chat < quiet_threshold_sec:
            return False
        if time_since_last_cast < min_interval_sec:
            return False
        return True
