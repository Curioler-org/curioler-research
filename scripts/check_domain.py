#!/usr/bin/env python3
"""Hold every study record to a reviewed `domain`.

`domain` is a caregiver-facing editorial judgement (see the study-domain hand-off),
not something PubMed metadata can answer, so the failure that matters here is not a
crash but a record silently shipping uncategorised - or worse, silently defaulted to
"general" - on the public Studies browse page.
"""

from __future__ import annotations

import argparse
import json

from pipelines.pubmed.common import DOMAIN_VALUES, STUDIES_DIR, load_study_domains


def check(pmid: str, study: dict, overrides: dict[str, str]) -> list[str]:
    errors = []
    domain = study.get("domain")
    if domain not in DOMAIN_VALUES:
        errors.append(f"domain is missing or out of vocabulary: {domain!r}")
    if pmid not in overrides:
        errors.append(f"PMID{pmid} has no reviewed entry in config/study_domains.json")
    elif overrides[pmid] != domain:
        errors.append(f"domain {domain!r} does not match the reviewed override {overrides[pmid]!r}")
    return errors


def main() -> None:
    argparse.ArgumentParser(description="Check study domain against the reviewed overrides map.").parse_args()
    overrides = load_study_domains()
    paths = sorted(STUDIES_DIR.glob("*/*.json"))
    failed = False
    for path in paths:
        study = json.loads(path.read_text(encoding="utf-8"))
        errors = check(study["pmid"], study, overrides)
        if errors:
            failed = True
            print(f"{path}:")
            for error in errors:
                print(f"  - {error}")
    if failed:
        raise SystemExit(1)
    print(f"Every study carries a reviewed domain across {len(paths)} study file(s).")


if __name__ == "__main__":
    main()
