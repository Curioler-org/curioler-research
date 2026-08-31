#!/usr/bin/env python3
"""Build study JSON from already-fetched PubMed raw files (no LLM required)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from pipelines.pubmed.common import (
    RAW_ABSTRACT_DIR,
    RAW_XML_DIR,
    STUDIES_DIR,
    existing_pmids,
    normalize_study,
    study_path,
    utc_now,
)
from pipelines.pubmed.extract import metadata_from_xml
from pipelines.pubmed.index import write_indexes
from pipelines.pubmed.validate import validate_study
from scripts.generate_study_pages import generate_pages

SECTION_RE = re.compile(
    r"(?is)\b(BACKGROUND|INTRODUCTION|OBJECTIVE|OBJECTIVES|PURPOSE|AIM|AIMS|"
    r"METHODS?|MATERIALS AND METHODS|DESIGN|RESULTS?|FINDINGS|"
    r"CONCLUSIONS?|CONCLUSION|DISCUSSION|UNLABELLED)\b\s*[:.\-]\s*"
)

# `participants` is the TOTAL number of people enrolled, or None. The previous
# patterns took the first "n = X" in the abstract, which in a trial abstract is
# almost always a single arm: PMID40178785 stored 20 for a 40-child study, and
# PMID41392642 stored 6 from "n = 6, 7%" of eighty rated studies. A wrong number
# here becomes a wrong sentence in the Easy explainer, so every pattern requires a
# person noun and anything ambiguous returns None.
PERSON_NOUN = (
    r"(?:children|adults?|adolescents?|youth|participants?|patients?|individuals?|"
    r"subjects?|toddlers?|infants?|preschoolers?|cases|caregivers?|parents?|dyads?|"
    r"families|women|men|mothers?|fathers?|people)"
)

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
NUMBER_WORD_RE = "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))
# "Forty", "Eighty-seven", "One hundred and seven", "One-hundred and thirty",
# "Seventy- two" (an occasional hyphen-space artifact from the source PDF's line
# wraps) — [-\s]+ tolerates any run of hyphens/spaces between the word tokens.
SPELLED = rf"(?:(?:{NUMBER_WORD_RE})(?:[-\s]+hundred)?(?:[-\s]+and)?(?:[-\s]+(?:{NUMBER_WORD_RE}))*)"

# Words that mean the number counts something other than enrolled people. "controls"
# must be plural: "500 controls" is a separate comparison population (case-control
# design, reject), but "control (n=48)" names one randomised arm ("intervention
# (n=48) and control (n=48)", arms summing to the stated total), which PER_ARM
# already handles correctly for the spelled-out pattern.
NOT_PEOPLE = re.compile(
    r"(?i)\b(observations?|studies|articles|papers|records|sessions|samples?|images?|"
    r"videos?|questionnaires?|visits?|scans?|trials?|controls|screened)\b"
)
# Words that mean the number is one arm rather than the whole study. "both groups" /
# "all groups" describe every arm collectively, i.e. the whole study, so those two
# phrasings are excepted rather than treated as a per-arm cue.
PER_ARM = re.compile(
    r"(?i)(?<!both )(?<!all )(\bgroups?\b|\barms?\b|\beach\b|per group|/group|\bsubgroups?\b|\bcompleters?\b)"
)
# "were included" can mean enrolled in the study (the total we want) or included in
# the ANALYSIS after some people dropped out (a smaller, post-attrition subset) -
# "38 children were included in the final analyses" is the latter, and the abstract's
# real enrolled total (40) sits in an earlier, separate sentence ("Forty ... were
# enrolled"). A subset marker right after the match means it is not the total.
SUBSET_MARKER = re.compile(
    r"(?i)\b(final analys\w*|per-protocol|completers?|completed (?:the|all)|dropped out|attrition)\b"
)
# "Eighty-one autistic people, 11 carers/supporters, and 18 clinicians returned
# questionnaires" — a comma-separated list of other counts right after the match
# means several different populations were counted, not one study total.
ENUMERATED_GROUPS = re.compile(r",\s*\d+\s+[a-z]+.*?,\s*(?:and\s+)?\d+\s+[a-z]+", re.IGNORECASE | re.DOTALL)

PARTICIPANT_PATTERNS = [
    # "a total of 112 autistic children"
    re.compile(rf"(?i)\ba total of\s+(\d{{1,5}})\s+(?:[\w-]+\s+){{0,3}}?{PERSON_NOUN}\b"),
    # "Parents (N = 41) of autistic children"
    re.compile(rf"(?i)\b{PERSON_NOUN}\s*\(\s*[Nn]\s*=\s*(\d{{1,5}})\s*\)"),
    # "109 participants were randomized", "40 participants were randomized"
    re.compile(
        rf"(?i)\b(\d{{1,5}})\s+(?:[\w-]+\s+){{0,3}}?{PERSON_NOUN}\s+(?:were|was)\s+"
        r"(?:randomi|enroll|recruit|assign|includ|allocat)"
    ),
    # "recruited 40 children with ASD", "randomized 112 children", "cohort includes
    # 876 children", "Among 642 children", "In this trial, 178 children recruited..."
    re.compile(
        rf"(?i)\b(?:randomi\w+|enrolled|recruited|includ\w*|involving|comprised|among)\s+"
        rf"(\d{{1,5}})\s+(?:[\w-]+\s+){{0,3}}?{PERSON_NOUN}\b"
    ),
    # "the study had 75 participants"
    re.compile(rf"(?i)\b(?:study|trial|cohort|sample)\s+had\s+(\d{{1,5}})\s+(?:[\w-]+\s+){{0,3}}?{PERSON_NOUN}\b"),
    # "178 preschool children with ASD recruited between..." — the enrolment verb
    # trails the noun with no "were/was" in between.
    re.compile(
        rf"(?i)\b(\d{{1,5}})\s+(?:[\w-]+\s+){{0,3}}?{PERSON_NOUN}(?:\s+with\s+[\w-]+)?\s+"
        r"(?:randomi\w+|enrolled|recruited|included)\b"
    ),
    # "delivered ... to 249 parents of autistic children"
    re.compile(rf"(?i)\bto\s+(\d{{1,5}})\s+(?:[\w-]+\s+){{0,3}}?{PERSON_NOUN}\b"),
    # "Of 132 individuals screened, 67 were randomized" — the noun for the total was
    # already given for the screened count; the total itself is anaphoric, so this
    # pattern is deliberately comma-anchored rather than requiring its own noun.
    re.compile(r"(?i),\s*(\d{1,5})\s+(?:were|was)\s+(?:randomi|enroll|recruit|assign|includ|allocat)"),
    # "Forty children", "Eighty-seven autistic children", "One hundred and seven parents"
    re.compile(rf"(?i)\b({SPELLED})\s+(?:[\w-]+\s+){{0,3}}?{PERSON_NOUN}\b"),
]

# An age range without its unit is worse than no age range: "24-60" is months and
# "7-13" is years, and they render identically. Every pattern here must capture the
# unit, and each is anchored on an explicit age cue so that durations
# ("followed for 12-24 months") cannot be mistaken for ages.
AGE_UNIT = r"(years?|yrs?|months?|mos?|weeks?|days?)"
NUM = r"(\d{1,3}(?:\.\d+)?)"
AGE_PATTERNS = [
    # "ages 7-13 years", "aged 3 to 12 years", "age range 2-8 years"
    re.compile(rf"(?i)\bages?d?\b(?:\s+range)?\s+{NUM}\s*(?:to|-|–|—)\s*{NUM}\s*{AGE_UNIT}\b"),
    # "11-35 years of age", "15-30 years old"
    re.compile(rf"(?i)\b{NUM}\s*(?:to|-|–|—)\s*{NUM}\s*{AGE_UNIT}\s*(?:old|of age)\b"),
    # "(6-12 years)" — a parenthesised range next to a population noun
    re.compile(rf"(?i)\(\s*{NUM}\s*(?:to|-|–|—)\s*{NUM}\s*(years?|months?)\s*[,)]"),
]

AGE_UNIT_CANONICAL = {
    "year": "years",
    "years": "years",
    "yr": "years",
    "yrs": "years",
    "month": "months",
    "months": "months",
    "mo": "months",
    "mos": "months",
    "week": "weeks",
    "weeks": "weeks",
    "day": "days",
    "days": "days",
}

DURATION_PATTERNS = [
    re.compile(r"(?i)\b(?:for|over|during|across|up to)\s+(\d+\s*(?:day|days|week|weeks|month|months|year|years))\b"),
    re.compile(r"(?i)\b(\d+-week|\d+-month|\d+-day)\b"),
    re.compile(r"(?i)\b(?:follow[- ]up(?: period)? of|followed for)\s+(\d+\s*(?:day|days|week|weeks|month|months|year|years))\b"),
]


def split_sections(abstract: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(abstract or ""))
    if not matches:
        return {"BODY": (abstract or "").strip()}
    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        label = match.group(1).upper()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(abstract)
        text = abstract[start:end].strip()
        if text:
            sections[label] = text
    return sections


def first_match(patterns: list[re.Pattern[str]], text: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(text or "")
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()
    return None


def infer_age(text: str) -> dict[str, Any]:
    """Return age_min/age_max/age_unit plus a display string, or nulls if no unit is stated."""
    for pattern in AGE_PATTERNS:
        match = pattern.search(text or "")
        if not match:
            continue
        low, high, unit = match.group(1), match.group(2), match.group(3)
        unit = AGE_UNIT_CANONICAL.get(unit.lower().rstrip("."))
        if not unit:
            continue
        age_min, age_max = float(low), float(high)
        if age_max < age_min:
            continue
        age_min = int(age_min) if age_min.is_integer() else age_min
        age_max = int(age_max) if age_max.is_integer() else age_max
        return {
            "age_range": f"{age_min}-{age_max} {unit}",
            "age_min": age_min,
            "age_max": age_max,
            "age_unit": unit,
        }
    return {"age_range": None, "age_min": None, "age_max": None, "age_unit": None}


def words_to_int(text: str) -> int | None:
    total = 0
    current = 0
    for token in re.split(r"[- ]+", text.lower()):
        if token == "and":
            continue
        if token == "hundred":
            current = (current or 1) * 100
            continue
        value = NUMBER_WORDS.get(token)
        if value is None:
            return None
        current += value
    total += current
    return total or None


def infer_participants(text: str) -> int | None:
    """Total people enrolled, or None when the abstract does not state one clearly."""
    text = text or ""
    found: list[int] = []
    for index, pattern in enumerate(PARTICIPANT_PATTERNS):
        # Patterns 0-3 all require an enrolment verb immediately next to the number
        # ("a total of", "(N=X)", "were randomised/enrolled/...", "recruited/included
        # X") - structurally that verb is describing the whole sample, not one arm,
        # so a later "group" mention (e.g. naming the two arms it was split into)
        # must not veto it. Pattern 4 (spelled-out numbers) has no verb requirement
        # at all, so it is the one that needs the per-arm guard: "Seventy-two parents
        # were randomly assigned to an intervention group" is a genuine arm count
        # sitting right next to a person noun, exactly the shape this guard exists for.
        is_spelled_pattern = index == len(PARTICIPANT_PATTERNS) - 1
        for match in pattern.finditer(text):
            # Only the text right after the match can disqualify it: "500 controls"
            # or "(n=15/group)" sit next to the number itself. A word like "trial"
            # in "a randomized controlled trial and included 148 caregivers" sits
            # before the match, describing the study rather than the count, and
            # must not veto a count it has nothing to do with.
            trailing = text[match.end() : match.end() + 60]
            # SUBSET_MARKER gets a much shorter window than NOT_PEOPLE/PER_ARM: it
            # must describe the matched number itself ("were included in the final
            # analyses" right after "38 children"), not a later, different number
            # introduced by its own clause ("Twenty children were enrolled, of whom
            # 13 completed..." - the marker there is about 13, not the matched 20).
            if NOT_PEOPLE.search(trailing) or SUBSET_MARKER.search(text[match.end() : match.end() + 25]):
                continue
            if is_spelled_pattern and PER_ARM.search(trailing):
                continue
            if ENUMERATED_GROUPS.match(text[match.end() : match.end() + 100]):
                continue
            raw = match.group(1)
            value = int(raw) if raw.isdigit() else words_to_int(raw)
            if value and 1 <= value <= 100000:
                found.append(value)
        if found:
            break
    if not found:
        return None
    # Disagreeing candidates from the same pattern mean the abstract is reporting
    # several counts (cases and controls, or several cohorts). Refuse to pick.
    return found[0] if len(set(found)) == 1 else None


def infer_diagnosis(title: str, abstract: str, mesh: list[str], keywords: list[str]) -> str | None:
    blob = " ".join([title or "", abstract or "", " ".join(mesh), " ".join(keywords)]).lower()
    if "autism" in blob or "asd" in blob:
        return "Autism Spectrum Disorder"
    for term in mesh + keywords:
        if term:
            return term
    return None


DIAGNOSIS_LIKE = re.compile(
    r"(?i)^(autism(?: spectrum disorder)?|asd|neurodevelopmental(?: disorder)?|children|adults|"
    r"patients?|individuals?|youth|adolescents?)$"
)


def clean_intervention(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip(" ,.;:-")
    cleaned = re.sub(r"(?i)\s+in (?:children|adults|patients|individuals|youth).*$", "", cleaned).strip()
    if len(cleaned) < 4 or DIAGNOSIS_LIKE.fullmatch(cleaned):
        return None
    if re.search(r"(?i)\bautism spectrum disorder\b", cleaned) and not re.search(
        r"(?i)\b(therapy|treatment|intervention|training|program|stimulation|transplant|device|cannab|oxytocin|quercetin)\b",
        cleaned,
    ):
        return None
    return cleaned[:140]


def infer_intervention(title: str, abstract: str, keywords: list[str]) -> str | None:
    title_l = (title or "").lower()
    candidates = [
        ("cannabidiol", "cannabidiol (CBD)"),
        ("cannabis", "cannabis-based medicinal products"),
        ("quercetin", "quercetin"),
        ("oxytocin", "oxytocin"),
        ("mindfulness", "mindfulness-based intervention"),
        ("wearable", "wearable device physical activity monitoring"),
        ("ayres sensory", "Ayres sensory integration"),
        ("theta-burst", "intermittent theta-burst stimulation (iTBS)"),
        ("microbiota", "washed microbiota transplantation"),
        ("yizhi kaiqiao", "Yizhi Kaiqiao"),
        ("cognitive behavioral", "cognitive behavioral therapy"),
        ("parent-implemented", "parent-implemented intervention"),
        ("music therapy", "group-based music therapy combined with speech therapy"),
        ("speech therapy", "speech therapy"),
        ("artificial intelligence", "AI-supported social communication training"),
        ("professional development", "professional development training"),
        ("self-determination", "self-determination promotion program"),
        ("crisis prevention", "brief mental health crisis prevention program"),
        ("telehealth", "telehealth program"),
        ("vitamin d", "vitamin D"),
        ("care coordination", "care coordination"),
        ("placebo", None),
    ]
    for needle, label in candidates:
        if needle in title_l and label:
            return label

    abstract_l = abstract or ""
    patterns = [
        r"(?i)\b(?:treated with|received|assigned to receive(?: either)?|evaluated the (?:effects|efficacy) of|effects of|efficacy of)\s+([^.;]{8,110})",
        r"(?i)\b(?:using|via|with)\s+((?:AI|artificial intelligence|CBT|cognitive behavioral therapy|wearable devices?|telehealth)[^.;]{0,80})",
    ]
    for pattern in patterns:
        match = re.search(pattern, abstract_l)
        if match:
            cleaned = clean_intervention(match.group(1))
            if cleaned:
                return cleaned

    for kw in keywords:
        cleaned = clean_intervention(kw)
        if cleaned and not DIAGNOSIS_LIKE.search(cleaned):
            return cleaned

    if title:
        # Prefer the clause after a colon when present (often names the approach).
        if ":" in title:
            after = clean_intervention(title.split(":", 1)[1])
            if after:
                return after
        before = clean_intervention(re.split(r"[.?]", title, maxsplit=1)[0])
        if before and "autism" not in before.lower():
            return before
    return None

def infer_outcomes(sections: dict[str, str], abstract: str) -> tuple[list[str], list[str]]:
    primary: list[str] = []
    secondary: list[str] = []
    focus = " ".join(
        sections.get(k, "")
        for k in ("OBJECTIVE", "OBJECTIVES", "PURPOSE", "AIM", "AIMS", "METHODS", "METHOD", "RESULTS", "RESULT")
    ) or abstract
    outcome_hits = re.findall(
        r"(?i)\b((?:GAD-7|SQS|EQ-5D-5L|SRS|WHOQOL|CGI|ABC|Vineland|ADOS|AQ|RBS-R|CBCL|"
        r"primary outcome|secondary outcome|quality of life|anxiety|sleep quality|"
        r"social responsiveness|adverse events?)[^.;,]{0,60})",
        focus,
    )
    seen = set()
    for hit in outcome_hits:
        cleaned = re.sub(r"\s+", " ", hit).strip(" :-")
        key = cleaned.lower()
        if key in seen or len(cleaned) < 3:
            continue
        seen.add(key)
        if "adverse" in key or "secondary" in key:
            secondary.append(cleaned)
        else:
            primary.append(cleaned)
        if len(primary) + len(secondary) >= 6:
            break
    if not primary and sections.get("RESULTS"):
        primary.append(sections["RESULTS"][:180].rstrip() + ("…" if len(sections["RESULTS"]) > 180 else ""))
    return primary[:4], secondary[:3]


def infer_limitations(sections: dict[str, str], abstract: str) -> list[str]:
    blob = " ".join([sections.get("CONCLUSION", ""), sections.get("CONCLUSIONS", ""), abstract or ""])
    limitations: list[str] = []
    patterns = [
        r"(?i)absence of a control group[^.;]{0,80}",
        r"(?i)observational[^.;]{0,80}",
        r"(?i)small sample[^.;]{0,80}",
        r"(?i)further (?:high-quality )?(?:randomized controlled trials|studies|research)[^.;]{0,100}",
        r"(?i)findings represent associations rather than[^.;]{0,80}",
        r"(?i)limited[^.;]{0,80}",
    ]
    for pattern in patterns:
        match = re.search(pattern, blob)
        if match:
            text = re.sub(r"\s+", " ", match.group(0)).strip(" ,;")
            if text and text not in limitations:
                limitations.append(text)
        if len(limitations) >= 3:
            break
    if not limitations:
        limitations.append("Extracted from abstract only; full-text methods and risk-of-bias details were not reviewed.")
    return limitations


def infer_clinical_implications(conclusion: str | None, intervention: str | None, diagnosis: str | None) -> str | None:
    if conclusion:
        sentence = re.split(r"(?<=[.!?])\s+", conclusion.strip())[0]
        if len(sentence) > 40:
            return sentence
    parts = []
    if intervention and diagnosis:
        parts.append(f"May be relevant to {intervention} in {diagnosis}, based on abstract-reported findings.")
    elif diagnosis:
        parts.append(f"May be relevant to clinical care in {diagnosis}; interpret cautiously from abstract-level evidence.")
    return parts[0] if parts else None


def infer_conclusion(sections: dict[str, str], abstract: str) -> str | None:
    """Return the abstract's stated conclusion, or None.

    There is deliberately no fallback to the last paragraph: for an unstructured
    abstract that is the whole abstract, and the page would then print it twice.
    None lets the platform omit the section instead.
    """
    for key in ("CONCLUSION", "CONCLUSIONS"):
        if sections.get(key):
            return sections[key]
    return None


def existing_created_at(pmid: str, year: int | None) -> str | None:
    """Keep the original created_at when a record is rebuilt from the same raw capture."""
    path = study_path(pmid, year)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("created_at")
    except json.JSONDecodeError:
        return None


def build_study(pmid: str) -> dict:
    xml_text = (RAW_XML_DIR / f"PMID{pmid}.xml").read_text(encoding="utf-8")
    abstract = (RAW_ABSTRACT_DIR / f"PMID{pmid}.txt").read_text(encoding="utf-8").strip()
    metadata = metadata_from_xml(pmid, xml_text)
    sections = split_sections(abstract)
    methodsish = " ".join(
        sections.get(k, "")
        for k in ("METHODS", "METHOD", "MATERIALS AND METHODS", "DESIGN", "RESULTS", "RESULT", "BODY")
    )
    all_text = f"{metadata.get('title') or ''}\n{abstract}"
    conclusion = infer_conclusion(sections, abstract)
    intervention = infer_intervention(metadata.get("title") or "", abstract, metadata.get("keywords") or [])
    diagnosis = infer_diagnosis(
        metadata.get("title") or "",
        abstract,
        metadata.get("mesh_terms") or [],
        metadata.get("keywords") or [],
    )
    primary, secondary = infer_outcomes(sections, abstract)
    now = utc_now()
    study = {
        **metadata,
        "participants": infer_participants(methodsish.strip() or all_text),
        **infer_age(all_text),
        "diagnosis": diagnosis,
        "intervention": intervention,
        "duration": first_match(DURATION_PATTERNS, methodsish.strip() or all_text),
        "primary_outcomes": primary,
        "secondary_outcomes": secondary,
        "limitations": infer_limitations(sections, abstract),
        "clinical_implications": infer_clinical_implications(conclusion, intervention, diagnosis),
        "abstract": abstract or None,
        "conclusion": conclusion,
        "created_at": existing_created_at(pmid, metadata.get("year")) or now,
        "last_updated": now,
    }
    return normalize_study(study)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract study JSON from raw PubMed captures.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--pmid", action="append", default=[])
    parser.add_argument(
        "--all",
        action="store_true",
        help="Rebuild every raw capture, including PMIDs that already have a study record.",
    )
    args = parser.parse_args()

    if args.pmid:
        pmids = args.pmid
    else:
        raw_pmids = sorted(p.stem.replace("PMID", "") for p in RAW_ABSTRACT_DIR.glob("PMID*.txt"))
        seen = set() if args.all else existing_pmids()
        pmids = [pmid for pmid in raw_pmids if pmid not in seen]
    if args.limit:
        pmids = pmids[: args.limit]

    saved = []
    failures = []
    for pmid in pmids:
        try:
            study = build_study(pmid)
            errors = validate_study(study)
            if errors:
                raise ValueError("; ".join(errors))
            path = study_path(study["pmid"], study.get("year"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(study, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
            saved.append(str(path))
        except Exception as exc:
            failures.append({"pmid": pmid, "error": str(exc)})

    write_indexes()
    generate_pages()
    print(f"Saved {len(saved)} studies")
    print(f"Failures: {len(failures)}")
    for item in failures:
        print(f"- PMID {item['pmid']}: {item['error']}")
    print(f"Total study JSON files: {len(list(STUDIES_DIR.glob('*/*.json')))}")


if __name__ == "__main__":
    main()
