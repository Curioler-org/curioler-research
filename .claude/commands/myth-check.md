Run the Curioler myth-checking pipeline for the statement: $ARGUMENTS

Steps:
1. cd to the repo root: `C:\Users\Bhavin\Desktop\Git Projects\Curioler-org\curioler-research`
2. Run: `MYTH_STATEMENT="<statement>" python agent/check_myth.py` (use Bash tool)
3. Show the saved file path, the verdict, and a preview of the frontmatter
4. Run: `git add docs/_myth_checks/ && git commit -m "myth-check: <statement>" && git push`
5. Report the GitHub Pages URL where it will publish

The agent auto-detects the domain. No other inputs needed.
