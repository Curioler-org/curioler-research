from __future__ import annotations

import os
import re
import json
import glob
import subprocess
from datetime import date

from tavily import TavilyClient


SYSTEM_PROMPT = """You are a myth-checking agent for Curioler, a platform that helps caregivers of autistic children understand research.

Rules:
- Check the statement against available peer-reviewed evidence
- Be honest: if evidence is mixed, say so clearly
- Never make diagnostic statements or give prescriptive clinical advice
- Plain, warm language — for a parent, not a clinician
- Verdict options (choose exactly one):
    myth               — clearly contradicted by strong evidence
    supported          — well-supported by strong evidence
    nuanced            — partially true or depends heavily on context
    misleading         — contains truth but leads to wrong conclusions
    insufficient-evidence — not enough quality research to say either way
- Output ONLY valid JSON, no preamble, no markdown fences
"""

EXTRACTION_PROMPT = """Analyse the statement and sources provided. Return a JSON object with this exact structure:

{
  "statement": "The exact statement being checked",
  "verdict": "myth | supported | nuanced | misleading | insufficient-evidence",
  "verdict_label": "This is a myth | This is supported | This is nuanced | This is misleading | Insufficient evidence",
  "domain": "Communication | Social | Sensory | Behaviour | Adaptive | Motor | General",
  "short_summary": "2-3 sentence plain-language summary of the verdict for the card listing.",
  "sections": {
    "the_claim": "1-2 sentences restating what people believe and why it persists.",
    "what_evidence_says": ["finding 1", "finding 2", "finding 3", "finding 4"],
    "the_verdict_explained": "2-3 paragraphs explaining the verdict in full, honestly acknowledging what we know and don't know.",
    "what_this_means": ["practical implication 1", "practical implication 2", "practical implication 3"],
    "important_caveats": ["caveat 1", "caveat 2"]
  },
  "sources": [
    {
      "title": "Source title",
      "citation": "Author(s), Year, Journal",
      "url": "https://..."
    }
  ],
  "tags": ["autism", "relevant-tag"]
}

Domain guide:
- Communication: language, speech, AAC, echolalia
- Social: joint attention, friendship, social skills
- Sensory: overload, sensitivity, meltdown
- Behaviour: challenging behaviour, stimming, routines
- Adaptive: daily living, self-care, independence
- Motor: coordination, fine/gross motor
- General: spans multiple domains or doesn't fit above
"""


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:60]


def search_web(statement: str) -> list[dict]:
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    response = client.search(
        query=f"autism research evidence {statement}"[:400],
        search_depth="advanced",
        max_results=5,
        include_raw_content=True,
    )
    return response.get("results", [])


def build_sources_text(results: list[dict]) -> str:
    text = ""
    for i, r in enumerate(results, 1):
        raw = r.get("raw_content") or r.get("content", "")
        text += f"\n\n### Source {i}: {r.get('title', 'Untitled')}\n"
        text += f"URL: {r.get('url', '')}\n"
        text += f"Content:\n{raw}\n"
    return text


def extract_structured_data(statement: str, sources_text: str) -> dict:
    today = date.today().isoformat()
    full_prompt = f"""{SYSTEM_PROMPT}

Statement to check: "{statement}"
Date: {today}

{EXTRACTION_PROMPT}

Sources:
{sources_text}
"""
    result = subprocess.run(
        ["claude", "-p", full_prompt, "--model", "claude-haiku-4-5-20251001"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI error:\n{result.stderr}")

    raw = result.stdout.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def find_related(statement: str, current_slug: str, max_related: int = 3) -> list[dict]:
    query_words = set(re.findall(r"\w+", statement.lower())) - {
        "the", "a", "an", "and", "or", "of", "in", "for", "to", "is", "are",
        "do", "does", "can", "will", "not", "it", "be", "has", "have",
    }
    related = []

    for collection_dir in ["docs/_summaries", "docs/_myth_checks"]:
        if not os.path.isdir(collection_dir):
            continue
        for filepath in glob.glob(os.path.join(collection_dir, "*.md")):
            slug = os.path.basename(filepath).replace(".md", "")
            if slug == current_slug:
                continue
            with open(filepath, encoding="utf-8") as f:
                content = f.read()

            title_match = re.search(r'^title:\s*"?(.+?)"?\s*$', content, re.MULTILINE)
            statement_match = re.search(r'^statement:\s*"?(.+?)"?\s*$', content, re.MULTILINE)
            domain_match = re.search(r'^domain:\s*"?(.+?)"?\s*$', content, re.MULTILINE)
            date_match = re.search(r'^(?:summary_date|check_date):\s*"?(.+?)"?\s*$', content, re.MULTILINE)

            display_title = (title_match or statement_match)
            if not display_title:
                continue

            file_text = display_title.group(1).lower()
            file_words = set(re.findall(r"\w+", file_text))
            overlap = len(query_words & file_words)

            # Determine URL prefix
            is_myth = "_myth_checks" in collection_dir
            url_prefix = "/curioler-research/myth-check/" if is_myth else "/curioler-research/summaries/"

            if overlap >= 1:
                related.append({
                    "title": display_title.group(1),
                    "slug": slug,
                    "url": f"{url_prefix}{slug}/",
                    "domain": domain_match.group(1) if domain_match else "",
                    "overlap": overlap,
                    "type": "Myth Check" if is_myth else "Summary",
                })

    related.sort(key=lambda x: x["overlap"], reverse=True)
    return related[:max_related]


def render_markdown(data: dict, statement: str, slug: str, today: str) -> str:
    sections = data.get("sections", {})
    sources = data.get("sources", [])
    related = find_related(statement, f"{today}-{slug}")

    short_summary_escaped = data.get("short_summary", "").replace('"', '\\"')
    statement_escaped = data.get("statement", statement).replace('"', '\\"')

    lines = [
        "---",
        f'title: "{statement_escaped}"',
        f'statement: "{statement_escaped}"',
        f'verdict: "{data["verdict"]}"',
        f'verdict_label: "{data["verdict_label"]}"',
        f'domain: "{data["domain"]}"',
        f'check_date: "{today}"',
        f'short_summary: "{short_summary_escaped}"',
        "status: published",
        f'tags: [{", ".join(data.get("tags", ["autism"]))}]',
        "---",
        "",
    ]

    if sections.get("the_claim"):
        lines += ["## The claim", "", sections["the_claim"], ""]

    if sections.get("what_evidence_says"):
        lines += ["## What the evidence says", ""]
        for item in sections["what_evidence_says"]:
            lines.append(f"- {item}")
        lines.append("")

    if sections.get("the_verdict_explained"):
        lines += ["## The verdict explained", "", sections["the_verdict_explained"], ""]

    if sections.get("what_this_means"):
        lines += ["## What this means for caregivers", ""]
        for item in sections["what_this_means"]:
            lines.append(f"- {item}")
        lines.append("")

    if sections.get("important_caveats"):
        lines += ["## Important caveats", ""]
        for item in sections["important_caveats"]:
            lines.append(f"- {item}")
        lines.append("")

    if sources:
        lines += ["## Sources", ""]
        for s in sources:
            title = s.get("title", "")
            citation = s.get("citation", "")
            url = s.get("url", "")
            if url:
                lines.append(f"- [{title}]({url}){(' — ' + citation) if citation else ''}")
            else:
                lines.append(f"- {title}{(' — ' + citation) if citation else ''}")
        lines.append("")

    if related:
        lines += ["## Related topics", ""]
        for r in related:
            lines.append(f"- [{r['title']}]({r['url']}) — {r['domain']} ({r['type']})")
        lines.append("")

    return "\n".join(lines)


def save_check(content: str, statement: str) -> str:
    today = date.today().isoformat()
    slug = slugify(statement)
    filename = f"{today}-{slug}.md"
    path = os.path.join("docs", "_myth_checks", filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    mirror_path = os.path.join("factchecks", filename)
    os.makedirs(os.path.dirname(mirror_path), exist_ok=True)
    with open(mirror_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Saved: {path}")
    return path


def main():
    statement = os.environ.get("MYTH_STATEMENT", "").strip()
    if not statement:
        raise SystemExit("Error: MYTH_STATEMENT env var is required")

    print(f"Checking: {statement}")
    results = search_web(statement)
    print(f"Found {len(results)} sources")

    sources_text = build_sources_text(results)

    print("Analysing with Claude...")
    data = extract_structured_data(statement, sources_text)

    today = date.today().isoformat()
    slug = slugify(statement)
    markdown = render_markdown(data, statement, slug, today)
    save_check(markdown, statement)
    print(f"Verdict: {data['verdict_label']}")


if __name__ == "__main__":
    main()
