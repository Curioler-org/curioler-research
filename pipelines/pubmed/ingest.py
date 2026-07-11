from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from pipelines.pubmed.common import existing_dois, existing_pmids, study_path
from pipelines.pubmed.discover import discover_new_pmids
from pipelines.pubmed.extract import extract_study
from pipelines.pubmed.fetch import fetch_and_store
from pipelines.pubmed.index import write_indexes
from pipelines.pubmed.validate import validate_study
from scripts.generate_study_pages import generate_pages


def save_study(study: dict) -> Path:
    path = study_path(study["pmid"], study.get("year"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(study, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run(limit: int | None = None) -> dict:
    started = time.monotonic()
    pmids = discover_new_pmids()
    if limit:
        pmids = pmids[:limit]
    seen_pmids = existing_pmids()
    seen_dois = existing_dois()
    summary = {
        "new_studies": 0,
        "duplicates": 0,
        "extraction_failures": 0,
        "validation_failures": 0,
        "indexes_updated": 0,
        "failures": [],
        "saved_files": [],
    }

    for pmid in pmids:
        try:
            if pmid in seen_pmids:
                summary["duplicates"] += 1
                continue
            fetch_and_store(pmid)
            study = extract_study(pmid)
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
    print(f"Duplicates: {summary['duplicates']}")
    print(f"Extraction Failures: {summary['extraction_failures']}")
    print(f"Validation Failures: {summary['validation_failures']}")
    print(f"Indexes Updated: {summary['indexes_updated']}")
    print(f"Completed In: {summary['completed_in']}")
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
