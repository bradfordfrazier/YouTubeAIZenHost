"""
Candidate reference passages for the 'pure_oracle' clone.

Drop-in replacement for the RAINBOW_PASSAGE used by voice_manager._generate_speaker_recipe.
The Rainbow Passage is a phonetics text read as *description* — a narrator cadence, which
Chatterbox faithfully clones. Since the clone inherits prosody as much as timbre, a reference
that already reads like the show produces delivery that already sounds like the show.

Each passage below is ~13-17 seconds at rate=-10%, uses short declarative clauses with flat
landings, and deliberately contains no questions, no exclamations, and no rising terminals.

HOW TO USE (on GAMER):
  1. Copy this file to C:\\Services\\tts-server\\ (or paste a passage straight into voice_manager.py).
  2. In voice_manager.py, import it and set the recipe text, e.g.
         from oracle_reference_passages import PASSAGES
         text = PASSAGES["dry_observer"]
     ...or simply replace RAINBOW_PASSAGE's use in _generate_speaker_recipe.
  3. Tune the recipe in SPEAKER_RECIPES["pure_oracle"] — suggestions in RECIPE_VARIANTS below.
  4. Delete C:\\Services\\tts-server\\voices\\pure_oracle.wav
  5. Request any synthesis; the file regenerates from the new passage.
  6. Audition with:  python voice_audition.py --voices pure_oracle --blind

Generate several variants under different names (pure_oracle_a.wav, _b, _c) by temporarily
pointing the alias at each, then audition them side by side rather than one at a time.
"""

PASSAGES = {
    # Flat, observational, unhurried. The safest general-purpose choice for this persona:
    # it teaches the clone to land on a period rather than lift into the next clause.
    "dry_observer": (
        "There is nothing to explain here. A room, a chair, the sound of a refrigerator "
        "deciding to run. People look for the meaning behind all of it, and the meaning "
        "keeps sitting exactly where they left it. Nothing is hidden. Nothing was ever hidden. "
        "The whole arrangement is quite ordinary, which is the part nobody believes."
    ),

    # Same flatness with a faint amusement underneath. Good if 'dry_observer' clones too cold.
    # The short final clause teaches a clean punchline landing.
    "amused_flat": (
        "You can spend forty years looking for the thing you are standing on. Most people do. "
        "They read the map, they take the course, they buy the small brass bell. "
        "Then one afternoon they put down a cup of coffee and the search quietly stops "
        "mattering. No trumpet. No certificate. Just the cup, and the afternoon."
    ),

    # More air and space between phrases; slightly more resonant and 'oracular' without
    # becoming a narrator. Use if you want the transcendent moods to have somewhere to go.
    "spacious": (
        "Everything that is happening is already complete. The light on the wall. "
        "The traffic outside. The small unfinished argument you are still carrying. "
        "None of it is waiting on your approval. It simply continues, evenly, "
        "whether or not you decide to notice."
    ),

    # Deliberately mundane vocabulary and concrete nouns — matches the CRAFT rule in the bit
    # prompt ('anchor the bit in one specific physical object'). Clones a very grounded read.
    "household": (
        "A man once spent an entire morning looking for his glasses. They were on his head. "
        "He had used them to look. That is the whole situation, more or less, "
        "for everyone involved. The looking and the thing being looked for "
        "have never once been apart."
    ),
}

# Recipe variants to try in SPEAKER_RECIPES["pure_oracle"]. Regenerate the wav for each.
# Start with 'grounded'; move toward 'androgynous' if you want the original Pure Oracle target.
RECIPE_VARIANTS = {
    "current": {"voice": "en-US-ChristopherNeural", "pitch": "+2Hz", "rate": "-5%"},
    "grounded": {"voice": "en-US-ChristopherNeural", "pitch": "-3Hz", "rate": "-12%"},
    "androgynous": {"voice": "en-US-ChristopherNeural", "pitch": "+6Hz", "rate": "-10%"},
    "dry_american": {"voice": "en-US-GuyNeural", "pitch": "-2Hz", "rate": "-10%"},
    "measured_brit": {"voice": "en-GB-RyanNeural", "pitch": "-2Hz", "rate": "-12%"},
    "warm_low": {"voice": "en-US-DavisNeural", "pitch": "-4Hz", "rate": "-8%"},
}

DEFAULT_PASSAGE = "dry_observer"


if __name__ == "__main__":
    # Quick length sanity check: ~2.7 words/sec at rate=-10%
    for name, text in PASSAGES.items():
        words = len(text.split())
        print(f"{name:<14} {words:>3} words  ~{words / 2.5:4.1f}s at -10% rate")
