from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from pipelines.pubmed.common import (
    RAW_ABSTRACT_DIR,
    RAW_XML_DIR,
    existing_dois,
    existing_pmids,
    load_study_domains,
    study_path,
)
from pipelines.pubmed.discover import discover_new_pmids
from pipelines.pubmed.extract import extract_study, metadata_from_xml
from pipelines.pubmed.fetch import fetch_and_store
from pipelines.pubmed.index import write_indexes
from pipelines.pubmed.validate import validate_study
from scripts.extract_studies_from_raw import build_study
from scripts.generate_study_pages import generate_pages


def save_study(study: dict) -> Path:
    path = study_path(study["pmid"], study.get("year"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(study, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return path


def extract_with_fallback(pmid: str, summary: dict) -> dict:
    """Extract one study, falling back to the abstract-rules extractor.

    `fetch_and_store` writes the raw XML before extraction runs, so an extraction
    that raises used to leave a raw capture with no study record. Discovery is a
    sliding window over the newest results, so that capture then fell out of range
    and was never retried — which is how eight raw files sat unpublished. The
    fallback is deterministic and needs no API key, so a fetched paper always
    produces a record in the same run.
    """
    try:
        study = extract_study(pmid)
        summary["llm_extractions"] += 1
        return study
    except Exception as exc:
        summary["llm_fallbacks"] += 1
        summary["llm_errors"].append({"pmid": pmid, "error": str(exc)})
        return build_study(pmid)


def raw_pmids() -> list[str]:
    return sorted(path.stem.replace("PMID", "") for path in RAW_ABSTRACT_DIR.glob("PMID*.txt"))


def raw_title(pmid: str) -> str | None:
    try:
        xml_text = (RAW_XML_DIR / f"PMID{pmid}.xml").read_text(encoding="utf-8")
        return metadata_from_xml(pmid, xml_text).get("title")
    except Exception:
        return None


def backfill_orphans(summary: dict, seen_pmids: set[str], seen_dois: set[str]) -> None:
    """Give a study record to every raw capture that does not have one yet.

    Covers captures orphaned by earlier runs, captures whose domain was reviewed
    since they were fetched, and any raw file added by hand. A capture with no
    reviewed domain cannot become a valid record yet (domain is never inferred), so
    it is listed as awaiting review rather than counted as a validation failure;
    scripts/check_raw_coverage.py applies the same rule.
    """
    reviewed = load_study_domains()
    for pmid in raw_pmids():
        if pmid in seen_pmids:
            continue
        if pmid not in reviewed:
            summary["awaiting_domain_review"].append({"pmid": pmid, "title": raw_title(pmid)})
            continue
        try:
            study = build_study(pmid)
        except Exception as exc:
            summary["extraction_failures"] += 1
            summary["failures"].append({"pmid": pmid, "stage": "backfill", "error": str(exc)})
            continue
        doi = study.get("doi")
        if doi and str(doi).lower() in seen_dois:
            summary["duplicates"] += 1
            continue
        errors = validate_study(study)
        if errors:
            summary["validation_failures"] += 1
            summary["failures"].append({"pmid": pmid, "stage": "backfill-validate", "error": "; ".join(errors)})
            continue
        path = save_study(study)
        seen_pmids.add(pmid)
        if doi:
            seen_dois.add(str(doi).lower())
        summary["backfilled"] += 1
        summary["saved_files"].append(str(path))


def new_summary() -> dict:
    return {
        "new_studies": 0,
        "backfilled": 0,
        "duplicates": 0,
        "llm_extractions": 0,
        "llm_fallbacks": 0,
        "extraction_failures": 0,
        "validation_failures": 0,
        "indexes_updated": 0,
        "failures": [],
        "llm_errors": [],
        "saved_files": [],
        "awaiting_domain_review": [],
    }


def run(limit: int | None = None) -> dict:
    started = time.monotonic()
    pmids = discover_new_pmids()
    if limit:
        pmids = pmids[:limit]
    seen_pmids = existing_pmids()
    seen_dois = existing_dois()
    reviewed = load_study_domains()
    summary = new_summary()

    for pmid in pmids:
        try:
            if pmid in seen_pmids:
                summary["duplicates"] += 1
                continue
            fetch_and_store(pmid)
            if pmid not in reviewed:
                # No reviewed domain yet, so no valid record can be built; skip the
                # extraction call. backfill_orphans lists it as awaiting review and
                # builds it on the first run after its domain is added.
                continue
            study = extract_with_fallback(pmid, summary)
            doi = study.get("doi")
            if doi and str(doi).lower() in seen_dois:
                summary["duplicates"] += 1
                continue
        except Exception as exc:
            summary["extraction_failures"] += 1
            summary["failures"].append({"pmid": pmid, "stage": "extract", "error": str(exc)})
            continue

        errors = validate_study(study)
        if errors:
            summary["validation_failures"] += 1
            summary["failures"].append({"pmid": pmid, "stage": "validate", "error": "; ".join(errors)})
            continue

        path = save_study(study)
        seen_pmids.add(pmid)
        if study.get("doi"):
            seen_dois.add(str(study["doi"]).lower())
        summary["new_studies"] += 1
        summary["saved_files"].append(str(path))

    backfill_orphans(summary, seen_pmids, seen_dois)

    written_indexes = write_indexes()
    generate_pages()
    summary["indexes_updated"] = len(written_indexes)
    elapsed = int(time.monotonic() - started)
    summary["completed_in"] = f"{elapsed // 60}m {elapsed % 60}s"
    return summary


def print_summary(summary: dict) -> None:
    print("Pipeline Summary")
    print()
    print(f"New Studies: {summary['new_studies']}")
    print(f"Backfilled From Raw: {summary['backfilled']}")
    print(f"Duplicates: {summary['duplicates']}")
    print(f"LLM Extractions: {summary['llm_extractions']}")
    print(f"Abstract-Rules Fallbacks: {summary['llm_fallbacks']}")
    print(f"Extraction Failures: {summary['extraction_failures']}")
    print(f"Validation Failures: {summary['validation_failures']}")
    print(f"Indexes Updated: {summary['indexes_updated']}")
    print(f"Awaiting Domain Review: {len(summary['awaiting_domain_review'])}")
    print(f"Completed In: {summary['completed_in']}")
    if summary["awaiting_domain_review"]:
        print()
        print("Awaiting domain review (add each PMID to config/study_domains.json to publish it):")
        for item in summary["awaiting_domain_review"]:
            print(f"- PMID {item['pmid']}: {item['title'] or '(title unavailable)'}")
    if summary["llm_errors"]:
        print()
        print("LLM extraction fell back to abstract rules:")
        for item in summary["llm_errors"]:
            print(f"- PMID {item['pmid']}: {item['error']}")
    if summary["failures"]:
        print()
        print("Failures:")
        for failure in summary["failures"]:
            print(f"- PMID {failure['pmid']} ({failure['stage']}): {failure['error']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the PubMed ingestion pipeline.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum new studies to process.")
    args = parser.parse_args()
    print_summary(run(limit=args.limit))


if __name__ == "__main__":
    main()
