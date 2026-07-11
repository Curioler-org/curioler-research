from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from datetime import date

from pipelines.pubmed.common import existing_pmids, load_config

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"


def build_query(config: dict) -> str:
    start_year = date.today().year - int(config.get("years_back", 10)) + 1
    type_terms = " OR ".join(f'"{item}"[Publication Type]' for item in config["study_types"])
    return f'({config["query"]}) AND ({type_terms}) AND ("{start_year}"[Date - Publication] : "3000"[Date - Publication])'


def search_pubmed(config: dict) -> list[str]:
    params = {
        "db": "pubmed",
        "term": build_query(config),
        "retmode": "json",
        "retmax": str(config.get("max_results", 25)),
        "sort": "pub date",
        "tool": config["pubmed"]["tool"],
        "email": config["pubmed"]["email"],
    }
    url = f"{EUTILS}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("esearchresult", {}).get("idlist", [])


def discover_new_pmids() -> list[str]:
    config = load_config()
    seen = existing_pmids()
    return [pmid for pmid in search_pubmed(config) if pmid not in seen]


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover new PubMed PMIDs for Curioler research ingestion.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of one PMID per line.")
    args = parser.parse_args()
    pmids = discover_new_pmids()
    print(json.dumps(pmids, indent=2) if args.json else "\n".join(pmids))


if __name__ == "__main__":
    main()
