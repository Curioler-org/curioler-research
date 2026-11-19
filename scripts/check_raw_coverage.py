#!/usr/bin/env python3
"""Fail if any raw PubMed capture has no study record.

Raw XML is written before extraction runs, so a failed extraction leaves a capture
with nothing published from it, and discovery's sliding window never offers that
PMID again. Eight captures accumulated that way before anyone noticed, because
nothing checked. This is that check.

One state is not a failure: a capture whose PMID has no reviewed `domain` in
config/study_domains.json. Domain is a founder-reviewed editorial judgement, so no
record can be built until someone reviews it (the schema rejects a record without
one). Ingestion skips those captures by the same rule and lists them in its run
summary; once a domain is added, the next run's backfill builds the record. They
are reported here as a warning so the queue stays visible without turning the
daily run red.
"""

from __future__ import annotations

import argparse
import os

from pipelines.pubmed.common import RAW_ABSTRACT_DIR, existing_pmids, load_study_domains


def classify(raw: set[str], recorded: set[str], reviewed: dict[str, str]) -> tuple[list[str], list[str]]:
    """Split captures without a record into (orphans, awaiting domain review)."""
    missing = raw - recorded
    orphans = sorted(pmid for pmid in missing if pmid in reviewed)
    awaiting = sorted(pmid for pmid in missing if pmid not in reviewed)
    return orphans, awaiting


def raw_pmids() -> set[str]:
    return {path.stem.replace("PMID", "") for path in RAW_ABSTRACT_DIR.glob("PMID*.txt")}


def orphan_pmids() -> list[str]:
    return classify(raw_pmids(), existing_pmids(), load_study_domains())[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Check that every raw capture has a study record.")
    parser.parse_args()
    raw = raw_pmids()
    orphans, awaiting = classify(raw, existing_pmids(), load_study_domains())

    if awaiting:
        print(f"{len(awaiting)} of {len(raw)} raw captures await a reviewed domain:")
        for pmid in awaiting:
            print(f"  - PMID{pmid}")
        print("Add each to config/study_domains.json; the next ingestion run builds its record.")
        print()
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(
                f"::warning title=Studies awaiting domain review::{len(awaiting)} fetched papers have no "
                "reviewed domain in config/study_domains.json, so they are not published yet."
            )

    if orphans:
        print(f"{len(orphans)} of {len(raw)} raw captures have a reviewed domain but no study record:")
        for pmid in orphans:
            print(f"  - PMID{pmid} (raw/pubmed/xml/PMID{pmid}.xml)")
        print()
        print("Build them with: python -m scripts.extract_studies_from_raw")
        raise SystemExit(1)
    print(f"Every raw capture with a reviewed domain has a study record ({len(raw) - len(awaiting)} of {len(raw)}).")


if __name__ == "__main__":
    main()
