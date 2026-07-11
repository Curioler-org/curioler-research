from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STUDIES_DIR = ROOT / "research" / "studies"
DOCS_STUDIES_DIR = ROOT / "docs" / "_studies"
DOCS_DATA_DIR = ROOT / "docs" / "_data"


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:72].strip("-") or "study"


def load_studies() -> list[dict[str, Any]]:
    studies = []
    for path in sorted(STUDIES_DIR.glob("*/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_source_file"] = str(path.relative_to(ROOT)).replace("\\", "/")
        studies.append(data)
    return studies


def frontmatter_value(value: Any) -> str:
    if value is None:
        return '""'
    return json.dumps(value, ensure_ascii=False)


def render_study_page(study: dict[str, Any]) -> str:
    title = study.get("title") or f"PMID {study['pmid']}"
    slug = f"PMID{study['pmid']}-{slugify(title)}"
    lines = [
        "---",
        "layout: study",
        f"title: {frontmatter_value(title)}",
        f"slug: {frontmatter_value(slug)}",
        f"pmid: {frontmatter_value(study.get('pmid'))}",
        f"doi: {frontmatter_value(study.get('doi'))}",
        f"year: {frontmatter_value(study.get('year'))}",
        f"journal: {frontmatter_value(study.get('journal'))}",
        f"authors: {frontmatter_value(study.get('authors', []))}",
        f"study_type: {frontmatter_value(study.get('study_type'))}",
        f"participants: {frontmatter_value(study.get('participants'))}",
        f"age_range: {frontmatter_value(study.get('age_range'))}",
        f"diagnosis: {frontmatter_value(study.get('diagnosis'))}",
        f"intervention: {frontmatter_value(study.get('intervention'))}",
        f"duration: {frontmatter_value(study.get('duration'))}",
        f"primary_outcomes: {frontmatter_value(study.get('primary_outcomes', []))}",
        f"secondary_outcomes: {frontmatter_value(study.get('secondary_outcomes', []))}",
        f"limitations: {frontmatter_value(study.get('limitations', []))}",
        f"clinical_implications: {frontmatter_value(study.get('clinical_implications'))}",
        f"abstract: {frontmatter_value(study.get('abstract'))}",
        f"conclusion: {frontmatter_value(study.get('conclusion'))}",
        f"mesh_terms: {frontmatter_value(study.get('mesh_terms', []))}",
        f"keywords: {frontmatter_value(study.get('keywords', []))}",
        f"source_url: {frontmatter_value(study.get('source_url'))}",
        f"extraction_confidence: {frontmatter_value(study.get('extraction_confidence'))}",
        f"created_at: {frontmatter_value(study.get('created_at'))}",
        f"last_updated: {frontmatter_value(study.get('last_updated'))}",
        "---",
        "",
    ]
    return "\n".join(lines)


def public_study_summary(study: dict[str, Any]) -> dict[str, Any]:
    slug = f"PMID{study['pmid']}-{slugify(study.get('title') or '')}"
    return {
        "title": study.get("title"),
        "pmid": study.get("pmid"),
        "year": study.get("year"),
        "study_type": study.get("study_type"),
        "intervention": study.get("intervention"),
        "diagnosis": study.get("diagnosis"),
        "journal": study.get("journal"),
        "url": f"/studies/{slug}/",
        "source_url": study.get("source_url"),
    }


def generate_pages() -> None:
    studies = load_studies()
    DOCS_STUDIES_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for old in DOCS_STUDIES_DIR.glob("*.md"):
        old.unlink()
    for study in studies:
        title = study.get("title") or f"PMID {study['pmid']}"
        slug = f"PMID{study['pmid']}-{slugify(title)}"
        (DOCS_STUDIES_DIR / f"{slug}.md").write_text(render_study_page(study), encoding="utf-8")
    data = [public_study_summary(study) for study in studies]
    DOCS_DATA_DIR.joinpath("studies.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    generate_pages()
    print("Generated study pages and docs/_data/studies.json")


if __name__ == "__main__":
    main()
