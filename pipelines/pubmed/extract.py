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

# Study designs ranked most to least specific. PubMed lists generic container types
# ("Journal Article", "Research Support…") alongside the real design, and often puts
# the generic one first, so the design has to be chosen by rank rather than by order.
# Matching on either the MeSH UI or the display string keeps this working when PubMed
# renames a term. Anything not on this list is not a study design: study_type stays
# null rather than falling back to a container type.
DESIGN_TYPE_RANK: list[tuple[str | None, str]] = [
    ("D016449", "Randomized Controlled Trial"),
    ("D000076362", "Adaptive Clinical Trial"),
    ("D065007", "Pragmatic Clinical Trial"),
    ("D017429", "Clinical Trial, Phase IV"),
    ("D017428", "Clinical Trial, Phase III"),
    ("D017427", "Clinical Trial, Phase II"),
    ("D017426", "Clinical Trial, Phase I"),
    ("D018848", "Controlled Clinical Trial"),
    ("D016430", "Clinical Trial"),
    ("D017418", "Meta-Analysis"),
    ("D000078182", "Systematic Review"),
    ("D064888", "Observational Study"),
    ("D002363", "Case Reports"),
]


# MeSH descriptors that name a condition co-occurring with autism, as opposed to the
# autism diagnosis itself or a study-population/method term. Matching is exact against
# the MeSH controlled vocabulary, so nothing here is inferred from free text.
CO_OCCURRING_MESH = {
    "Affective Symptoms",
    "Aggression",
    "Anxiety",
    "Anxiety Disorders",
    "Attention Deficit Disorder with Hyperactivity",
    "Bipolar Disorder",
    "Chromosome Disorders",
    "Communication Disorders",
    "Constipation",
    "Dental Caries",
    "Depression",
    "Depressive Disorder",
    "Developmental Disabilities",
    "Dysbiosis",
    "Epilepsy",
    "Feeding and Eating Disorders",
    "Fragile X Syndrome",
    "Gastrointestinal Diseases",
    "Intellectual Disability",
    "Language Development Disorders",
    "Major Depressive Disorder",
    "Motor Skills Disorders",
    "Obsessive-Compulsive Disorder",
    "Periodontal Diseases",
    "Psychotic Disorders",
    "Schizophrenia",
    "Seizures",
    "Self-Injurious Behavior",
    "Sleep Initiation and Maintenance Disorders",
    "Sleep Wake Disorders",
    "Stereotypic Movement Disorder",
    "Substance-Related Disorders",
    "Tic Disorders",
    "Tourette Syndrome",
}


def co_occurring_conditions(mesh_terms: list[str]) -> list[str]:
    seen: list[str] = []
    for term in mesh_terms:
        if term in CO_OCCURRING_MESH and term not in seen:
            seen.append(term)
    return seen


def text_or_none(node: ET.Element | None) -> str | None:
    if node is None:
        return None
    text = " ".join("".join(node.itertext()).split())
    return text or None


def article_doi(root: ET.Element) -> str | None:
    """Return the article's own DOI.

    Never use a `.//ArticleId` sweep here: `PubmedData/ReferenceList` carries an
    `<ArticleId IdType="doi">` for every cited reference, so a descendant search
    picks up the bibliography's DOIs alongside the article's own.
    """
    for node in root.findall(".//Article/ELocationID"):
        if node.attrib.get("EIdType") == "doi" and node.attrib.get("ValidYN", "Y") != "N":
            doi = text_or_none(node)
            if doi:
                return doi
    for node in root.findall(".//PubmedData/ArticleIdList/ArticleId"):
        if node.attrib.get("IdType") == "doi":
            doi = text_or_none(node)
            if doi:
                return doi
    return None


def study_design(publication_types: list[tuple[str | None, str]]) -> str | None:
    """Pick the most specific study design from the article's publication types."""
    uis = {ui for ui, _ in publication_types if ui}
    labels = {label.casefold() for _, label in publication_types}
    for ui, label in DESIGN_TYPE_RANK:
        if (ui and ui in uis) or label.casefold() in labels:
            return label
    return None


def metadata_from_xml(pmid: str, xml_text: str) -> dict:
    root = ET.fromstring(xml_text)
    article = root.find(".//Article")
    journal = text_or_none(root.find(".//Journal/Title"))
    year_text = text_or_none(root.find(".//PubDate/Year")) or text_or_none(root.find(".//ArticleDate/Year"))
    doi = article_doi(root)
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
    publication_types = [
        (node.attrib.get("UI"), label)
        for node, label in (
            (node, text_or_none(node)) for node in root.findall(".//Article/PublicationTypeList/PublicationType")
        )
        if label
    ]
    return {
        "pmid": pmid,
        "doi": doi,
        "title": text_or_none(article.find("ArticleTitle")) if article is not None else None,
        "year": int(year_text) if year_text and year_text.isdigit() else None,
        "journal": journal,
        "authors": authors,
        "study_type": study_design(publication_types),
        "co_occurring_conditions": co_occurring_conditions(mesh_terms),
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
            "age_min",
            "age_max",
            "age_unit",
            "diagnosis",
            "co_occurring_conditions",
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
