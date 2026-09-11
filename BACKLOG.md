# Backlog

Known work that is not urgent. Newest at the top within each priority.

## Low

### Store the Tavily API key somewhere permanent

`agent/generate_summary.py` and `agent/check_myth.py` both read `TAVILY_API_KEY`
from the environment and fail immediately if it is missing. There is no `.env`,
no `.env.example`, and nothing in the README that says where the key should
live, so a local run of either pipeline fails until someone digs the key out by
hand.

Options worth considering:

- A gitignored `.env` at the repo root, loaded via `python-dotenv`.
- A documented "set this in your shell profile" line in the README.
- Keep the CI path as-is — `.github/workflows/generate-summary.yml` already
  reads `secrets.TAVILY_API_KEY` — and only fix the local story.

Whatever is chosen, `.gitignore` currently has no `.env` entry; add one before
introducing a dotenv file.
