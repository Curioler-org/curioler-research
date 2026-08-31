#!/usr/bin/env python3
"""Fail if any raw PubMed capture has no study record.

Raw XML is written before extraction runs, so a failed extraction leaves a capture
with nothing published from it, and discovery's sliding window never offers that
PMID again. Eight captures accumulated that way before anyone noticed, because
nothing checked. This is that check.
"""

from __future__ import annotations

import argparse

from pipelines.pubmed.common import RAW_ABSTRACT_DIR, existing_pmids


def orphan_pmids() -> list[str]:
    raw = {path.stem.replace("PMID", "") for path in RAW_ABSTRACT_DIR.glob("PMID*.txt")}
    return sorted(raw - existing_pmids())


def main() -> None:
    parser = argparse.ArgumentParser(description="Check that every raw capture has a study record.")
    parser.parse_args()
    raw_count = len(list(RAW_ABSTRACT_DIR.glob("PMID*.txt")))
    orphans = orphan_pmids()
    if orphans:
        print(f"{len(orphans)} of {raw_count} raw captures have no study record:")
        for pmid in orphans:
            print(f"  - PMID{pmid} (raw/pubmed/xml/PMID{pmid}.xml)")
        print()
        print("Build them with: python -m scripts.extract_studies_from_raw")
        raise SystemExit(1)
    print(f"All {raw_count} raw captures have a study record.")


if __name__ == "__main__":
    main()
