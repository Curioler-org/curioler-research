from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET

from pipelines.pubmed.common import RAW_ABSTRACT_DIR, RAW_XML_DIR, load_config, normalize_study, utc_now
from pipelines.pubmed.llm import LLMClient, LLMConfig

SYSTEM_PROMPT = """You extract structured biomedical evidence for Curioler.
Use only the PubMed metadata, XML, and abstract supplied by the user.
Return valid JSON only. Never invent missing information. Use null for unknown scalar values and [] for unknown list values."""


def text_or_none(node: ET.Element | None) -> str | None:
    if node is None:
        return None
    text = " ".join("".join(node.itertext()).split())
    return text or None


def metadata_from_xml(pmid: str, xml_text: str) -> dict:
    root = ET.fromstring(xml_text)
    article = root.find(".//Article")
    journal = text_or_none(root.find(".//Journal/Title"))
    year_text = text_or_none(root.find(".//PubDate/Year")) or text_or_none(root.find(".//ArticleDate/Year"))
    doi = None
    for node in root.findall(".//ArticleId"):
        if node.attrib.get("IdType") == "doi":
            doi = text_or_none(node)
    authors = []
    for author in root.findall(".//Author"):
        last = text_or_none(author.find("LastName"))
        fore = text_or_none(author.find("ForeName"))
        collective = text_or_none(author.find("CollectiveName"))
        name = collective or " ".join(part for part in [fore, last] if part)
        if name:
            authors.append(name)
    mesh_terms = [term for term in (text_or_none(node) for node in root.findall(".//MeshHeading/DescriptorName")) if term]
    keywords = [term for term in (text_or_none(node) for node in root.findall(".//Keyword")) if term]
    publication_types = [term for term in (text_or_none(node) for node in root.findall(".//PublicationType")) if term]
    return {
        "pmid": pmid,
        "doi": doi,
        "title": text_or_none(article.find("ArticleTitle")) if article is not None else None,
        "year": int(year_text) if year_text and year_text.isdigit() else None,
        "journal": journal,
        "authors": authors,
        "study_type": publication_types[0] if publication_types else None,
        "mesh_terms": mesh_terms,
        "keywords": keywords,
        "source_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    }


def strip_code_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    return re.sub(r"\s*```$", "", text)


def extract_study(pmid: str) -> dict:
    config = load_config()
    xml_text = (RAW_XML_DIR / f"PMID{pmid}.xml").read_text(encoding="utf-8")
    abstract = (RAW_ABSTRACT_DIR / f"PMID{pmid}.txt").read_text(encoding="utf-8")
    metadata = metadata_from_xml(pmid, xml_text)
    prompt = {
        "required_schema_fields": [
            "pmid",
            "doi",
            "title",
            "year",
            "journal",
            "authors",
            "study_type",
            "participants",
            "age_range",
            "diagnosis",
            "intervention",
            "duration",
            "primary_outcomes",
            "secondary_outcomes",
            "limitations",
            "clinical_implications",
            "abstract",
            "conclusion",
            "mesh_terms",
            "keywords",
            "source_url",
            "extraction_confidence",
            "created_at",
            "last_updated",
        ],
        "known_metadata": metadata,
        "abstract": abstract,
        "instructions": "Preserve known_metadata exactly unless the XML clearly contradicts it. Use null for unknown scalar values.",
    }
    client = LLMClient(LLMConfig(provider=config["ai_provider"], model=config.get("ai_model", "")))
    extracted = client.complete_json(SYSTEM_PROMPT, json.dumps(prompt, ensure_ascii=False))
    now = utc_now()
    merged = {**metadata, **extracted, "created_at": extracted.get("created_at") or now, "last_updated": now}
    merged["abstract"] = merged.get("abstract") or abstract or None
    return normalize_study(merged)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract one PubMed study into Curioler JSON.")
    parser.add_argument("pmid")
    args = parser.parse_args()
    print(json.dumps(extract_study(args.pmid), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
