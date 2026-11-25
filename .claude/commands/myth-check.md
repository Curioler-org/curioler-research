Run the Curioler myth-checking pipeline for the statement: $ARGUMENTS

Steps:
1. cd to the repo root: `B:\Git Projects\Curioler-org\curioler-research`
2. Run: `MYTH_STATEMENT="<statement>" python agent/check_myth.py` (use Bash tool)
3. Show the saved file path, the verdict, and a preview of the frontmatter
4. Run: `git add docs/_myth_checks/ && git commit -m "myth-check: <statement>" && git push`
5. Report where it will publish: `https://www.curioler.com/knowledge/<slug>`, where `<slug>` is the file name without its date prefix and `.md`. The site imports from this repo every 30 minutes (on the hour and half hour, UTC) and refreshes the page as soon as it imports it.

The agent auto-detects the domain. No other inputs needed.
