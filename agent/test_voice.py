"""Both generators carry the Curioler voice, from the one copy in voice.py.

Before 2026-11-25 neither did: articles came out with statistics-heavy
caveats and a grand, hard-to-follow Curioler thought, because the voice rules
lived only in the platform repo, where a generator never reads them.
"""

import check_myth
import generate_summary
from voice import CURIOLER_THOUGHT_RULES, VOICE_PROMPT


def test_summary_prompt_carries_the_voice_and_the_thought_rules():
    assert VOICE_PROMPT in generate_summary.EXTRACTION_PROMPT
    assert CURIOLER_THOUGHT_RULES in generate_summary.EXTRACTION_PROMPT


def test_myth_check_prompt_carries_the_voice():
    assert VOICE_PROMPT in check_myth.EXTRACTION_PROMPT


def test_no_placeholder_is_left_unfilled():
    for prompt in (generate_summary.EXTRACTION_PROMPT, check_myth.EXTRACTION_PROMPT):
        for placeholder in ("{SOURCE_TYPE_RULE}", "{VOICE_RULES}", "{CURIOLER_THOUGHT_RULES}"):
            assert placeholder not in prompt


def test_the_old_cosmic_thought_rule_is_gone():
    # The founder preferred a simple thought to leave the reader with.
    assert "cosmic" not in generate_summary.EXTRACTION_PROMPT
