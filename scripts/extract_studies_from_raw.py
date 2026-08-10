#!/usr/bin/env python3
"""Build study JSON from already-fetched PubMed raw files (no LLM required)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

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

PARTICIPANT_PATTERNS = [
    re.compile(r"(?i)\b(\d{1,4})\s+(?:adults?|children|adolescents?|youth|patients?|participants?|individuals?|subjects?)\b"),
    re.compile(r"(?i)\b(?:n\s*=\s*|sample of |enrolled |included |analyzed )\(?(\d{1,4})\)?"),
    re.compile(r"(?i)\bdata from\s+(\d{1,4})\s+(?:subjects?|participants?|patients?)"),
]

AGE_PATTERNS = [
    re.compile(r"(?i)\bages?\s+(\d{1,2}\s*(?:to|-|–)\s*\d{1,2})\s*(?:years?)?"),
    re.compile(r"(?i)\b(\d{1,2}\s*(?:to|-|–)\s*\d{1,2})\s*years?\s*(?:old|of age)?"),
    re.compile(r"(?i)\bmean(?:\s*age)?[:\s]+(\d{1,2}(?:\.\d+)?)\s*years?"),
    re.compile(r"(?i)\baged\s+(\d{1,2}\s*(?:to|-|–)\s*\d{1,2})"),
]

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


def infer_participants(text: str) -> int | str | None:
    value = first_match(PARTICIPANT_PATTERNS, text)
    if value and value.isdigit():
        return int(value)
    return value


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
    for key in ("CONCLUSION", "CONCLUSIONS"):
        if sections.get(key):
            return sections[key]
    # Fall back to last paragraph-like chunk.
    parts = [p.strip() for p in re.split(r"\n+", abstract or "") if p.strip()]
    return parts[-1] if parts else None


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
        "participants": infer_participants(methodsish or all_text),
        "age_range": first_match(AGE_PATTERNS, methodsish or all_text),
        "diagnosis": diagnosis,
        "intervention": intervention,
        "duration": first_match(DURATION_PATTERNS, methodsish or all_text),
        "primary_outcomes": primary,
        "secondary_outcomes": secondary,
        "limitations": infer_limitations(sections, abstract),
        "clinical_implications": infer_clinical_implications(conclusion, intervention, diagnosis),
        "abstract": abstract or None,
        "conclusion": conclusion,
        "extraction_confidence": "medium",
        "created_at": now,
        "last_updated": now,
    }
    return normalize_study(study)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract study JSON from raw PubMed captures.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--pmid", action="append", default=[])
    args = parser.parse_args()

    if args.pmid:
        pmids = args.pmid
    else:
        raw_pmids = sorted(p.stem.replace("PMID", "") for p in RAW_ABSTRACT_DIR.glob("PMID*.txt"))
        seen = existing_pmids()
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
