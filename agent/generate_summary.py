from __future__ import annotations

import os
import re
import json
import shutil
import glob
import subprocess
from datetime import date

from tavily import TavilyClient

from dedupe import drop_repeats
from pipeline_secrets import require_tavily_key


SYSTEM_PROMPT = """You are a research summarisation agent for Curioler, a platform that helps caregivers of autistic children understand research.

Rules:
- Write in plain, warm language for a parent, not a clinician
- Never make diagnostic statements or give prescriptive clinical advice
- Be honest about what the research does NOT say
- Trust tier: assign based on the STRONGEST evidence type actually described
  in the sources, never a default and never based on how compelling the
  finding sounds.
  - Tier 1: Systematic review or meta-analysis
  - Tier 2: Peer-reviewed study, smaller RCT, clinical trial
  - Tier 3: Clinical consensus or professional guideline
  - Tier 4: Expert commentary or opinion, not peer-reviewed
- If multiple sources are provided, base the summary on the strongest evidence
- Output ONLY valid JSON, no preamble, no markdown fences
"""

EXTRACTION_PROMPT = """Analyse the research sources provided and return a JSON object with this exact structure.
Detect the content_type first — it determines which structured_fields to populate.

content_type options: "clinical_trial" | "research_paper" | "systematic_review" | "guideline" | "commentary"

Return ONLY this JSON (no markdown, no explanation):

{
  "title": "Clear, plain-language title",
  "content_type": "one of the options above",
  "trust_tier": 1,
  "trust_tier_label": "Systematic review or meta-analysis",
  "domain": "Communication",
  "what": "1-2 plain sentences: what this research is actually about -- the concept, finding, or mechanism, not just the topic searched.",
  "why": "1-2 plain sentences: why this matters to a caregiver -- the practical relevance to their child.",
  "when": "1-2 plain sentences: the journey stage, situation, or trigger that makes this relevant to a caregiver right now.",
  "short_summary": "2-3 sentence plain-language summary for the card on the listing page. What did they study and what did they find?",
  "structured_fields": {
    "sample_size": "e.g. 1,243 participants — or null if not applicable",
    "demographics": "e.g. Adults 40–70, 62% female, multi-ethnic — or null",
    "researchers": ["Name 1", "Name 2"],
    "institutes": ["Institute 1", "Institute 2"],
    "methodology": "1 sentence: study design, who was studied, and source quality",
    "key_outcome": "The single most important finding, with statistic if available"
  },
  "sections": {
    "what_they_found": ["2-4 bullets"],
    "what_this_means": ["2-3 bullets"],
    "important_caveats": ["2-4 bullets: the study's limitations and the limits of what it can tell a caregiver, together in one list"]
  },
  "sources": [
    {
      "title": "Source title",
      "citation": "Author(s), Year, Journal",
      "url": "https://..."
    }
  ],
  "tags": ["autism", "relevant-tag-2"]
}

For non-clinical-trial types, set sample_size/demographics/researchers/institutes to null where not applicable.
Always populate methodology and key_outcome if possible.

Keep it short. A caregiver reads short_summary first, then the sections, so:
- Say each fact once. key_outcome and short_summary already state the headline
  finding; what_they_found must add findings beyond it, not restate it.
- what_this_means gives practical implications, not the findings reworded.
- The bullet counts are ranges, not targets. If the sources support two
  distinct points, write two. Never pad to reach a count.
- One sentence per bullet, at most 25 words.
- Name the population actually studied. If a source studied adults or
  non-autistic children, say so; never present it as a finding about
  autistic children.
"""


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:60]


def search_web(query: str) -> list[dict]:
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    response = client.search(
        query=query[:400],
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


def claude_cli() -> str:
    """Resolve the Claude CLI. On Windows the launcher is claude.cmd, which
    CreateProcess will not find from the bare name."""
    return os.environ.get("CLAUDE_CLI") or shutil.which("claude") or "claude"


AUTH_HELP = """The Claude CLI is not authenticated, so the extraction step cannot run.

Fix it once, in an interactive terminal (not through this script):

    claude setup-token          # long-lived token, needs a Claude subscription

then store the token it prints on Railway, next to the Tavily key, so every
run picks it up with no setx:

    railway variable set CLAUDE_CODE_OAUTH_TOKEN --stdin --skip-deploys \\
        -p 57be53e0-bf1b-48cb-b0b3-d15a223e91bf -e production -s curioler-research-secrets

or, for a browser sign-in stored in ~/.claude/.credentials.json:

    claude auth login

Either way, open a NEW terminal afterwards and confirm with:

    claude auth status

Being signed in to the Claude desktop app is not enough -- the standalone CLI
keeps its own credentials, and this script shells out to the CLI.
"""


def preflight() -> None:
    """Fail fast, with an actionable message, before spending a Tavily search
    on a run that cannot finish. The CLI reports 'Not logged in' on stdout with
    a nonzero exit and an empty stderr, which is otherwise a silent failure."""
    require_tavily_key()  # also pulls a stored Claude token from Railway

    if os.environ.get("ANTHROPIC_API_KEY"):
        return  # the CLI will use the API key and never touch OAuth

    try:
        result = subprocess.run(
            [claude_cli(), "auth", "status"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"Could not run the Claude CLI ({exc}).\n\n{AUTH_HELP}")

    try:
        logged_in = json.loads(result.stdout).get("loggedIn", False)
    except (ValueError, AttributeError):
        logged_in = False

    if not logged_in:
        raise SystemExit(AUTH_HELP)


def extract_structured_data(query: str, domain: str, sources_text: str) -> dict:
    today = date.today().isoformat()

    # Combine system prompt + extraction instructions + sources into one prompt
    # so we can drive Claude via the Claude Code CLI (no separate API key needed)
    full_prompt = f"""{SYSTEM_PROMPT}

Topic: "{query}"
Domain: {domain}
Date: {today}

{EXTRACTION_PROMPT}

Sources:
{sources_text}
"""

    # The prompt carries whole source pages, so it is passed on stdin: Windows
    # caps a command line at 32k and CreateProcess refuses anything longer.
    result = subprocess.run(
        [claude_cli(), "-p", "--model", "claude-haiku-4-5-20251001"],
        input=full_prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    if result.returncode != 0:
        # The CLI puts 'Not logged in' and most other diagnostics on stdout,
        # so reporting stderr alone leaves the caller with a blank error.
        detail = (result.stderr or "").strip() or (result.stdout or "").strip()
        raise RuntimeError(f"Claude CLI error (exit {result.returncode}):\n{detail}")

    raw = result.stdout.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def find_related_summaries(query: str, current_slug: str, max_related: int = 3) -> list[dict]:
    """Find related summaries by matching tags and topic words against existing files."""
    summaries_dir = os.path.join("docs", "_summaries")
    if not os.path.isdir(summaries_dir):
        return []

    query_words = set(re.findall(r"\w+", query.lower())) - {"the", "a", "an", "and", "or", "of", "in", "for", "to", "is", "are"}
    related = []

    for filepath in glob.glob(os.path.join(summaries_dir, "*.md")):
        slug = os.path.basename(filepath).replace(".md", "")
        if slug == current_slug:
            continue
        with open(filepath, encoding="utf-8") as f:
            content = f.read()

        # Extract frontmatter fields
        title_match = re.search(r'^title:\s*"?(.+?)"?\s*$', content, re.MULTILINE)
        topic_match = re.search(r'^search_topic:\s*"?(.+?)"?\s*$', content, re.MULTILINE)
        date_match = re.search(r'^summary_date:\s*"?(.+?)"?\s*$', content, re.MULTILINE)
        domain_match = re.search(r'^domain:\s*"?(.+?)"?\s*$', content, re.MULTILINE)
        short_match = re.search(r'^short_summary:\s*"?(.+?)"?\s*$', content, re.MULTILINE)

        if not title_match:
            continue

        file_text = f"{title_match.group(1)} {topic_match.group(1) if topic_match else ''}".lower()
        file_words = set(re.findall(r"\w+", file_text))
        overlap = len(query_words & file_words)

        if overlap >= 1:
            related.append({
                "title": title_match.group(1),
                "slug": slug,
                "date": date_match.group(1) if date_match else "",
                "domain": domain_match.group(1) if domain_match else "",
                "short_summary": short_match.group(1) if short_match else "",
                "overlap": overlap,
            })

    related.sort(key=lambda x: x["overlap"], reverse=True)
    return related[:max_related]


def render_markdown(data: dict, query: str, slug: str, today: str) -> str:
    sf = data.get("structured_fields", {})
    sources = data.get("sources", [])
    sections = data.get("sections", {})
    related = find_related_summaries(query, f"{today}-{slug}")

    # --- Frontmatter ---
    short_summary_escaped = data.get("short_summary", "").replace('"', '\\"')
    what_escaped = data.get("what", "").replace('"', '\\"')
    why_escaped = data.get("why", "").replace('"', '\\"')
    when_escaped = data.get("when", "").replace('"', '\\"')
    lines = [
        "---",
        f'title: "{data["title"]}"',
        f'content_type: "{data["content_type"]}"',
        f'trust_tier: {data["trust_tier"]}',
        f'trust_tier_label: "{data["trust_tier_label"]}"',
        f'domain: "{data["domain"]}"',
        # The platform's Three Questions invariant (Knowledge-Architecture.md)
        # -- prepared here, at generation time, rather than left for the
        # ingestion pipeline to guess or leave blank.
        f'what: "{what_escaped}"',
        f'why: "{why_escaped}"',
        f'when: "{when_escaped}"',
        f'search_topic: "{query}"',
        f'summary_date: "{today}"',
        f'short_summary: "{short_summary_escaped}"',
        "status: published",
        f'tags: [{", ".join(data.get("tags", ["autism"]))}]',
        "---",
        "",
    ]

    # --- Structured fields block ---
    lines += [
        "## At a glance",
        "",
    ]

    if sf.get("sample_size"):
        lines.append(f"**Sample size:** {sf['sample_size']}  ")
    if sf.get("demographics"):
        lines.append(f"**Demographics:** {sf['demographics']}  ")
    if sf.get("key_outcome"):
        lines.append(f"**Key outcome:** {sf['key_outcome']}  ")
    if sf.get("methodology"):
        lines.append(f"**Methodology:** {sf['methodology']}  ")
    if sf.get("researchers"):
        lines.append(f"**Researchers:** {', '.join(sf['researchers'])}  ")
    if sf.get("institutes"):
        lines.append(f"**Institutes:** {', '.join(sf['institutes'])}  ")

    lines.append("")

    # --- Main sections ---
    # The page header already shows short_summary and At a glance shows the
    # key outcome, so both seed the "already said" set.
    said = [data.get("short_summary", ""), sf.get("key_outcome") or ""]
    # Older extractions kept study limitations apart from caveats; they are one
    # list now.
    caveats = (sf.get("limitations") or []) + (sections.get("important_caveats") or [])
    for heading, bullets in (
        ("What this research found", sections.get("what_they_found")),
        ("What this means for caregivers", sections.get("what_this_means")),
        ("Important caveats", caveats),
    ):
        kept = drop_repeats(bullets or [], said)
        if kept:
            lines += [f"## {heading}", ""] + [f"- {b}" for b in kept] + [""]

    # --- Sources ---
    if sources:
        lines += ["## Sources", ""]
        for s in sources:
            citation = s.get("citation", "")
            url = s.get("url", "")
            title = s.get("title", citation or url)
            if url:
                lines.append(f"- [{title}]({url}){(' — ' + citation) if citation else ''}")
            else:
                lines.append(f"- {title}{(' — ' + citation) if citation else ''}")
        lines.append("")

    # --- Related topics ---
    if related:
        lines += ["## Related topics", ""]
        for r in related:
            url_slug = r["slug"]
            lines.append(f"- [{r['title']}](/curioler-research/summaries/{url_slug}/) — {r['domain']}")
        lines.append("")

    # The disclaimer is not written here: the summary layout's footer carries it.
    return "\n".join(lines).rstrip() + "\n"


def save_summary(content: str, query: str) -> str:
    today = date.today().isoformat()
    slug = slugify(query)
    filename = f"{today}-{slug}.md"
    path = os.path.join("docs", "_summaries", filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    domain_match = re.search(r'^domain:\s*"?([^"\r\n]+)"?', content, re.MULTILINE)
    domain = domain_match.group(1).strip().lower() if domain_match else "general"
    domain = {
        "communication": "communication",
        "sensory": "sensory",
        "social": "social",
        "adaptive": "adaptive",
        "behaviour": "behavior",
        "behavior": "behavior",
        "motor": "motor",
        "general": "general",
        "statistics": "statistics",
    }.get(domain, "general")
    topic_path = os.path.join("topics", domain, filename)
    os.makedirs(os.path.dirname(topic_path), exist_ok=True)
    with open(topic_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Saved: {path}")
    return path


def main():
    query = os.environ.get("SEARCH_QUERY", "").strip()
    domain = os.environ.get("SEARCH_DOMAIN", "General").strip()

    if not query:
        raise SystemExit("Error: SEARCH_QUERY env var is required")

    preflight()

    print(f"Searching: {query}")
    results = search_web(query)
    print(f"Found {len(results)} sources")

    sources_text = build_sources_text(results)

    print("Extracting structured data with Claude...")
    data = extract_structured_data(query, domain, sources_text)

    today = date.today().isoformat()
    slug = slugify(query)
    markdown = render_markdown(data, query, slug, today)

    path = save_summary(markdown, query)
    print(f"Done — {path}")


if __name__ == "__main__":
    main()
