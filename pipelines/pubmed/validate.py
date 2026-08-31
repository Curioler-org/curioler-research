from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pipelines.pubmed.common import ROOT, STUDIES_DIR

SCHEMA_PATH = ROOT / "schemas" / "study.schema.json"


@lru_cache(maxsize=1)
def _validator():
    """Build a validator from schemas/study.schema.json.

    The schema is the contract, so it is what we check against. A hand-rolled
    subset is how the extraction_confidence type mismatch survived unnoticed.
    """
    import jsonschema

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def validate_study(data: dict[str, Any]) -> list[str]:
    errors = []
    for error in sorted(_validator().iter_errors(data), key=lambda e: list(e.absolute_path)):
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{location}: {error.message}")
    return errors


def validate_file(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"Malformed JSON: {exc}"]
    return validate_study(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate study JSON files against schemas/study.schema.json.")
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
    print(f"Validated {len(paths)} study file(s) against {SCHEMA_PATH.name}.")


if __name__ == "__main__":
    main()
