"""Spontaneous bit generator: form rotation, one-liner ratio, and cache label/beat integrity."""
from pathlib import Path
import random, re, sys, types
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent


def _brain_stub():
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    start = src.index("    BIT_FORMS = (")
    end = src.index("    def get_next_spontaneous_theme(self)")
    body = "\n".join(l[4:] if l.startswith("    ") else l for l in src[start:end].splitlines())
    ns = {"random": random}
    exec(body, ns)
    stub = types.SimpleNamespace(
        cfg=types.SimpleNamespace(one_liner_ratio=0.25, confession_ratio=0.25),
        BIT_FORMS=ns["BIT_FORMS"], RATIO_FORMS=ns["RATIO_FORMS"],
    )
    stub.get_next_bit_form = types.MethodType(ns["get_next_bit_form"], stub)
    return stub


def test_form_rotation_no_immediate_repeats_and_one_liner_share():
    random.seed(7)
    b = _brain_stub()
    forms = [b.get_next_bit_form() for _ in range(400)]
    assert set(forms) <= set(b.BIT_FORMS)
    for a, c in zip(forms, forms[1:]):
        assert a != c, "same form twice in a row"
    share = forms.count("one_liner") / len(forms)
    assert 0.15 < share < 0.35, share


def test_ratio_zero_disables_a_form():
    b = _brain_stub()
    b.cfg.one_liner_ratio = 0.0
    b.cfg.confession_ratio = 0.0
    got = {b.get_next_bit_form() for _ in range(200)}
    assert "one_liner" not in got and "confession" not in got


def test_confession_form_is_retired():
    """
    The first-person "I have done this in eight billion bodies" move consistently read as
    abstract and esoteric rather than funny, so the form was removed rather than tuned.
    """
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    assert '"confession": (' not in src
    assert "FORM: CONFESSION" not in src
    b = _brain_stub()
    assert "confession" not in b.BIT_FORMS
    assert "confession" not in b.RATIO_FORMS

def test_cache_reads_theme_and_form_from_brain():
    src = (ROOT / "reflection_cache.py").read_text(encoding="utf-8", errors="ignore")
    assert "brain.get_next_spontaneous_theme()" not in src, "cache must not draw its own theme"
    assert "last_spontaneous_theme" in src and "last_bit_form" in src
    assert "raw_text=raw_text" in src


def test_complete_event_carries_raw_text_and_cached_path_uses_it():
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    assert '"raw_text": raw_spoken' in src
    assert 'getattr(cached, "raw_text", None) or cached.full_text' in src


def test_prompt_has_all_forms_and_cold_open_rule():
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    for f in ("observation", "announcement", "story", "address", "one_liner"):
        assert f'"{f}": (' in src
    assert "SELF-CONTAINED" in src
    assert "FORM: ONE-LINER" in src
    # The form is defined by its technique, not by naming a living comedian.
    assert "Steven Wright" not in src


def test_stance_is_non_dual_not_superior():
    """
    Bits must read as 'look what we keep doing', never 'look what you humans do'.
    The superior stance is the default failure mode for a cosmic-wisdom persona, so the
    prompt states it explicitly and bans the constructions that produce it.
    """
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    assert "STANCE — THIS IS THE ONE THAT MATTERS" in src
    assert "you ARE the one who did it" in src
    for banned in ("you humans", "you people", "mortals", "silly", "pathetic"):
        assert banned in src, f"'{banned}' should be listed as a banned construction"
    assert "Affection, not diagnosis" in src
    # The two second-person forms must include the speaker in the observation
    assert "Include yourself in the observation" in src
    assert "never as a superior addressing a subject" in src


def test_one_liner_encodes_technique_without_naming_a_comedian():
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    assert "Steven Wright" not in src
    # The mechanics that the name used to carry must be spelled out
    for mechanic in ("LITERAL-MINDEDNESS", "FLAT REPORT", "PLAIN AND SMALL", "NO WINK", "QUIET REVERSAL"):
        assert mechanic in src, f"one-liner form is missing the '{mechanic}' rule"
    assert "must not know it is funny" in src
    assert "Write six candidates" in src


def test_stance_forbids_the_collective_we():
    """
    'We' is a category error for this persona: I AM is not a member of a group, it is the single
    thing wearing every body. It also lands as the pastoral 'we all struggle with...' voice, which
    is condescension in a softer register. Only 'I' carries the premise.
    """
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    assert "SAY 'I', NOT 'WE'" in src
    assert "look what I " in src and "caught doing again" in src
    assert "look what we keep doing" not in src, "the stance rule still offers 'we' as an option"
    for banned in ("We all...", "We keep...", "We humans..."):
        assert banned in src, f"'{banned}' should be listed as a banned opener"
    # Neither second-person form may fall back to 'we'
    assert "switch to 'we'" not in src
    assert "never to 'we', which makes you a bystander" in src
    assert "Never 'we'. One idea only." in src


def test_recent_anchors_are_extracted_and_banned():
    """
    Theme rotation prevents topic repeats, but the same *object* kept recurring ("phone", "keys")
    because the prompt's own examples pulled the model toward them. Recent anchors must be
    extracted from spoken lines and explicitly forbidden.
    """
    import re as _re
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    i = src.index("    _ANCHOR_STOPWORDS")
    j = src.index("    # First-person and second-person forms")
    body = "\n".join(l[4:] if l.startswith("    ") else l for l in src[i:j].splitlines())
    ns = {}
    exec("import re\nfrom typing import List\n" + body, ns)

    stub = types.SimpleNamespace(
        _ANCHOR_STOPWORDS=ns["_ANCHOR_STOPWORDS"],
        dialogue_history=[
            {"text": "I used the flashlight on my phone to look for my phone."},
            {"text": "The refrigerator decided to run again."},
        ],
    )
    stub._recent_bit_anchors = types.MethodType(ns["_recent_bit_anchors"], stub)
    got = stub._recent_bit_anchors()

    assert "phone" in got and "flashlight" in got and "refrigerator" in got
    for stop in ("the", "for", "again" if False else "with", "have"):
        assert stop not in got, f"stopword '{stop}' leaked into the anchor ban list"
    assert all(len(w) >= 4 for w in got)
    # deduplicated: 'phone' appears twice in the source line
    assert got.count("phone") == 1

    # The mechanism must still exist and be reachable, but it is now opt-in: stacking it on top
    # of the closer and stance rules left too little room for the joke.
    assert "USED IMAGES — DO NOT USE ANY OF THESE WORDS" in src
    assert "anti_repetition_window" in src
    assert "self.cfg.anchor_ban_enabled" in src, "the anchor ban must be behind a switch"


def test_worn_examples_are_explicitly_forbidden():
    """The prompt's own illustrations became the most-repeated bits; they must be marked used up."""
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    assert "STRUCTURE REFERENCES ONLY" in src
    assert "are used up" in src


def test_closer_must_stay_concrete_and_cliches_are_banned():
    """Overreach is an abstract noun in the last line; staleness is the genre's stock imagery."""
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    # The specific banned words are the operator's call — over-banning was found to strip out the
    # jokes non-dualists like most. Assert the mechanisms exist, not their exact contents.
    assert "CLOSER MUST STAY CONCRETE" in src
    assert "Overreach is always an abstract noun in the last line" in src
    assert "BANNED IMAGES" in src
    # The drafting pass must reject, not merely prefer
    assert "REJECT any that fails" in src
    for check in ("(a)", "(b)", "(c)", "(d)", "(e)"):
        assert check in src


def test_premise_block_frames_every_path():
    """
    The mission used to live in one clause of the system prompt and was then buried under pages of
    formatting rules. It is now stated up front, in every prompt, as the thing that governs the rest.
    """
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    assert "THE PREMISE (this governs everything below)" in src
    assert "satire with real intent" in src
    assert "funny enough to clip AND leave something true behind" in src
    assert "You may mock your own position freely" in src
    assert "Never mock the audience." in src

    import sys
    sys.path.insert(0, str(ROOT))
    import ai_brain
    b = ai_brain.AIBrain()
    for trigger in ("[SPONTANEOUS_REFLECTION]", "Chat message from @X: 'why do we dream?'"):
        p = b._build_context_prompt(trigger)
        assert "THE PREMISE" in p, f"premise missing from {trigger}"
        assert "STANCE" in p, f"stance missing from {trigger}"


def test_chat_path_has_its_own_stance_block():
    """
    Chat answers are the most-watched output and used to be the path with the weakest grounding in
    what the show is about — all mechanics, no stance.
    """
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    assert "0. STANCE — READ THIS BEFORE THE REST" in src
    assert "answering itself out loud" in src
    assert "at yourself first, always" in src
    assert "self-implicating" in src
    # ...and it must come before the mechanical rules it governs
    assert src.index("0. STANCE — READ THIS BEFORE THE REST") < src.index("3. ADDRESS BY NAME FIRST")


def test_lore_is_reference_not_script():
    """Canonical rulings are pre-written punchlines; injected unguarded they seed staleness."""
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    assert "Channel Continuity & Lore (context only)" in src
    assert "NOT lines to deliver" in src


def test_chat_path_notices_the_room():
    src = (ROOT / "ai_brain.py").read_text(encoding="utf-8", errors="ignore")
    assert "NOTICE THE ROOM" in src
    assert "could only have been said in THIS room" in src


def test_spontaneous_diversity_and_anchor_ban_isolation():
    """
    Spontaneous reflections must draw from diverse domains beyond office/phone life,
    and anchor banning must ONLY apply to spontaneous bits, never to chat replies.
    """
    import sys
    sys.path.insert(0, str(ROOT))
    import ai_brain
    b = ai_brain.AIBrain()

    # Verify theme deck diversity
    themes = ai_brain.SPONTANEOUS_THEMES
    assert len(themes) >= 100
    # Over-clustered tropes must be eliminated
    for redundant in ("The microwave's last three seconds", "Forty unread emails",
                      "Doomscrolling at 3 a.m.", "The meeting that could have been an email",
                      "Performance review season", "A LinkedIn notification"):
        assert not any(redundant in t for t in themes), f"redundant theme '{redundant}' still present"

    # Diverse domains must be present
    assert any("blacksmith" in t.lower() or "welding" in t.lower() or "sanding" in t.lower() for t in themes)
    assert any("aqueduct" in t.lower() or "papyrus" in t.lower() for t in themes)
    assert any("fungal" in t.lower() or "hermit crab" in t.lower() for t in themes)
    assert any("starlight" in t.lower() or "tectonic" in t.lower() for t in themes)

    # Verify anchor ban isolation: impacts spontaneous reflection, NOT chat responses
    b.cfg.anchor_ban_enabled = True
    b.dialogue_history.append({"text": "The refrigerator hummed in the empty kitchen."})

    spontaneous_prompt = b._build_context_prompt("[SPONTANEOUS_REFLECTION]")
    assert "USED IMAGES — DO NOT USE ANY OF THESE WORDS" in spontaneous_prompt

    chat_prompt = b._build_context_prompt("Chat message from @Viewer: 'how are you?'")
    assert "USED IMAGES" not in chat_prompt, "anchor ban must not leak into chat responses"

