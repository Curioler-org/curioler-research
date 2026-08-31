#!/usr/bin/env python3
"""Corpus invariants for the Easy explainer.

The block is read by caregivers deciding about their child's care, so the
failure that matters is not a crash but a confident sentence the record does
not support. These checks target exactly that.
"""

from __future__ import annotations

import argparse
import json
import re

from pipelines.pubmed.common import STUDIES_DIR
from pipelines.pubmed.explainer import SMALL_SAMPLE, base_tier, build_explainer, design_kind, trust_tier

MISSING_PHRASES = {
    "the ages of the people who took part": "age_range",
    "how long the study ran": "duration",
}

# A small trial and a small observational study are not equally weak evidence: the
# trial's randomisation still controls confounding, the observational study's does
# not. The size sentence must say so, not just report the same generic warning for
# both - this pins that distinction down as a corpus invariant. Markers are chosen
# to be non-overlapping substrings ("random assignment" alone would also match
# inside the observational sentence's "without random assignment").
DESIGN_SIZE_MARKERS = {
    "trial": "started out comparable",
    "observational": "something other than what was studied",
}


def check(study: dict) -> list[str]:
    errors = []
    tier, label = study.get("trust_tier"), study.get("trust_tier_label")
    explainer = study.get("easy_explainer") or {}

    if not isinstance(tier, int) or not 1 <= tier <= 4:
        errors.append(f"trust_tier must be 1-4, got {tier!r}")
    if not label:
        errors.append("trust_tier_label is empty")
    if tier == 4 and study.get("study_type"):
        errors.append(f"tier 4 means 'design not stated', but study_type is {study['study_type']!r}")

    # A number in the size sentence with no participants value is the failure mode
    # this whole feature was designed around.
    if study.get("participants") is None and re.search(r"\d", explainer.get("size", "")):
        errors.append(f"size sentence quotes a number but participants is null: {explainer.get('size')!r}")
    if study.get("participants") is None and tier != base_tier(study.get("study_type")):
        errors.append("tier was demoted while participants is null")
    # The null-case sentence ("...does not state what the researchers concluded.")
    # also contains the words "researchers concluded", so match on the quote marker
    # that only the populated case produces, not the bare phrase.
    if study.get("conclusion") is None and 'researchers concluded: "' in (explainer.get("conclusion") or ""):
        errors.append("conclusion sentence quotes researchers but conclusion is null")

    participants = study.get("participants")
    kind = design_kind(study.get("study_type"))
    if isinstance(participants, int) and 1 < participants < SMALL_SAMPLE and kind in DESIGN_SIZE_MARKERS:
        marker = DESIGN_SIZE_MARKERS[kind]
        size_text = (explainer.get("size") or "").lower()
        if marker not in size_text:
            errors.append(f"small-sample {kind} size sentence should mention {marker!r}: {explainer.get('size')!r}")
        other_marker = next(v for k, v in DESIGN_SIZE_MARKERS.items() if k != kind)
        if other_marker in size_text:
            errors.append(f"small-sample {kind} size sentence uses the {other_marker!r} wording of the other design")

    for phrase in explainer.get("not_stated", []):
        field = MISSING_PHRASES.get(phrase)
        if field is None:
            errors.append(f"unrecognised not_stated phrase: {phrase!r}")
        elif study.get(field):
            errors.append(f"not_stated claims {field} is missing, but it is {study[field]!r}")

    # Text must be reproducible from the record alone.
    if explainer != build_explainer(study):
        errors.append("easy_explainer does not match a fresh build from this record")
    if (tier, label) != trust_tier(study):
        errors.append("trust_tier/label do not match a fresh computation")
    return errors


def main() -> None:
    argparse.ArgumentParser(description="Check Easy explainer invariants.").parse_args()
    paths = sorted(STUDIES_DIR.glob("*/*.json"))
    failed = False
    for path in paths:
        study = json.loads(path.read_text(encoding="utf-8"))
        errors = check(study)
        if errors:
            failed = True
            print(f"{path}:")
            for error in errors:
                print(f"  - {error}")
    if failed:
        raise SystemExit(1)
    print(f"Easy explainer invariants hold across {len(paths)} study file(s).")


if __name__ == "__main__":
    main()
