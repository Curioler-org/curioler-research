"""Fill in PubMed and PubMed Central sources that web search returns empty.

Tavily gets little more than the title from PMC article pages, so the one
source that states participants, design and results is the one the model
never sees. For those, fetch the abstract from NCBI E-utilities (the same free
API pipelines/pubmed uses) and put it in place of the thin search content.

Shared by generate_summary.py and check_myth.py.
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

THIN_CONTENT_CHARS = 1500
TOOL = "curioler-research"
IDCONV = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

PMC_URL = re.compile(r"(?:pmc\.ncbi\.nlm\.nih\.gov/articles/|ncbi\.nlm\.nih\.gov/pmc/articles/)(PMC\d+)", re.I)
PUBMED_URL = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", re.I)


def _get(url: str, params: dict) -> str:
    query = urllib.parse.urlencode({**params, "tool": TOOL})
    with urllib.request.urlopen(f"{url}?{query}", timeout=30) as response:
        return response.read().decode("utf-8")


def _pmid_for(url: str) -> str | None:
    if match := PUBMED_URL.search(url):
        return match.group(1)
    if match := PMC_URL.search(url):
        records = json.loads(_get(IDCONV, {"ids": match.group(1), "format": "json"})).get("records", [])
        return records[0].get("pmid") if records else None
    return None


def _abstract(pmid: str) -> str:
    root = ET.fromstring(_get(EFETCH, {"db": "pubmed", "id": pmid, "retmode": "xml"}))
    parts = []
    for node in root.findall(".//AbstractText"):
        text = " ".join("".join(node.itertext()).split())
        if text:
            label = node.attrib.get("Label")
            parts.append(f"{label}: {text}" if label else text)
    return html.unescape("\n".join(parts))


def fill_thin_pubmed_sources(results: list[dict]) -> list[dict]:
    """Replace near-empty PubMed/PMC search content with the paper's abstract.
    Anything that fails is left as it was; this never blocks a run."""
    for result in results:
        content = result.get("raw_content") or result.get("content") or ""
        if len(content) >= THIN_CONTENT_CHARS:
            continue
        try:
            pmid = _pmid_for(result.get("url", ""))
            abstract = _abstract(pmid) if pmid else ""
        except Exception as exc:  # network or parse trouble: keep what search gave
            print(f"  could not fetch abstract for {result.get('url')}: {exc}")
            continue
        if abstract:
            result["raw_content"] = f"PubMed abstract (PMID {pmid}):\n{abstract}"
            print(f"  filled abstract from PubMed for PMID {pmid}")
    return results
