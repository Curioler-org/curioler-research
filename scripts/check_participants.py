#!/usr/bin/env python3
"""Hold the participants parser to a hand-read truth fixture.

The parser may return the recorded total, or null when the abstract does not
state one unambiguously. Any third answer is a failure: a wrong sample size
becomes a wrong sentence in the Easy explainer, read by caregivers.
"""

from __future__ import annotations

import argparse
import json

from pipelines.pubmed.common import RAW_ABSTRACT_DIR, ROOT
from scripts.extract_studies_from_raw import infer_participants, split_sections

TRUTH_PATH = ROOT / "specs" / "fixtures" / "participants-truth.json"


def parsed_value(pmid: str) -> object:
    abstract = (RAW_ABSTRACT_DIR / f"PMID{pmid}.txt").read_text(encoding="utf-8").strip()
    sections = split_sections(abstract)
    methodsish = " ".join(
        sections.get(key, "")
        for key in ("METHODS", "METHOD", "MATERIALS AND METHODS", "DESIGN", "RESULTS", "RESULT", "BODY")
    )
    return infer_participants(methodsish or abstract)


def main() -> None:
    argparse.ArgumentParser(description="Check participants against the truth fixture.").parse_args()
    truth = {k: v for k, v in json.loads(TRUTH_PATH.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    wrong, missing, matched, conceded = [], [], 0, 0
    for pmid, expected in sorted(truth.items()):
        if not (RAW_ABSTRACT_DIR / f"PMID{pmid}.txt").exists():
            missing.append(pmid)
            continue
        actual = parsed_value(pmid)
        if actual == expected:
            matched += 1
        elif actual is None:
            conceded += 1
        else:
            wrong.append((pmid, expected, actual))
    if missing:
        print(f"WARNING: {len(missing)} fixture PMIDs have no raw abstract: {missing}")
    print(f"exact match: {matched}   conceded to null: {conceded}   WRONG: {len(wrong)}")
    for pmid, expected, actual in wrong:
        print(f"  - PMID{pmid}: expected {expected} or null, got {actual}")
    if wrong:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
