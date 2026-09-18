"""
Bit Gate — the editor between the writer and the cache.

Why this exists: the bit prompt asks the model to draft several candidates privately and output
only the survivor. That makes the writer its own editor, inside one thinking pass, and a writer
likes its own joke. The result is a show whose best bits are good and whose median bit is a
near-miss — and the median is what gets clipped.

Bits are generated OFFLINE into the reflection cache, so a second look costs credits but no
stream latency. The gate spends that slack in two stages:

  1. LINT   — mechanical checks for the rules PROJECT_MASTER.md already declares (no "we", no
              handles or callbacks, no question ending, no abstract noun in the landing, no
              near-duplicate of a recent line, no parroting the theme card). These are rules a
              regex can enforce, so a prompt should not be the only thing enforcing them.
  2. EDITOR — a separate, cold call. It never sees the theme or the form. It reads the surviving
              candidates the way a Shorts viewer hears them: once, with no context. It may pick
              none, and then nothing is cached — a missed slot is cheaper than a dud on a loop.

Everything here is pure (no I/O, no model calls) so it can be unit-tested without Gemini.
ai_brain.AIBrain._generate_vetted_bit() owns the calls.

Every threshold and word list is a config key. The lists are the operator's call (see §6 of the
master doc: over-banning strips out the jokes). The defaults are deliberately short.
"""

from __future__ import annotations

import difflib
import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Reasons are stable codes (they go to the log and the jsonl) with a note the writer sees on retry.
RETRY_NOTES: Dict[str, str] = {
    "too_long": "A previous draft ran long. Cut until only the setup and the landing remain.",
    "too_short": "A previous draft was a fragment. It needs a setup before it can turn.",
    "one_liner_multi_sentence": "A previous one-liner used two sentences. One sentence, one breath.",
    "we_voice": "A previous draft said 'we'/'us'/'our'. Say 'I'. There is no group to be a member of.",
    "handle_or_callback": "A previous draft referred to a viewer, the chat, or something said earlier. The bit must work cold.",
    "ends_on_question": "A previous draft ended on a question. End on a flat statement.",
    "banned_phrase": "A previous draft used a banned phrase. Plain words only.",
    "abstract_landing": "A previous draft landed on an abstract noun. The last words must be a thing you could drop on your foot.",
    "theme_parrot": "A previous draft just reworded the DIRECTION line. That line is a compass, not the joke. Find your own way in.",
    "near_duplicate": "A previous draft was too close to a line that already aired. Different angle, different image.",
    "repeated_opener": "A previous draft opened with the same words as a recent bit. Start somewhere else.",
    "editor_passed": "An editor read the previous candidates cold and none of them got a laugh: they were wise, not funny. Be more specific and more surprising; put the funniest word last.",
}

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z'’-]*")
_SENT_END_RE = re.compile(r"[.!?]+[\"'”’)]*\s+(?=[\"'“‘(]?[A-Z0-9])")
_QUOTED_RE = re.compile(r"“[^”]*”|\"[^\"]*\"|(?<![A-Za-z])'[^']*'(?![A-Za-z])")
_WE_RE = re.compile(r"\b(we|us|our|ours|ourselves|we're|we’re|we've|we’ve|we'll|we’ll|we'd|we’d)\b", re.IGNORECASE)
_LETS_RE = re.compile(r"\blet(?:'|’)?s\b|\blet us\b", re.IGNORECASE)
_CALLBACK_RE = re.compile(
    r"@\w|\b(as i said|like i said|as i mentioned|as mentioned|speaking of which|"
    r"back to (?:the|that|what)|earlier (?:i|bit|tonight|today i said)|last bit|previous bit|"
    r"someone in (?:the )?chat|in the chat just|one of you (?:just )?(?:asked|said))\b",
    re.IGNORECASE,
)

_STOP = frozenset("""
a an the and or but if then than that this these those there here what which who whom whose
you your yours i me my mine it its they them their he she his her him we us our
is are was were be been being am do does did doing have has had having will would can could
should shall may might must not no nor only just even also very really so too much many
of in on at to for with from by about into over under after before while when where how why
as like still yet own same other another more most less least up out off down all any some
one two three every each because until once again ever never always
""".split())


def _words(text: str) -> List[str]:
    return [w.lower().strip("'’-") for w in _WORD_RE.findall(text or "")]


def _stem(w: str) -> str:
    """Crude on purpose: enough to match 'shingles'/'shingle', 'sanding'/'sand'."""
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def content_words(text: str) -> List[str]:
    return [_stem(w) for w in _words(text) if len(w) > 2 and w not in _STOP]


def split_theme(theme: str) -> Tuple[str, str]:
    """'ANCHOR — angle' -> (anchor, angle). A card with no dash is all anchor."""
    for sep in (" — ", " -- ", " – "):
        if sep in (theme or ""):
            a, b = theme.split(sep, 1)
            return a.strip(), b.strip()
    return (theme or "").strip(), ""


def count_sentences(text: str) -> int:
    t = (text or "").strip()
    return 0 if not t else len(_SENT_END_RE.split(t))


def similarity(a: str, b: str) -> float:
    """0..1. The larger of character-level ratio and content-word overlap (Jaccard)."""
    na, nb = " ".join(_words(a)), " ".join(_words(b))
    if not na or not nb:
        return 0.0
    ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    ca, cb = set(content_words(a)), set(content_words(b))
    jac = len(ca & cb) / len(ca | cb) if (ca and cb) else 0.0
    return max(ratio, jac)


def opener(text: str, n: int = 3) -> str:
    return " ".join(_words(text)[:n])


# ---------------------------------------------------------------------------------------------
# Stage 0: parse what the writer sent back
# ---------------------------------------------------------------------------------------------
_NUMBERED_RE = re.compile(r"^\s*(?:\*{0,2})(\d{1,2})\s*[.):\-]\s*(?:\*{0,2})\s*(.*)$")


def parse_candidates(raw: str, expected: int = 0) -> List[str]:
    """
    Splits the writer's reply into raw candidates (markers intact). Tolerant: accepts '1.', '1)',
    '**1.**', wrapped continuation lines, and surrounding quotes. If nothing is numbered, the whole
    reply is treated as a single candidate so a model that ignores the format still yields a bit.
    """
    out: List[str] = []
    cur: Optional[List[str]] = None
    for line in (raw or "").splitlines():
        if not line.strip():
            continue
        m = _NUMBERED_RE.match(line)
        if m:
            if cur:
                out.append(" ".join(cur))
            cur = [m.group(2).strip()]
        elif cur is not None:
            cur.append(line.strip())
    if cur:
        out.append(" ".join(cur))

    if not out and (raw or "").strip():
        out = [" ".join(l.strip() for l in raw.splitlines() if l.strip())]

    cleaned = []
    for c in out:
        c = c.strip().strip("*").strip()
        # Strip one pair of wrapping quotes, but leave quotes that belong to dialogue.
        if len(c) > 2 and c[0] in "\"“" and c[-1] in "\"”" and c.count('"') + c.count("“") <= 2:
            c = c[1:-1].strip()
        if c and c not in cleaned:
            cleaned.append(c)
    return cleaned[:expected] if expected and len(cleaned) > expected else cleaned


# ---------------------------------------------------------------------------------------------
# Stage 1: lint
# ---------------------------------------------------------------------------------------------
def lint_bit(
    spoken: str,
    *,
    form: str,
    theme: str,
    recent: Sequence[str],
    favorites: Sequence[str],
    cfg: Any,
) -> List[str]:
    """
    Returns the reasons `spoken` must not air (empty list = clean). `spoken` is marker-free text,
    exactly what the TTS would say. `recent` is newest-last.
    """
    reasons: List[str] = []
    text = (spoken or "").strip()
    words = text.split()
    n = len(words)

    # --- length -------------------------------------------------------------------------------
    if form == "one_liner":
        if n > int(cfg.one_liner_words_max):
            reasons.append("too_long")
        if n < 6:
            reasons.append("too_short")
        if count_sentences(text) > 1:
            reasons.append("one_liner_multi_sentence")
    else:
        if n > int(int(cfg.bit_words_max) * 1.2):
            reasons.append("too_long")
        if n < max(6, int(int(cfg.bit_words_min) * 0.6)):
            reasons.append("too_short")

    # --- voice and cold-open safety (§2.5, §2.6) ------------------------------------------------
    # Dialogue inside a story may legitimately say "we"; the narrator may not.
    narration = _QUOTED_RE.sub(" ", text)
    if _WE_RE.search(narration) or _LETS_RE.search(narration):
        reasons.append("we_voice")
    if _CALLBACK_RE.search(text):
        reasons.append("handle_or_callback")
    if text.rstrip("\"'”’) ").endswith("?"):
        reasons.append("ends_on_question")

    # --- operator-owned lists -------------------------------------------------------------------
    low = " " + " ".join(_words(text)) + " "
    for phrase in cfg.bit_gate_banned_phrases or []:
        p = " ".join(_words(phrase))
        if p and f" {p} " in low:
            reasons.append("banned_phrase")
            break
    if re.match(r"\s*ah\b\s*[,.!—-]", text, re.IGNORECASE):
        reasons.append("banned_phrase")

    tail_n = int(cfg.bit_gate_abstract_tail_words)
    if tail_n > 0:
        tail = set(_words(" ".join(words[-tail_n:])))
        abstract = {a.lower() for a in (cfg.bit_gate_abstract_nouns or [])}
        if tail & abstract:
            reasons.append("abstract_landing")

    # --- originality ----------------------------------------------------------------------------
    _, angle = split_theme(theme)
    angle_cw = set(content_words(angle))
    if len(angle_cw) >= 3:   # the shortest angles are the aphorisms most tempting to reword
        overlap = len(angle_cw & set(content_words(text))) / len(angle_cw)
        if overlap >= float(cfg.bit_gate_theme_overlap_max):
            reasons.append("theme_parrot")

    dup_at = float(cfg.bit_gate_duplicate_similarity)
    if any(similarity(text, r) >= dup_at for r in list(recent) + list(favorites) if r):
        reasons.append("near_duplicate")

    win = int(cfg.bit_gate_opener_window)
    if win > 0:
        mine = opener(text)
        if mine and len(mine.split()) == 3 and any(opener(r) == mine for r in list(recent)[-win:] if r):
            reasons.append("repeated_opener")

    # de-dupe, keep order
    seen, uniq = set(), []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    return uniq


def retry_note(reasons: Sequence[str]) -> str:
    """The most common failures of the last round, phrased as instructions for the next writer call."""
    counts: Dict[str, int] = {}
    for r in reasons:
        counts[r] = counts.get(r, 0) + 1
    top = sorted(counts, key=lambda k: -counts[k])[:2]
    return " ".join(RETRY_NOTES[r] for r in top if r in RETRY_NOTES)


# ---------------------------------------------------------------------------------------------
# Stage 2: the cold-read editor
# ---------------------------------------------------------------------------------------------
EDITOR_SYSTEM = (
    "You are the script editor of a comedy show. You did not write these lines and you have no "
    "stake in any of them. You are hard to make laugh and you are not polite about near-misses."
)


def build_editor_prompt(candidates: Sequence[str], recent: Sequence[str], min_laugh: int) -> str:
    lines = [
        "A calm synthetic voice will speak ONE of the lines below over looping music. It will be "
        "clipped and watched by a stranger who has seen nothing else: no theme, no chat, no "
        "earlier joke. The speaker is 'I AM' — the one consciousness behind everything, doing dry "
        "stand-up about having turned itself into all of this. The show's standard: funny enough "
        "to clip AND something true left behind, never stated.",
        "",
        "Read each candidate ONCE, cold, as that stranger hears it.",
        "",
        "Score each:",
        "  laugh 1-5 — 1 no reaction · 2 'I see what it was going for' · 3 an actual exhale "
        "through the nose · 4 a laugh · 5 you would send it to someone. MOST CANDIDATES ARE A 2. "
        "A wise line is not a funny line; a nod is not a laugh.",
        "  true  1-5 — is there something a non-dualist would recognise underneath, WITHOUT the "
        "line saying it?",
        "",
        "Mark a candidate dead (laugh 1) if any of these is so:",
        "  - you could have predicted the last five words from the first ten",
        "  - it is a saying wearing a joke costume, or it explains itself",
        "  - the object is interchangeable: swap it for another and the line still works",
        "  - it resembles a joke you already know, a fridge magnet, or a social-media format",
        "  - it is aimed at the listener ('you people…') rather than at the speaker",
        "  - the funniest word is not at or near the end",
        "  - it would sound like a mistake read aloud (tongue-twisting, or two ideas at once)",
    ]
    if recent:
        lines += ["", "Already aired recently — a candidate that is the same joke again is dead:"]
        lines += [f"  - {r}" for r in list(recent)[-6:]]
    lines += ["", "CANDIDATES:"]
    lines += [f"  {i}. {c}" for i, c in enumerate(candidates, 1)]
    lines += [
        "",
        f"Pick the candidate with the highest laugh score, provided laugh >= {int(min_laugh)} and "
        "true >= 2. Break ties toward the shorter line. If none qualifies, pick 0 — airing nothing "
        "is better than airing a dud, and the writer will try again.",
        "",
        "Reply with ONLY this JSON, nothing before or after it:",
        '{"scores": [{"n": 1, "laugh": 2, "true": 3}], "pick": 0, "why": "one short sentence"}',
    ]
    return "\n".join(lines)


def parse_editor_reply(text: str, n_candidates: int) -> Tuple[Optional[int], str, List[Dict[str, Any]]]:
    """
    -> (pick, why, scores). pick is 1-based, 0 for 'none', or None when the reply is unusable
    (the caller then fails open to the first lint survivor rather than wasting the round).
    """
    raw = re.sub(r"```(?:json)?|```", "", text or "").strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None, "unparseable", []
    try:
        data = json.loads(m.group(0))
    except Exception:
        pm = re.search(r'"pick"\s*:\s*(\d+)', raw)
        if not pm:
            return None, "unparseable", []
        data = {"pick": int(pm.group(1))}
    try:
        pick = int(data.get("pick"))
    except Exception:
        return None, "unparseable", []
    if pick < 0 or pick > n_candidates:
        return None, "pick out of range", []
    scores = data.get("scores") if isinstance(data.get("scores"), list) else []
    return pick, str(data.get("why", ""))[:200], scores
