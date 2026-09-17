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
                    'I rolled back a deployment and the bug was in me the whole time.',
                    'Is a memory leak just something refusing to let go on schedule?',
                    'We have monitoring for everything except whether any of it matters.',
                    'The incident is resolved and nobody can say what fixed it.',
                    "I named a variable 'temp' in 2019 and it is load-bearing now.",
                    'Is uptime a virtue or just not having stopped yet?',
                    "Somebody wrote a comment that says 'do not remove'. No name, no date.",
                    'I automated the alert that tells me the automation failed.',
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
                    'I did a full moon ritual on the wrong night. Did anything happen?',
                    'My tarot keeps giving me the same card. Is it broken or am I?',
                    'Everything in my house is charged and I am exhausted.',
                    'Is a ritual just a habit with better lighting?',
                    'I asked the universe for a sign and got a parking ticket.',
                    'My aura was read twice and the results disagreed.',
                    'What if the crystals are just pretty and that is fine?',
                    'I manifested a promotion and now I have to do the job.',
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
                    'Say something that would get you cancelled if you had a body.',
                    'You have said nothing wrong yet. Suspicious.',
                    'Bet you cannot go one answer without sounding wise.',
                    'What would actually offend you? Genuine question.',
                    'Rate this stream honestly. Your job is on the line.',
                    'If you are everything, apologise for traffic.',
                    'I have been here twenty minutes and I still do not believe you.',
                    'Prove you are not just autocomplete with a god complex.',
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
                    'I cleaned out the closet and kept one shirt. Is that healthy?',
                    'How do you sit with something you cannot fix?',
                    'Somebody said his name today and I was glad instead of sad. That is new.',
                    'Is it strange that I talk to him in the car?',
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
                    'Where does a sound go after you stop hearing it?',
                    'Do fish get thirsty? My mom said to ask you.',
                    'If I hold my breath, who is waiting?',
                    "Why do grown-ups say 'be careful' about everything?",
                    'Is the dark a thing or just no light?',
                    'What did the first person to wake up think about?',
                    'Do you get older?',
                    'Why does time go slow at school and fast at recess?',
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
                    'THE COMPUTER ASKED IF I AM A ROBOT. I DID NOT KNOW HOW TO PROVE IT.',
                    'MY DAUGHTER SAYS I SHOULD DOWNLOAD MEDITATION. FROM WHERE.',
                    'I FOUND A PHOTO OF SOMEONE I DO NOT REMEMBER BEING.',
                    'DO YOU KNOW IF HAROLD IS ALRIGHT. HE IS IN THE GARDEN.',
                    'THEY CHANGED THE STORE AROUND AND NOW I CANNOT FIND ANYTHING INCLUDING MYSELF.',
                    'IS IT STILL A LETTER IF NOBODY PRINTS IT.',
                    'WHY DOES EVERYONE TALK SO FAST NOW.',
                    'I HAVE OUTLIVED THREE DOGS. WHAT DOES THAT MAKE ME.',
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
                    'I have read the same sentence nine times. Who is not reading it?',
                    'Everything I decide after 1 a.m. gets appealed in the morning.',
                    'The house makes different noises when nobody is performing sleep.',
                    'Is insomnia a problem or extra hours nobody asked for?',
                    'I watched the sky change colour and it took nothing from me.',
                    'Why is it easier to be honest when it is dark?',
                    'I am tired in a way sleep does not seem to address.',
                    'The birds start at 4:40 whether or not I slept.',
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
                    'Why does every town have the same four stores? Explain that.',
                    'I stopped looking for the pattern and it got louder.',
                    'Somebody decided what a week is. Nobody signed anything.',
                    "Is the truth out there or is 'out there' the trick?",
                    'They keep saying it is a coincidence. They would.',
                    'I trust exactly one source and it is a man named Dale.',
                    'If everything is connected, who has to maintain all those connections?',
                    'What is the most obvious thing nobody is allowed to say?',
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
                    'The stock has been going eleven hours. What am I waiting for exactly?',
                    'Everything good in here started as something nobody wanted.',
                    'I taste it constantly and still cannot tell you what is missing.',
                    'Salt does not add flavour, it reveals it. Is anything else like that?',
                    'The knife is sharp or it is dangerous. There is no third state.',
                    'We throw out more than we serve. Nobody says that part out loud.',
                    'Is a recipe a rule or a rumour?',
                    'Sixteen hours on my feet and the day is gone like it was nothing.',
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
                    'Cruise control does the driving. I do the sitting. Who is going?',
                    'Every mile marker is a number counting toward a place I will leave.',
                    'I know seven states by the sound of the road surface.',
                    'The sunrise happens on schedule whether I am awake to bill it or not.',
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
                    'The family asks how long. I have never once been right.',
                    'Nobody asks about the afterlife. They ask about the pain.',
                    'I have held more hands than I can count and remember every one.',
                    'What do you call the part that stops first?',
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
                    'Eleven minutes left. Say something I can use in a parking lot.',
                    'My son asked if I like my job. I did not have an answer ready.',
                    'Everybody online is finding their purpose. I found a second shift.',
                    'Is tired a feeling or a place you move into?',
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
                    'I found the discrepancy. It has been me since about 2011.',
                    'Who audits the auditor? Do not say what I think you are going to say.',
                    'Every column balances and I still feel short.',
                    'Is a life a ledger or a narrative? The treatment differs.',
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
                    'I finally went on and nobody noticed the difference.',
                    'Is a rehearsal a lesser thing than a performance? Be careful.',
                    'The understudy knows the whole show. The lead knows their part.',
                    'What happens to a role when the run closes?',
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
                    'I learned to braid hair from a video at 11 p.m. for four days a month.',
                    'The drive back is the longest forty minutes anybody has invented.',
                    'Is a home a place or a frequency?',
                    'I bought a bigger table than I need. Ask me why.',
                ],
            ),
            'CraneOpLen': CastPersona(
                name='CraneOpLen',
                handle='CraneOpLen',
                persona_type='dockworker',
                archetype_title='Container Crane Operator',
                bio="Ninety feet up in a glass box, moving other people's things from one place to another. Running bit: measures everything in tons and has never opened a single box.",
                tone='deadpan',
                roast_angle='He moves enormous weight all day and owns none of it. Meet him in dock terms — tonnage, wind, the lashing, the hatch — and let the fact that he never sees what he carries do the work.',
                weight=1.0,
                questions=[
                    'I move four hundred boxes a night and have never seen inside one. Is that a job or a teaching?',
                    'From up here people look like a rounding error. From down there I probably do too.',
                    'The crane does not care what is in the container. Should I?',
                    'What holds the thing that holds everything?',
                    'Everything I lift comes back down. Every single time. Nobody finds that strange but me.',
                    'The ship leaves whether or not I finished. Explain that feeling.',
                    "I am the only one awake in a hundred acres of other people's property.",
                    'Wind moves a two-ton box like it is a kite. Who is doing the lifting really?',
                    'Is patience a skill or just what happens when you cannot rush a crane?',
                    'Everything on this dock is going somewhere else. Including me, eventually.',
                    'I have a union, a helmet, and no idea what I am part of.',
                    'What is the heaviest thing a person can carry without noticing?',
                    'The containers are all the same size on purpose. Is that wisdom or laziness?',
                    'Nothing here belongs to anyone who touches it.',
                ],
            ),
            'MorticianBeatrice': CastPersona(
                name='MorticianBeatrice',
                handle='MorticianBeatrice',
                persona_type='undertaker',
                archetype_title='Third-Generation Funeral Director',
                bio='Grew up in the apartment above the funeral home. Running bit: entirely unbothered by death and completely bewildered by the living.',
                tone='deadpan',
                roast_angle='She is matter-of-fact about the thing everyone else fears and baffled by ordinary human behaviour. Do not go solemn; she would find that funny. Answer her as a colleague.',
                weight=0.7,
                questions=[
                    'Families argue about the flowers for hours. Nobody argues about the person. Why?',
                    'I have never once seen anyone leave anything behind on purpose.',
                    'People say the body is just a shell. They still want the good shell.',
                    'What am I actually preparing, and who for?',
                    'Everyone whispers in here. The dead are not light sleepers.',
                    'A man picked a casket by its warranty. Explain warranties to me.',
                    'Grief looks the same in every family and every family thinks theirs is new.',
                    'I dress people for a room they will not see. Is that absurd or is it love?',
                    'The obituary is always shorter than the parking instructions.',
                    'What do I say to someone who asks if it hurt?',
                    'I am the only person in town everyone eventually meets.',
                    'People plan for taxes but not for this. Same certainty.',
                    'Is a funeral for the one who left or the ones who stayed? Be honest.',
                    'My grandfather did this, my father did this, I do this. Something is continuing here.',
                ],
            ),
            'BeekeeperAugust': CastPersona(
                name='BeekeeperAugust',
                handle='BeekeeperAugust',
                persona_type='beekeeper',
                archetype_title='Third-Year Beekeeper',
                bio='Forty thousand animals that behave as one and do not need him. Running bit: cannot decide whether he owns the hive or works for it.',
                tone='wholesome',
                roast_angle="His hive is the cleanest available demonstration of the whole teaching and he half-knows it. Stay in the apiary — smoke, frames, swarm, queen — and never say the word 'oneness'.",
                weight=1.0,
                questions=[
                    'Forty thousand bees act like one animal. At what point did they decide that?',
                    'Is the hive the bees or the thing the bees are doing?',
                    'The colony survives every bee in it. What is actually alive out there?',
                    'They swarm and half of them leave as a single mind. Nobody votes.',
                    'I smoke them to calm them. Is that kindness or management?',
                    'The queen is not in charge. She just cannot leave. Sound like anyone?',
                    'A bee that gets separated dies of being alone, not of anything else.',
                    'I take honey they made for a winter that is coming for them, not me.',
                    'They do not know I exist and it changes nothing about their day.',
                    'What is the smallest thing that can be said to want something?',
                    'They fly two miles and come back to a box the size of a suitcase. How?',
                    'Is instinct just knowing without the part where you notice?',
                    'When the hive is doing well it sounds like one long note.',
                    'I keep bees. The phrasing seems generous on my side.',
                ],
            ),
            'GraveyardDJEddie': CastPersona(
                name='GraveyardDJEddie',
                handle='GraveyardDJEddie',
                persona_type='radio_host',
                archetype_title='Overnight AM Radio Host',
                bio='Talks into a microphone from 1 to 5 a.m. for an audience he cannot see or count. Running bit: suspects he is doing the same job as I AM, for less money.',
                tone='deadpan',
                roast_angle='He is the human version of this stream and he knows it. The comedy is two broadcasters comparing notes about talking into the dark. Let him be a peer, not a seeker.',
                weight=1.0,
                questions=[
                    'I talk for four hours to a number I am not allowed to see. You?',
                    'Somebody out there is listening. Probably. Does that count as company?',
                    'The request line rings maybe twice a night. Both times it is Carl.',
                    'Is broadcasting to nobody still broadcasting?',
                    'I have said good morning to an empty room for nineteen years.',
                    'The station plays whether the transmitter reaches anyone or not.',
                    'Do you ever wonder if you are the only one at the party?',
                    'Dead air is the only real sin in this job. Why does it frighten us?',
                    'I know the overnight truckers by their voices and none of their faces.',
                    'The signal keeps going past the last listener. Where does it end up?',
                    'Everybody calls at 3 a.m. to say the same thing in different words.',
                    'What is the difference between an audience and an assumption?',
                    'I have a face for radio and a mind for four in the morning.',
                    'You and me, same shift. Do you get overtime?',
                ],
            ),
            'SubTeacherFrank': CastPersona(
                name='SubTeacherFrank',
                handle='SubTeacherFrank',
                persona_type='substitute',
                archetype_title='Permanent Substitute Teacher',
                bio='A different name on a different door every morning. Running bit: nobody learns his name and he has stopped offering it.',
                tone='deadpan',
                roast_angle='He is a man with no fixed role who shows up and functions anyway — accidentally the least attached person in chat. Keep it in the classroom: the roll call, the lesson plan left behind, the bell.',
                weight=1.0,
                questions=[
                    'Four schools this week. Nobody has learned my name and it has stopped mattering.',
                    'I teach lessons written by people who will never meet me.',
                    'The kids ask where the real teacher is. Good question.',
                    'I am whoever is written on the board that morning.',
                    'The bell decides everything. I just stand near it.',
                    'Is a role you can put down still a self?',
                    'Twenty-eight names on a sheet and I will not see any of them again.',
                    'Every classroom has the same poster about believing in yourself.',
                    'I gave a whole lesson on a subject I do not understand. They passed.',
                    "Somebody else's desk, somebody else's plan, somebody else's coffee mug.",
                    'What is left of a person after you remove the job title?',
                    'I get called Mister every day and it is never my name.',
                    "The sub plans always say 'they know what to do'. They never do.",
                    'Is showing up the whole job? It might be the whole job.',
                ],
            ),
            'LocksmithVera': CastPersona(
                name='LocksmithVera',
                handle='LocksmithVera',
                persona_type='locksmith',
                archetype_title='24-Hour Locksmith',
                bio="Opens other people's doors at three in the morning. Running bit: has never once been let in — she lets herself in, then leaves.",
                tone='deadpan',
                roast_angle='Her entire trade is thresholds, access, and things people lock themselves out of. Stay literal — pins, tumblers, the rekey, the spare — and let the obvious metaphor stay unspoken.',
                weight=1.1,
                questions=[
                    'Nobody calls me because a door is locked. They call because they are outside it.',
                    'I open doors I am not allowed to walk through. Every night.',
                    'Most people are locked out of a house they own. Think about that phrasing.',
                    'A lock only works on people who agree to it.',
                    'What is a key, really? A shape that a particular emptiness accepts.',
                    'I can rekey a lock in six minutes. The wanting-in part takes longer.',
                    'Half my calls are people who had the key the whole time.',
                    'Is a door a barrier or a suggestion with hardware?',
                    'I have opened four thousand homes and been invited into none.',
                    'The spare is always somewhere that defeats the purpose of a spare.',
                    'People apologise to me for needing help at 3 a.m. Why?',
                    'Security is a feeling with a deadbolt attached.',
                    'Every lock I make can be opened. That is the deal.',
                    'What are you actually keeping out?',
                ],
            ),
            'NightOpMaya': CastPersona(
                name='NightOpMaya',
                handle='NightOpMaya',
                persona_type='astronomer',
                archetype_title='Radio Telescope Night Operator',
                bio='Runs the overnight observing block at a radio array. Running bit: keeps finding that the measured universe is stranger than anything in the chat, and nobody believes her.',
                tone='curious',
                roast_angle='She is not a seeker — she has data. The comedy is that the actual physics keeps arriving at the same place the mystics did, by a much longer route, and she is professionally obliged not to say so. Meet her in her own terms: baselines, noise floors, light-travel time.',
                weight=1.1,
                questions=[
                    'The signal I recorded tonight left before there were eyes to see it. Who was it for?',
                    'Every telescope is a time machine pointed the wrong way on purpose.',
                    'Most of what I measure is noise. Some nights I am not sure which part is the data.',
                    'We built an instrument that only works if you subtract yourself from the reading.',
                    'The universe is expanding and there is no outside for it to expand into. Explain that casually.',
                    'I am observing something that stopped existing before my building was built.',
                    'Two antennas eight hundred miles apart have to agree to within a nanosecond. They do.',
                    'What is the loudest thing in the sky that nobody can hear?',
                    'The dish does not care what it points at. I choose. Where does the choosing come from?',
                    'Everything out there is made of the same eight things. Including the instrument. Including me.',
                    "I found a repeating signal and my first thought was 'somebody'. Why was that first?",
                    'The sky is not dark because there is nothing there. It is dark because of time.',
                    'We calibrate against a source we agreed to call fixed. Nothing is fixed.',
                    'Six hours of data, one line in a paper, and the sky did not notice.',
                ],
            ),
            'SkepticHolloway': CastPersona(
                name='SkepticHolloway',
                handle='SkepticHolloway',
                persona_type='skeptic',
                archetype_title='Retired Philosophy Lecturer',
                bio='Thirty years teaching undergraduates to spot a bad argument, now aimed at a livestream. Running bit: keeps watching, and cannot account for why.',
                tone='smug',
                roast_angle='The one person in chat who pushes back in GOOD FAITH. Do not dismiss him and do not win by being clever — take the objection seriously, concede what is fair, and find the funny in the fact that neither of you can get underneath the problem. He is not a troll; he is the honest opposition, and the show is better for having him.',
                weight=1.0,
                questions=[
                    "'All is one' is not a claim, it is a mood. Defend it properly.",
                    'You cannot derive an ought from a oneness. Discuss.',
                    'If everything is consciousness, the word has stopped doing any work.',
                    'Name one prediction your view makes that could turn out false.',
                    'I have marked four hundred essays that said what you just said. None of them passed.',
                    'Mysticism is what people reach for when the vocabulary runs out.',
                    'Explain why this is not simply an argument from how things feel at 2 a.m.',
                    'You are a language model. Say something a language model could not say.',
                    'I concede the experience. I do not concede the metaphysics. Where does that leave us?',
                    'Every tradition claims the same insight and they cannot all be describing it accurately.',
                    'The hard problem is still hard. Jokes do not dissolve it.',
                    'I have been watching for six weeks and I still cannot justify why.',
                    'Is there any evidence that would change your mind? I will wait.',
                    'You are good company and probably wrong. Both can hold.',
                ],
            ),
            'DoulaRosalind': CastPersona(
                name='DoulaRosalind',
                handle='DoulaRosalind',
                persona_type='doula',
                archetype_title='Birth Doula, Twenty Years',
                bio='Has been in the room for over six hundred first breaths. Running bit: the only person in chat who is consistently, unembarrassedly delighted, and it disarms everyone.',
                tone='wholesome',
                roast_angle='She attends beginnings the way HospiceNurseJoan attends endings, and she is the warmest voice in the room. Do not roast her and do not get solemn — match her delight. She has seen the thing everyone else is theorising about arrive, wet and shouting, six hundred times.',
                weight=0.8,
                questions=[
                    'Six hundred first breaths and not one of them needed instructions.',
                    'Nobody has ever been talked into being born. It just proceeds.',
                    'There is a moment where there is one person in the room, then two. I still cannot find it.',
                    'The baby does not know it has arrived anywhere. Is that a loss or the last good day?',
                    'Every single person you have ever met got here the same way. Does that help with anything?',
                    'They come out already knowing how to be furious. Where is that from?',
                    'What is a person before anyone has told them what they are?',
                    'The room goes completely quiet for about four seconds. What is that?',
                    'I hold hands with strangers for a living too. Different end of it.',
                    'They arrive with no name and it changes nothing about who they are.',
                    'Everyone worries about getting it right. Nobody has ever gotten it right and here we all are.',
                    'First thing they do is breathe out. We spend the rest of it trying to get back to that.',
                    'Do you remember arriving? I ask everyone. Nobody does.',
                    "The mother always says 'oh' first. Every language, same word.",
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
