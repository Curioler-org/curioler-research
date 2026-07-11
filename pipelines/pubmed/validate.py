from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from pipelines.pubmed.common import STUDY_FIELDS, STUDIES_DIR


def validate_study(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in STUDY_FIELDS:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    if not re.fullmatch(r"[0-9]+", str(data.get("pmid", ""))):
        errors.append("PMID must contain only digits")
    if not data.get("title"):
        errors.append("Title is required")
    if not re.fullmatch(r"https://pubmed\.ncbi\.nlm\.nih\.gov/[0-9]+/?", str(data.get("source_url", ""))):
        errors.append("source_url must be a PubMed URL")
    for field in ["authors", "primary_outcomes", "secondary_outcomes", "limitations", "mesh_terms", "keywords"]:
        if field in data and not isinstance(data[field], list):
            errors.append(f"{field} must be a list")
    return errors


def validate_file(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"Malformed JSON: {exc}"]
    return validate_study(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate study JSON files.")
    parser.add_argument("paths", nargs="*", help="Study JSON paths. Defaults to all studies.")
    args = parser.parse_args()
    paths = [Path(path) for path in args.paths] if args.paths else sorted(STUDIES_DIR.glob("*/*.json"))
    failed = False
    for path in paths:
        errors = validate_file(path)
        if errors:
            failed = True
            print(f"{path}:")
            for error in errors:
                print(f"  - {error}")
    if failed:
        raise SystemExit(1)
    print(f"Validated {len(paths)} study file(s).")


if __name__ == "__main__":
    main()
