from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from pipelines.pubmed.common import INDEX_DIR, STUDIES_DIR


def load_studies() -> list[dict[str, Any]]:
    studies = []
    for path in sorted(STUDIES_DIR.glob("*/*.json")):
        studies.append(json.loads(path.read_text(encoding="utf-8")))
    return studies


def key_or_unknown(value: Any) -> str:
    return str(value).strip() if value not in (None, "", []) else "Unknown"


def append_index(index: dict[str, list[str]], key: Any, pmid: str) -> None:
    index[key_or_unknown(key)].append(pmid)


def generate_indexes() -> dict[str, Any]:
    studies = load_studies()
    by_year: dict[str, list[str]] = defaultdict(list)
    by_study_type: dict[str, list[str]] = defaultdict(list)
    by_intervention: dict[str, list[str]] = defaultdict(list)
    by_topic: dict[str, list[str]] = defaultdict(list)
    latest = sorted(studies, key=lambda item: (item.get("year") or 0, item.get("last_updated") or ""), reverse=True)[:25]
    for study in studies:
        pmid = study["pmid"]
        append_index(by_year, study.get("year"), pmid)
        append_index(by_study_type, study.get("study_type"), pmid)
        append_index(by_intervention, study.get("intervention"), pmid)
        topics = study.get("keywords") or study.get("mesh_terms") or ["Unknown"]
        for topic in topics:
            append_index(by_topic, topic, pmid)
    return {
        "by_year.json": dict(sorted(by_year.items())),
        "by_study_type.json": dict(sorted(by_study_type.items())),
        "by_intervention.json": dict(sorted(by_intervention.items())),
        "by_topic.json": dict(sorted(by_topic.items())),
        "latest.json": latest,
    }


def write_indexes() -> list[Path]:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for filename, data in generate_indexes().items():
        path = INDEX_DIR / filename
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate Curioler research study indexes.")
    parser.parse_args()
    for path in write_indexes():
        print(path)


if __name__ == "__main__":
    main()
