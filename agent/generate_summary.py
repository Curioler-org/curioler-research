import argparse
import os
import re
from datetime import date

import anthropic
from tavily import TavilyClient


SYSTEM_PROMPT = """You are a research summarisation agent for Curioler, a platform that helps caregivers of autistic children understand research.

Rules:
- Write in plain, warm language for a parent, not a clinician
- Never make diagnostic statements or give prescriptive clinical advice
- Be honest about what the research does NOT say
- Trust tier guide:
  - Tier 1: Systematic review or meta-analysis
  - Tier 2: Peer-reviewed study
  - Tier 3: Clinical consensus or guideline
  - Tier 4: Expert commentary or opinion
- If multiple sources are provided, base the summary on the strongest evidence
- Output ONLY the markdown document, no preamble or explanation
"""

SUMMARY_TEMPLATE = """---
title: "{title}"
source_citation: "{source_citation}"
source_url: "{source_url}"
trust_tier: {trust_tier}
trust_tier_label: "{trust_tier_label}"
domain: "{domain}"
search_topic: "{query}"
summary_date: "{summary_date}"
status: draft
tags: [autism]
---

# {title}

**Source:** {source_citation}
**Evidence level:** Tier {trust_tier} — {trust_tier_label}
**Domain:** {domain}

## What this research found
[3-5 bullet points in plain language]

## What this means for caregivers of autistic children
[2-4 warm, practical implications]

## Important caveats
[2-3 limitations and when to consult a professional]

## About this research
[2-3 sentences on methodology]

## Read the original
{source_url}

---
*This summary was prepared by the Curioler research agent. It is not medical advice. Always consult a qualified professional before making decisions about your child's care.*
"""


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:60]


def search_web(query: str) -> list[dict]:
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    response = client.search(
        query=query,
        search_depth="advanced",
        max_results=5,
        include_raw_content=True,
    )
    return response.get("results", [])


def build_user_prompt(query: str, domain: str, results: list[dict]) -> str:
    sources_text = ""
    for i, r in enumerate(results, 1):
        sources_text += f"\n\n### Source {i}: {r.get('title', 'Untitled')}\n"
        sources_text += f"URL: {r.get('url', '')}\n"
        sources_text += f"Content:\n{r.get('raw_content') or r.get('content', '')}\n"

    today = date.today().isoformat()

    return f"""Summarise the following research on the topic: "{query}"
Domain: {domain}
Date: {today}

Produce a structured markdown summary using EXACTLY this format (fill in all placeholders):

{SUMMARY_TEMPLATE}

Sources to summarise:
{sources_text}
"""


def generate_summary(query: str, domain: str, results: list[dict]) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(query, domain, results)}],
    )
    return message.content[0].text


def save_draft(content: str, query: str) -> str:
    today = date.today().isoformat()
    slug = slugify(query)
    filename = f"{today}-{slug}.md"
    path = os.path.join("docs", "_summaries", filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Saved: {path}")
    return path


def main():
    parser = argparse.ArgumentParser(description="Curioler research summary agent")
    parser.add_argument("--query", required=True, help="Search topic")
    parser.add_argument("--domain", required=True, help="Research domain")
    args = parser.parse_args()

    print(f"Searching: {args.query}")
    results = search_web(args.query)
    print(f"Found {len(results)} sources")

    print("Generating summary with Claude...")
    summary = generate_summary(args.query, args.domain, results)

    save_draft(summary, args.query)


if __name__ == "__main__":
    main()
