"""Drop bullets that repeat what an article has already said.

Shared by generate_summary.py and check_myth.py. The prompts ask the model not
to repeat itself; this is the safety net for when it does anyway.
"""

from __future__ import annotations

import re

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "for", "to", "is", "are", "be",
    "that", "this", "it", "with", "on", "as", "can", "may", "their", "your",
    "not", "more", "by", "at", "from", "was", "were", "has", "have",
}


def _content_words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower())) - STOPWORDS


def drop_repeats(bullets: list[str], said: list[str], threshold: float = 0.6) -> list[str]:
    """Keep bullets that add something. A bullet is a repeat when most of its
    content words already appear in one earlier piece of text. Kept bullets
    are appended to `said`, so later sections are checked against them too."""
    kept = []
    for bullet in bullets:
        words = _content_words(bullet)
        if words and any(
            len(words & _content_words(prior)) / len(words) >= threshold for prior in said
        ):
            continue
        kept.append(bullet)
        said.append(bullet)
    return kept
