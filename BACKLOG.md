# Backlog

Known work that is not urgent. Newest at the top within each priority.

## To discuss and decide

- **Save the web sources each summary and fact-check is written from** (raised 2026-11-25).
  Today `agent/generate_summary.py` and `agent/check_myth.py` search the web, read up to
  five full pages, write the article and throw the pages away; only the PubMed pipeline
  keeps raw captures (`raw/pubmed/`). Saving them would let a revision reuse the same
  sources (no new search, the same facts) and let questions about an article be answered
  without going online. Proposed: write `raw/web/<article-file-name>.json` (search used,
  date, each page's title, URL and full text) and add `REUSE_SOURCES=1` to rerun from it.
  **Open question: where they live.** This repository is public and the pages are other
  people's work, so committing their full text would republish it, permanently, in git
  history. Options: local and gitignored (like `_drafts/requests/`; covers every run,
  since the generators only run on the founder's machine, but no backup), or a separate
  private GitHub repository (backed up, one more repository to manage).

## Low
