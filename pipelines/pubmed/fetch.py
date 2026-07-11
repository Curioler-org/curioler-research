from __future__ import annotations

import argparse
import html
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from pipelines.pubmed.common import RAW_ABSTRACT_DIR, RAW_XML_DIR, load_config

EUTILS_FETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def fetch_xml(pmid: str) -> str:
    config = load_config()
    params = {
        "db": "pubmed",
        "id": pmid,
        "retmode": "xml",
        "tool": config["pubmed"]["tool"],
        "email": config["pubmed"]["email"],
    }
    url = f"{EUTILS_FETCH}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read().decode("utf-8")


def abstract_from_xml(xml_text: str) -> str:
    root = ET.fromstring(xml_text)
    parts: list[str] = []
    for node in root.findall(".//AbstractText"):
        label = node.attrib.get("Label")
        text = " ".join("".join(node.itertext()).split())
        if not text:
            continue
        parts.append(f"{label}: {text}" if label else text)
    return html.unescape("\n".join(parts))


def save_raw(pmid: str, xml_text: str) -> tuple[Path, Path]:
    RAW_XML_DIR.mkdir(parents=True, exist_ok=True)
    RAW_ABSTRACT_DIR.mkdir(parents=True, exist_ok=True)
    xml_path = RAW_XML_DIR / f"PMID{pmid}.xml"
    abstract_path = RAW_ABSTRACT_DIR / f"PMID{pmid}.txt"
    if not xml_path.exists():
        xml_path.write_text(xml_text, encoding="utf-8")
    if not abstract_path.exists():
        abstract_path.write_text(abstract_from_xml(xml_text), encoding="utf-8")
    return xml_path, abstract_path


def fetch_and_store(pmid: str) -> tuple[Path, Path]:
    return save_raw(pmid, fetch_xml(pmid))


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and preserve raw PubMed XML and abstract text.")
    parser.add_argument("pmid")
    args = parser.parse_args()
    xml_path, abstract_path = fetch_and_store(args.pmid)
    print(f"XML: {xml_path}")
    print(f"Abstract: {abstract_path}")


if __name__ == "__main__":
    main()
