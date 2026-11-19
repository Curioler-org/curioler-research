Run the Curioler myth-checking pipeline for the statement: $ARGUMENTS

Steps:
1. cd to the repo root: `B:\Git Projects\Curioler-org\curioler-research`
2. Run: `MYTH_STATEMENT="<statement>" python agent/check_myth.py` (use Bash tool)
3. Show the saved file path, the verdict, and a preview of the frontmatter
4. Run: `git add docs/_myth_checks/ factchecks/ && git commit -m "myth-check: <statement>" && git push`
5. Report where it will publish: `https://www.curioler.com/knowledge/<slug>`, where `<slug>` is the file name without its date prefix and `.md`. The site imports from this repo every 30 minutes, and a page can take up to another hour to refresh.

The agent auto-detects the domain. No other inputs needed.
