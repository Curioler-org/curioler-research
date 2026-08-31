from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pipelines.pubmed.explainer import build_explainer, trust_tier

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "research_ingestion.json"
STUDY_DOMAINS_PATH = ROOT / "config" / "study_domains.json"
STUDIES_DIR = ROOT / "research" / "studies"
INDEX_DIR = ROOT / "research" / "indexes"
RAW_XML_DIR = ROOT / "raw" / "pubmed" / "xml"
RAW_ABSTRACT_DIR = ROOT / "raw" / "pubmed" / "abstracts"

# The platform's canonical knowledge-domain vocabulary (migration
# 003_knowledge_domains.sql). `domain` is a caregiver-facing editorial judgement, not
# something derivable from PubMed metadata, so it is never inferred here - see
# STUDY_DOMAINS_PATH.
DOMAIN_VALUES = ["adaptive", "behaviour", "cognitive", "communication", "general", "motor", "sensory", "social"]

STUDY_FIELDS = [
    "pmid",
    "doi",
    "title",
    "year",
    "journal",
    "authors",
    "study_type",
    "domain",
    "trust_tier",
    "trust_tier_label",
    "easy_explainer",
    "participants",
    "age_range",
    "age_min",
    "age_max",
    "age_unit",
    "diagnosis",
    "co_occurring_conditions",
    "intervention",
    "duration",
    "primary_outcomes",
    "secondary_outcomes",
    "limitations",
    "clinical_implications",
    "abstract",
    "conclusion",
    "mesh_terms",
    "keywords",
    "source_url",
    "created_at",
    "last_updated",
]

ARRAY_FIELDS = {
    "authors",
    "co_occurring_conditions",
    "primary_outcomes",
    "secondary_outcomes",
    "limitations",
    "mesh_terms",
    "keywords",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def current_year() -> int:
    return date.today().year


def load_config() -> dict[str, Any]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config["ai_provider"] = (os.environ.get("AI_PROVIDER") or config.get("ai_provider", "openrouter")).lower()
    config["ai_model"] = os.environ.get("AI_MODEL") or config.get("ai_model", "")
    config["pubmed"]["email"] = os.environ.get("PUBMED_EMAIL") or config["pubmed"].get("email", "")
    config["pubmed"]["tool"] = os.environ.get("PUBMED_TOOL_NAME") or config["pubmed"].get("tool", "curioler-research")
    return config


def load_study_domains() -> dict[str, str]:
    """PMID -> reviewed domain, from the checked-in overrides map.

    This is a human judgement call (see the study-domain hand-off), so regeneration
    must read it rather than derive a value: a PMID with no entry gets no domain,
    which fails schema validation instead of silently defaulting to "general".
    """
    if not STUDY_DOMAINS_PATH.exists():
        return {}
    return json.loads(STUDY_DOMAINS_PATH.read_text(encoding="utf-8"))


def existing_pmids() -> set[str]:
    return {path.stem.replace("PMID", "") for path in STUDIES_DIR.glob("*/*.json")}


def existing_dois() -> set[str]:
    dois: set[str] = set()
    for path in STUDIES_DIR.glob("*/*.json"):
        try:
            doi = json.loads(path.read_text(encoding="utf-8")).get("doi")
        except json.JSONDecodeError:
            continue
        if doi:
            dois.add(str(doi).lower())
    return dois


def study_path(pmid: str, year: int | None) -> Path:
    bucket = str(year or "unknown")
    return STUDIES_DIR / bucket / f"PMID{pmid}.json"


def normalize_array(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(value)]


def normalize_study(data: dict[str, Any]) -> dict[str, Any]:
    normalized = {field: data.get(field) for field in STUDY_FIELDS}
    for field in ARRAY_FIELDS:
        normalized[field] = normalize_array(normalized[field])
    normalized["pmid"] = str(normalized["pmid"] or "")
    normalized["source_url"] = normalized["source_url"] or f"https://pubmed.ncbi.nlm.nih.gov/{normalized['pmid']}/"
    # Overrides win over anything an extraction path supplied: domain is reviewed
    # human judgement, not model output, so a rebuild must not silently drop it.
    normalized["domain"] = load_study_domains().get(normalized["pmid"])
    # Derived last, from the settled fields, so both extraction paths and every
    # rebuild produce the same block.
    normalized["trust_tier"], normalized["trust_tier_label"] = trust_tier(normalized)
    normalized["easy_explainer"] = build_explainer(normalized)
    return normalized
