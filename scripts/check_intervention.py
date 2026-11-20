#!/usr/bin/env python3
"""Hold the intervention parser to a hand-read truth fixture.

The parser may return one of the recorded names for the paper's intervention, or
null when the title and vocabulary do not name it clearly. Any third answer is a
failure: the old fallbacks stored PubMed keywords ("ADHD", "Biomarker"), a design
phrase from the title ("A Randomized Trial") or the control arm ("PRT education
only") as the intervention, and the value feeds the by_intervention index and
site search.
"""

from __future__ import annotations

import argparse
import json
import re

from pipelines.pubmed.common import RAW_ABSTRACT_DIR, RAW_XML_DIR, ROOT
from pipelines.pubmed.extract import metadata_from_xml
from scripts.extract_studies_from_raw import infer_intervention

TRUTH_PATH = ROOT / "specs" / "fixtures" / "intervention-truth.json"


def normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def parsed_value(pmid: str) -> str | None:
    xml_text = (RAW_XML_DIR / f"PMID{pmid}.xml").read_text(encoding="utf-8")
    abstract = (RAW_ABSTRACT_DIR / f"PMID{pmid}.txt").read_text(encoding="utf-8").strip()
    metadata = metadata_from_xml(pmid, xml_text)
    return infer_intervention(metadata.get("title") or "", abstract, metadata.get("keywords") or [])


def main() -> None:
    argparse.ArgumentParser(description="Check intervention against the truth fixture.").parse_args()
    truth = {k: v for k, v in json.loads(TRUTH_PATH.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    wrong, missing, matched, conceded, null_right = [], [], 0, 0, 0
    for pmid, accepted in sorted(truth.items()):
        if not (RAW_XML_DIR / f"PMID{pmid}.xml").exists():
            missing.append(pmid)
            continue
        actual = parsed_value(pmid)
        if accepted is None:
            if actual is None:
                null_right += 1
            else:
                wrong.append((pmid, "null (no intervention studied)", actual))
        elif actual is None:
            conceded += 1
        elif normalise(actual) in {normalise(name) for name in accepted}:
            matched += 1
        else:
            wrong.append((pmid, " | ".join(accepted) + " | null", actual))
    if missing:
        print(f"WARNING: {len(missing)} fixture PMIDs have no raw capture: {missing}")
    print(
        f"named correctly: {matched}   correctly null: {null_right}   "
        f"conceded to null: {conceded}   WRONG: {len(wrong)}"
    )
    for pmid, expected, actual in wrong:
        print(f"  - PMID{pmid}: expected {expected}, got {actual!r}")
    if wrong:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
