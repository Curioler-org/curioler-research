# /research — Curioler Research Summariser

Generate a structured two-tier research summary from Tavily search results and save it to the Jekyll site.

## Usage

```
/research <topic> [domain]
```

Examples:
- `/research echolalia in autism`
- `/research sensory processing disorder interventions Sensory`
- `/research clinical trials melatonin autism sleep Communication`

## What it does

1. Searches the web via Tavily (5 sources, full raw content)
2. Detects content type (clinical trial, research paper, systematic review, guideline, commentary)
3. Extracts structured fields: sample size, demographics, researchers, institutes, methodology, key outcome, limitations
4. Generates a short summary (card) + full structured breakdown (detail page)
5. Finds related topics from existing summaries
6. Saves to `docs/_summaries/YYYY-MM-DD-<slug>.md`
7. Commits and pushes → GitHub Pages auto-publishes

## Steps to run

Run these commands in order from the repo root (`curioler-research/`):

```bash
cd "C:\Users\Bhavin\Desktop\Git Projects\Curioler-org\curioler-research"

# Set your keys (skip if already in environment)
export TAVILY_API_KEY=your_key_here
export ANTHROPIC_API_KEY=your_key_here

# Run with your topic
SEARCH_QUERY="<topic>" SEARCH_DOMAIN="<domain>" python agent/generate_summary.py

# Commit and push
git add docs/_summaries/
git commit -m "research: add summary for <topic>"
git push
```

## Domain options

Communication, Social, Sensory, Behaviour, Adaptive, Motor, General

## Notes

- The `ANTHROPIC_API_KEY` here uses your own key. To use Claude Code subscription instead, run this skill directly from Claude Code and ask Claude to call the Anthropic API on your behalf using the built-in model access.
- Tavily free tier: 1,000 searches/month — sufficient for regular use.
- No token truncation — full raw content is passed for richer extraction.
