"""Compose the plain-language Easy explainer block from a study record.

Deterministic by design: the same record always produces the same text, so the
output is reviewable in a diff and cannot assert anything the abstract does not
carry. See specs/2026-08-31-easy-explainer-design.md.
"""

from __future__ import annotations

import re

DISCLAIMER = (
    "This is a plain-language summary of one paper's abstract, not medical advice. "
    "Talk to your child's clinician before changing anything."
)

SMALL_SAMPLE = 30
SHORT_STUDY_WEEKS = 12

TIER_1_DESIGNS = {"Meta-Analysis", "Systematic Review"}
TIER_3_DESIGNS = {"Observational Study", "Case Reports"}

DESIGN_SENTENCES = {
    "trial": (
        "This was a randomised controlled trial — people were assigned to treatments by "
        "chance, which is the most reliable way to tell whether a treatment itself caused "
        "a change."
    ),
    "review": (
        "This pooled the results of several earlier studies, which usually gives a steadier "
        "picture than any single study can."
    ),
    "observational": (
        "This was an observational study — researchers watched what happened rather than "
        "assigning treatments. It can show that two things happen together, but it cannot "
        "show that one caused the other."
    ),
    "case": (
        "This describes one case or a small handful of cases. It can raise a question worth "
        "studying, but it cannot tell you what happens for most people."
    ),
    "unknown": (
        "This record does not state what kind of study this was, so how much weight it "
        "carries cannot be judged from this page."
    ),
}

UNIT_WEEKS = {"day": 1 / 7, "week": 1.0, "month": 4.345, "year": 52.18}


def design_kind(study_type: str | None) -> str:
    if not study_type:
        return "unknown"
    if study_type in TIER_1_DESIGNS:
        return "review"
    if study_type == "Observational Study":
        return "observational"
    if study_type == "Case Reports":
        return "case"
    return "trial"


def base_tier(study_type: str | None) -> int:
    if not study_type:
        return 4
    if study_type in TIER_1_DESIGNS:
        return 1
    if study_type in TIER_3_DESIGNS:
        return 3
    return 2


def trust_tier(study: dict) -> tuple[int, str]:
    """Return (tier, label). Small samples demote one step, floored at tier 3."""
    study_type = study.get("study_type")
    tier = base_tier(study_type)
    label = study_type or "Study design not stated"
    participants = study.get("participants")
    if isinstance(participants, int) and participants < SMALL_SAMPLE and tier < 3:
        tier += 1
        label = f"{label} (small sample)"
    return tier, label


def duration_weeks(text: str | None) -> float | None:
    """Normalise a free-text duration to weeks. None when it cannot be parsed."""
    if not text:
        return None
    match = re.search(r"(?i)(\d+(?:\.\d+)?)\s*-?\s*(day|week|month|year)s?", text)
    if not match:
        return None
    return float(match.group(1)) * UNIT_WEEKS[match.group(2).lower()]


# Below SMALL_SAMPLE, what a small N *means* depends on the design, so the sentence
# branches by design_kind there. Random assignment is what a trial's small-N warning
# is really about (it keeps the two groups comparable even when N is small — the risk
# is an imprecise estimate, not a biased one), while an observational study has no
# randomisation to fall back on, so a small group makes it easier for something other
# than the studied factor to explain what was seen. Above SMALL_SAMPLE the two risks
# converge enough that a single generic sentence covers both without repeating the
# design sentence above it.
SMALL_SAMPLE_BY_DESIGN = {
    "trial": (
        "It involved only {n} people. Random assignment still means the groups started out "
        "comparable, but with so few people the result can shift a lot by chance — a larger "
        "trial could easily find something different. Treat this as an early signal rather "
        "than an answer."
    ),
    "observational": (
        "It involved only {n} people. Without random assignment, a group this small makes it "
        "especially easy for something other than what was studied to explain the difference "
        "researchers saw. Treat this as a very early signal rather than an answer."
    ),
}


def size_sentence(participants: object, design_kind_value: str = "unknown") -> str:
    if not isinstance(participants, int):
        return (
            "The number of people who took part is not stated in this record, so the result "
            "cannot be judged on size."
        )
    if participants == 1:
        return (
            "It describes just 1 person. A single case can raise a question worth studying, "
            "but it cannot tell you what happens for most people."
        )
    if participants < SMALL_SAMPLE:
        template = SMALL_SAMPLE_BY_DESIGN.get(
            design_kind_value,
            "It involved only {n} people. With a group this small, results can shift a lot by "
            "chance, so treat this as an early signal rather than an answer.",
        )
        return template.format(n=f"{participants:,}")
    if participants < 100:
        return (
            f"It involved {participants:,} people — a modest group, enough to be interesting "
            "but not enough to settle a question on its own."
        )
    if participants < 500:
        return f"It involved {participants:,} people, a reasonably sized group for this kind of research."
    return (
        f"It involved {participants:,} people, which is a large group for autism research and "
        "makes the findings steadier."
    )


def duration_sentence(duration: str | None) -> str | None:
    if not duration:
        return None
    sentence = f"The study ran for {duration}."
    weeks = duration_weeks(duration)
    if weeks is not None and weeks <= SHORT_STUDY_WEEKS:
        sentence += " That is a short window, so it says nothing about whether the effects last."
    return sentence


def conclusion_sentence(conclusion: str | None) -> str | None:
    if not conclusion:
        return (
            "The abstract does not include a conclusions section, so this page does not state "
            "what the researchers concluded."
        )
    sentences = re.split(r"(?<=[.!?])\s+", conclusion.strip())
    trimmed = " ".join(sentences[:2]).strip()
    return f'The researchers concluded: "{trimmed}"'


def not_stated(study: dict) -> list[str]:
    """Only fields with no sentence of their own, so the block never repeats itself."""
    missing = []
    if not study.get("age_range"):
        missing.append("the ages of the people who took part")
    if not study.get("duration"):
        missing.append("how long the study ran")
    return missing


def build_explainer(study: dict) -> dict:
    kind = design_kind(study.get("study_type"))
    return {
        "design": DESIGN_SENTENCES[kind],
        "size": size_sentence(study.get("participants"), kind),
        "duration": duration_sentence(study.get("duration")),
        "conclusion": conclusion_sentence(study.get("conclusion")),
        "not_stated": not_stated(study),
        "disclaimer": DISCLAIMER,
    }
