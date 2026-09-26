"""Resolve the pipeline's secrets without anyone having to setx them.

Order, per variable: the process environment first (so CI and one-off
overrides still win), then the `curioler-research-secrets` service on
Railway, read through the Railway CLI's own login. The Railway service is
never deployed; it exists only to hold these values.

Nothing here prints a secret value.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

RAILWAY_PROJECT = os.environ.get("CURIOLER_RAILWAY_PROJECT", "57be53e0-bf1b-48cb-b0b3-d15a223e91bf")
RAILWAY_ENVIRONMENT = os.environ.get("CURIOLER_RAILWAY_ENVIRONMENT", "production")
RAILWAY_SERVICE = os.environ.get("CURIOLER_RAILWAY_SERVICE", "curioler-research-secrets")

# TAVILY_API_KEY feeds the search step. The other two authenticate the Claude
# CLI for the extraction step; either one is enough.
SECRET_NAMES = ("TAVILY_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY")

SET_HELP = f"""Store it once on Railway and every run picks it up:

    railway variable set TAVILY_API_KEY --stdin --skip-deploys \\
        -p {RAILWAY_PROJECT} -e {RAILWAY_ENVIRONMENT} -s {RAILWAY_SERVICE}

(paste the key, then Enter and Ctrl+Z/Ctrl+D), or add it in the Railway
dashboard under brave-flexibility > {RAILWAY_SERVICE} > Variables.
"""


def _railway_variables() -> tuple[dict, str | None]:
    """Return (variables, problem). problem is None on success."""
    cli = shutil.which("railway")
    if not cli:
        return {}, "the Railway CLI is not installed (npm i -g @railway/cli)"
    try:
        result = subprocess.run(
            [cli, "variables", "-p", RAILWAY_PROJECT, "-e", RAILWAY_ENVIRONMENT,
             "-s", RAILWAY_SERVICE, "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {}, f"the Railway CLI could not run ({exc})"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        hint = detail[0] if detail else f"exit {result.returncode}"
        return {}, f"the Railway CLI failed: {hint} (try `railway login`)"
    try:
        return json.loads(result.stdout), None
    except ValueError:
        return {}, "the Railway CLI returned output that was not JSON"


def load_secrets() -> str | None:
    """Fill any missing SECRET_NAMES into os.environ from Railway.

    Returns a description of why Railway could not be read, or None. Callers
    decide which secrets are required; this only fetches.
    """
    missing = [name for name in SECRET_NAMES if not os.environ.get(name)]
    if not missing:
        return None
    variables, problem = _railway_variables()
    for name in missing:
        if variables.get(name):
            os.environ[name] = variables[name]
    return problem


def require_tavily_key() -> None:
    problem = load_secrets()
    if os.environ.get("TAVILY_API_KEY"):
        return
    where = f"Railway could not be read: {problem}." if problem else (
        f"It is not set on Railway ({RAILWAY_SERVICE})."
    )
    raise SystemExit(f"TAVILY_API_KEY is not in the environment. {where}\n\n{SET_HELP}")
