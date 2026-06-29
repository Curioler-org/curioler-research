# /research — Curioler Research Summariser

Generate a structured two-tier research summary from Tavily search results and publish it to the Jekyll site. Uses Claude Code's built-in model — no separate Anthropic API billing.

## Usage

```
/research <topic> [domain]
```

Examples:
- `/research echolalia in autism`
- `/research sensory processing disorder interventions Sensory`
- `/research clinical trials melatonin autism sleep Communication`

## What it does

1. Searches the web via Tavily (5 sources, full raw content, no truncation)
2. Detects content type (clinical trial, research paper, systematic review, guideline, commentary)
3. Extracts structured fields: sample size, demographics, researchers, institutes, methodology, key outcome, limitations
4. Generates a short summary (card excerpt) + full structured breakdown (detail page)
5. Links related topics from existing summaries automatically
6. Saves to `docs/_summaries/YYYY-MM-DD-<slug>.md`
7. Commits and pushes → GitHub Pages auto-publishes

## Steps to run

From the repo root (`curioler-research/`):

```bash
cd "C:\Users\Bhavin\Desktop\Git Projects\Curioler-org\curioler-research"

# Only Tavily key needed — Claude runs via Claude Code subscription
export TAVILY_API_KEY=your_tavily_key

# Run
SEARCH_QUERY="melatonin autism sleep clinical trial" SEARCH_DOMAIN="Behaviour" python agent/generate_summary.py

# Commit and push
git add docs/_summaries/
git commit -m "research: add summary for <topic>"
git push
```

## Domain options

Communication, Social, Sensory, Behaviour, Adaptive, Motor, General

## Notes

- No `ANTHROPIC_API_KEY` needed — uses `claude` CLI via your Claude Code subscription
- Tavily free tier: 1,000 searches/month
- Full raw content passed to Claude — richer extraction than the truncated version
