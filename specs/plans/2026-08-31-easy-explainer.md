# Easy Explainer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a plain-language "Easy explainer" block to every study page that tells a caregiver how much weight the study carries, what is missing, and what the researchers concluded — after first repairing the `participants` field it depends on.

**Architecture:** A new standalone module `pipelines/pubmed/explainer.py` composes the block deterministically from fields already on the record. It is called from `normalize_study()` so both extraction paths and every rebuild produce identical output. `participants` extraction is rewritten in `scripts/extract_studies_from_raw.py` to find the study total or return `null`, guarded by a hand-read truth fixture covering all 44 abstracts. Rendering reuses the site's existing `--tier-N` colour variables.

**Tech Stack:** Python 3.12 stdlib only (plus `jsonschema`, already a dependency). Jekyll/Liquid + plain CSS for rendering. No new runtime dependencies.

## Global Constraints

- **Never state what the source does not support.** `null` is always a correct answer; a plausible guess is not. This governs every copy rule below.
- **No pytest.** This repo has no test framework. Verification is corpus-invariant checker scripts in the style of `scripts/check_raw_coverage.py`, run in CI. (Spec Part 6.)
- **Deterministic only.** No LLM call anywhere in this feature. Same record must always produce the same text.
- **`trust_tier_label` quotes `study_type` verbatim** ("Randomized Controlled Trial"), because the page header badge shows that exact string a few lines above. Prose is British spelling. (Spec Part 3, Part 4.)
- **Demotion floors at tier 3.** Tier 4 means "design not stated" site-wide and must not come to mean "small".
- **Unknown size never demotes.** A `null` participant count is missing information, not a small study.
- **Small-sample threshold is `n < 30`**, the same number as the `size` copy band, so badge and prose always agree.
- Run all commands from the repo root: `C:\Users\Bhavin\Desktop\Git Projects\Curioler-org\curioler-research`.

## File Structure

| File | Responsibility |
|---|---|
| `specs/fixtures/participants-truth.json` | **Create.** Hand-read total for all 44 PMIDs. The contract the parser is held to. |
| `scripts/check_participants.py` | **Create.** Asserts parser output matches truth or is `null`. |
| `scripts/extract_studies_from_raw.py` | **Modify.** Replace `PARTICIPANT_PATTERNS` / `infer_participants`. |
| `pipelines/pubmed/explainer.py` | **Create.** `trust_tier()`, `build_explainer()`, and copy rules. Standalone — imports nothing from `common`, to avoid a cycle. |
| `pipelines/pubmed/common.py` | **Modify.** Add 3 fields to `STUDY_FIELDS`; call explainer at the end of `normalize_study()`. |
| `schemas/study.schema.json` | **Modify.** Add `trust_tier`, `trust_tier_label`, `easy_explainer`. |
| `scripts/generate_study_pages.py` | **Modify.** Emit new fields into frontmatter and `docs/_data/studies.json`. |
| `docs/_layouts/study.html` | **Modify.** Render the block after `.summary-header`. |
| `docs/assets/css/style.css` | **Modify.** `.easy-explainer` rules using existing tier variables. |
| `scripts/check_explainer.py` | **Create.** Corpus invariants + copy-rule assertions on synthetic inputs. |
| `.github/workflows/pubmed-ingestion.yml` | **Modify.** Run both new checkers. |

---

### Task 1: Participants truth fixture and its failing checker

Establishes the contract before touching the parser. This task deliberately ends **red** — the checker must fail against today's parser, proving it detects the defect.

**Files:**
- Create: `specs/fixtures/participants-truth.json`
- Create: `scripts/check_participants.py`

**Interfaces:**
- Consumes: `infer_participants(text)` and `split_sections(abstract)` from `scripts/extract_studies_from_raw.py` (existing).
- Produces: `specs/fixtures/participants-truth.json`, a `{pmid: int | null}` map consumed by Task 2's verification.

- [ ] **Step 1: Write the truth fixture**

Values below were established by reading each abstract. `null` means the abstract states no unambiguous study total. Two entries (`40120015`, `42160813`) are counts split across two groups joined by "and"; the total is recorded, and a parser returning `null` for them is acceptable — returning either half is not.

Create `specs/fixtures/participants-truth.json`:

```json
{
  "_comment": "Hand-read total enrolled per abstract. Parser must return this value or null; any other value is a failure. See specs/2026-08-31-easy-explainer-design.md Part 1.",
  "39930281": 148,
  "39948293": 49,
  "39951211": null,
  "39954217": null,
  "39954218": null,
  "39984783": 107,
  "40016545": 41,
  "40120015": 625,
  "40178785": 40,
  "40750084": 109,
  "41392642": 20,
  "41486975": 366,
  "41527987": 75,
  "41550040": 87,
  "41578977": 27,
  "41765239": 62,
  "41904269": null,
  "41927180": null,
  "41941984": null,
  "41967364": null,
  "41986743": 67,
  "42080302": null,
  "42092454": null,
  "42092723": 642,
  "42160813": 46,
  "42166881": 96,
  "42217453": 12,
  "42224253": 177,
  "42248366": 20,
  "42281150": 178,
  "42303595": null,
  "42363339": 30,
  "42387975": 130,
  "42393738": 112,
  "42394366": 249,
  "42410944": 66,
  "42438230": 52,
  "42459342": 38,
  "42468411": 40,
  "42491294": null,
  "42492413": 876,
  "42492845": 40,
  "42494078": 40,
  "42590803": 70
}
```

- [ ] **Step 2: Write the checker**

Create `scripts/check_participants.py`:

```python
#!/usr/bin/env python3
"""Hold the participants parser to a hand-read truth fixture.

The parser may return the recorded total, or null when the abstract does not
state one unambiguously. Any third answer is a failure: a wrong sample size
becomes a wrong sentence in the Easy explainer, read by caregivers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipelines.pubmed.common import RAW_ABSTRACT_DIR, ROOT
from scripts.extract_studies_from_raw import infer_participants, split_sections

TRUTH_PATH = ROOT / "specs" / "fixtures" / "participants-truth.json"


def parsed_value(pmid: str) -> object:
    abstract = (RAW_ABSTRACT_DIR / f"PMID{pmid}.txt").read_text(encoding="utf-8").strip()
    sections = split_sections(abstract)
    methodsish = " ".join(
        sections.get(key, "")
        for key in ("METHODS", "METHOD", "MATERIALS AND METHODS", "DESIGN", "RESULTS", "RESULT", "BODY")
    )
    return infer_participants(methodsish or abstract)


def main() -> None:
    argparse.ArgumentParser(description="Check participants against the truth fixture.").parse_args()
    truth = {k: v for k, v in json.loads(TRUTH_PATH.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    wrong, missing, matched, conceded = [], [], 0, 0
    for pmid, expected in sorted(truth.items()):
        if not (RAW_ABSTRACT_DIR / f"PMID{pmid}.txt").exists():
            missing.append(pmid)
            continue
        actual = parsed_value(pmid)
        if actual == expected:
            matched += 1
        elif actual is None:
            conceded += 1
        else:
            wrong.append((pmid, expected, actual))
    if missing:
        print(f"WARNING: {len(missing)} fixture PMIDs have no raw abstract: {missing}")
    print(f"exact match: {matched}   conceded to null: {conceded}   WRONG: {len(wrong)}")
    for pmid, expected, actual in wrong:
        print(f"  - PMID{pmid}: expected {expected} or null, got {actual}")
    if wrong:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the checker and confirm it fails**

```bash
python -m scripts.check_participants
```

Expected: exit 1, with roughly a dozen `WRONG` lines including `PMID41392642: expected 20 or null, got 6` and `PMID42224253: expected 177 or null, got 414`. If it passes, the fixture is wrong — stop and re-read the abstracts.

- [ ] **Step 4: Commit the red state**

```bash
git add specs/fixtures/participants-truth.json scripts/check_participants.py
git commit -m "Add participants truth fixture and checker

Records the hand-read total for all 44 abstracts and fails against the
current parser, which takes the first 'n = X' and so returns a single trial
arm. Committed red so the fix has something to turn green."
```

---

### Task 2: Rewrite the participants parser

**Files:**
- Modify: `scripts/extract_studies_from_raw.py` (replace `PARTICIPANT_PATTERNS` and `infer_participants`)

**Interfaces:**
- Consumes: `specs/fixtures/participants-truth.json` via `scripts/check_participants.py` from Task 1.
- Produces: `infer_participants(text) -> int | None`. Signature unchanged, so `build_study()` needs no edit. Return type narrows from `int | str | None` to `int | None`.

- [ ] **Step 1: Replace the patterns and the function**

In `scripts/extract_studies_from_raw.py`, replace the whole `PARTICIPANT_PATTERNS` block with:

```python
# `participants` is the TOTAL number of people enrolled, or None. The previous
# patterns took the first "n = X" in the abstract, which in a trial abstract is
# almost always a single arm: PMID40178785 stored 20 for a 40-child study, and
# PMID41392642 stored 6 from "n = 6, 7%" of eighty rated studies. A wrong number
# here becomes a wrong sentence in the Easy explainer, so every pattern requires a
# person noun and anything ambiguous returns None.
PERSON_NOUN = (
    r"(?:children|adults?|adolescents?|youth|participants?|patients?|individuals?|"
    r"subjects?|toddlers?|infants?|preschoolers?|cases|caregivers?|parents?|dyads?|"
    r"families|women|men|mothers?|fathers?|people)"
)

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
NUMBER_WORD_RE = "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))
# "Forty", "Eighty-seven", "One hundred and seven", "One-hundred and thirty"
SPELLED = rf"(?:(?:{NUMBER_WORD_RE})(?:[- ]hundred)?(?:[- ]and)?(?:[- ](?:{NUMBER_WORD_RE}))*)"

# Words that mean the number counts something other than enrolled people.
NOT_PEOPLE = re.compile(
    r"(?i)\b(observations?|studies|articles|papers|records|sessions|samples?|images?|"
    r"videos?|questionnaires?|visits?|scans?|trials?|controls?|screened)\b"
)
# Words that mean the number is one arm rather than the whole study.
PER_ARM = re.compile(r"(?i)(\bgroups?\b|\barms?\b|\beach\b|per group|/group|\bsubgroups?\b|\bcompleters?\b)")

PARTICIPANT_PATTERNS = [
    # "a total of 112 autistic children"
    re.compile(rf"(?i)\ba total of\s+(\d{{1,5}})\s+(?:[\w-]+\s+){{0,3}}?{PERSON_NOUN}\b"),
    # "Parents (N = 41) of autistic children"
    re.compile(rf"(?i)\b{PERSON_NOUN}\s*\(\s*[Nn]\s*=\s*(\d{{1,5}})\s*\)"),
    # "109 participants were randomized", "40 participants were randomized"
    re.compile(
        rf"(?i)\b(\d{{1,5}})\s+(?:[\w-]+\s+){{0,3}}?{PERSON_NOUN}\s+(?:were|was)\s+"
        r"(?:randomi|enroll|recruit|assign|includ|allocat)"
    ),
    # "recruited 40 children with ASD", "randomized 112 children"
    re.compile(
        rf"(?i)\b(?:randomi\w+|enrolled|recruited|included|involving|comprised)\s+"
        rf"(\d{{1,5}})\s+(?:[\w-]+\s+){{0,3}}?{PERSON_NOUN}\b"
    ),
    # "Forty children", "Eighty-seven autistic children", "One hundred and seven parents"
    re.compile(rf"(?i)\b({SPELLED})\s+(?:[\w-]+\s+){{0,3}}?{PERSON_NOUN}\b"),
]
```

Then replace `infer_participants` with:

```python
def words_to_int(text: str) -> int | None:
    total = 0
    current = 0
    for token in re.split(r"[- ]+", text.lower()):
        if token == "and":
            continue
        if token == "hundred":
            current = (current or 1) * 100
            continue
        value = NUMBER_WORDS.get(token)
        if value is None:
            return None
        current += value
    total += current
    return total or None


def infer_participants(text: str) -> int | None:
    """Total people enrolled, or None when the abstract does not state one clearly."""
    text = text or ""
    found: list[int] = []
    for pattern in PARTICIPANT_PATTERNS:
        for match in pattern.finditer(text):
            context = text[max(0, match.start() - 60) : match.end() + 60]
            if NOT_PEOPLE.search(context) or PER_ARM.search(context):
                continue
            raw = match.group(1)
            value = int(raw) if raw.isdigit() else words_to_int(raw)
            if value and 1 <= value <= 100000:
                found.append(value)
        if found:
            break
    if not found:
        return None
    # Disagreeing candidates from the same pattern mean the abstract is reporting
    # several counts (cases and controls, or several cohorts). Refuse to pick.
    return found[0] if len(set(found)) == 1 else None
```

- [ ] **Step 2: Run the checker and confirm it passes**

```bash
python -m scripts.check_participants
```

Expected: exit 0, `WRONG: 0`. Some records will show under "conceded to null" — that is allowed. If any `WRONG` line remains, adjust the patterns; **never** adjust the fixture to match the parser.

- [ ] **Step 3: Check coverage did not collapse**

```bash
python -c "
import json,sys; sys.path.insert(0,'.')
from scripts.check_participants import parsed_value, TRUTH_PATH
t={k:v for k,v in json.load(open(TRUTH_PATH,encoding='utf-8')).items() if not k.startswith('_')}
got=sum(1 for p in t if parsed_value(p) is not None)
print(f'populated: {got}/44 (was 28, of which ~13 were wrong)')
"
```

Expected: 28 or more. If it drops below 25, a pattern is too strict — investigate before continuing.

- [ ] **Step 4: Commit**

```bash
git add scripts/extract_studies_from_raw.py
git commit -m "Extract the study total for participants, not the first arm

Every pattern now requires a person noun, rejects per-arm and non-person
contexts, and refuses to choose between disagreeing candidates. Adds
spelled-out totals ('Forty children', 'One hundred and seven parents'), which
were missed entirely and are exactly where the digit patterns went wrong.
Verified against the 44-record truth fixture."
```

---

### Task 3: The explainer module

**Files:**
- Create: `pipelines/pubmed/explainer.py`

**Interfaces:**
- Consumes: nothing from other project modules. Standalone by design — `common.py` imports it in Task 4, so it must not import `common`.
- Produces:
  - `trust_tier(study: dict) -> tuple[int, str]` returning `(tier, label)`.
  - `build_explainer(study: dict) -> dict` returning the six keys `design`, `size`, `duration`, `conclusion`, `not_stated`, `disclaimer`.
  - `duration_weeks(text: str | None) -> float | None`.

- [ ] **Step 1: Write the module**

Create `pipelines/pubmed/explainer.py`:

```python
"""Compose the plain-language Easy explainer block from a study record.

Deterministic by design: the same record always produces the same text, so the
output is reviewable in a diff and cannot assert anything the abstract does not
carry. See specs/2026-08-31-easy-explainer-design.md.
"""

from __future__ import annotations

import re

DISCLAIMER = (
    "This is a plain-language summary of one paper's abstract, not medical advice. "
    "Talk to your child's clinician before changing anything."
)

SMALL_SAMPLE = 30
SHORT_STUDY_WEEKS = 12

TIER_1_DESIGNS = {"Meta-Analysis", "Systematic Review"}
TIER_3_DESIGNS = {"Observational Study", "Case Reports"}

DESIGN_SENTENCES = {
    "trial": (
        "This was a randomised controlled trial — people were assigned to treatments by "
        "chance, which is the most reliable way to tell whether a treatment itself caused "
        "a change."
    ),
    "review": (
        "This pooled the results of several earlier studies, which usually gives a steadier "
        "picture than any single study can."
    ),
    "observational": (
        "This was an observational study — researchers watched what happened rather than "
        "assigning treatments. It can show that two things happen together, but it cannot "
        "show that one caused the other."
    ),
    "case": (
        "This describes one case or a small handful of cases. It can raise a question worth "
        "studying, but it cannot tell you what happens for most people."
    ),
    "unknown": (
        "This record does not state what kind of study this was, so how much weight it "
        "carries cannot be judged from this page."
    ),
}

UNIT_WEEKS = {"day": 1 / 7, "week": 1.0, "month": 4.345, "year": 52.18}


def design_kind(study_type: str | None) -> str:
    if not study_type:
        return "unknown"
    if study_type in TIER_1_DESIGNS:
        return "review"
    if study_type == "Observational Study":
        return "observational"
    if study_type == "Case Reports":
        return "case"
    return "trial"


def base_tier(study_type: str | None) -> int:
    if not study_type:
        return 4
    if study_type in TIER_1_DESIGNS:
        return 1
    if study_type in TIER_3_DESIGNS:
        return 3
    return 2


def trust_tier(study: dict) -> tuple[int, str]:
    """Return (tier, label). Small samples demote one step, floored at tier 3."""
    study_type = study.get("study_type")
    tier = base_tier(study_type)
    label = study_type or "Study design not stated"
    participants = study.get("participants")
    if isinstance(participants, int) and participants < SMALL_SAMPLE and tier < 3:
        tier += 1
        label = f"{label} (small sample)"
    return tier, label


def duration_weeks(text: str | None) -> float | None:
    """Normalise a free-text duration to weeks. None when it cannot be parsed."""
    if not text:
        return None
    match = re.search(r"(?i)(\d+(?:\.\d+)?)\s*-?\s*(day|week|month|year)s?", text)
    if not match:
        return None
    return float(match.group(1)) * UNIT_WEEKS[match.group(2).lower()]


def size_sentence(participants: object) -> str:
    if not isinstance(participants, int):
        return (
            "The number of people who took part is not stated in this record, so the result "
            "cannot be judged on size."
        )
    if participants < SMALL_SAMPLE:
        return (
            f"It involved only {participants:,} people. With a group this small, results can "
            "shift a lot by chance, so treat this as an early signal rather than an answer."
        )
    if participants < 100:
        return (
            f"It involved {participants:,} people — a modest group, enough to be interesting "
            "but not enough to settle a question on its own."
        )
    if participants < 500:
        return f"It involved {participants:,} people, a reasonably sized group for this kind of research."
    return (
        f"It involved {participants:,} people, which is a large group for autism research and "
        "makes the findings steadier."
    )


def duration_sentence(duration: str | None) -> str | None:
    if not duration:
        return None
    sentence = f"The study ran for {duration}."
    weeks = duration_weeks(duration)
    if weeks is not None and weeks <= SHORT_STUDY_WEEKS:
        sentence += " That is a short window, so it says nothing about whether the effects last."
    return sentence


def conclusion_sentence(conclusion: str | None) -> str | None:
    if not conclusion:
        return (
            "The abstract does not include a conclusions section, so this page does not state "
            "what the researchers concluded."
        )
    sentences = re.split(r"(?<=[.!?])\s+", conclusion.strip())
    trimmed = " ".join(sentences[:2]).strip()
    return f'The researchers concluded: "{trimmed}"'


def not_stated(study: dict) -> list[str]:
    """Only fields with no sentence of their own, so the block never repeats itself."""
    missing = []
    if not study.get("age_range"):
        missing.append("the ages of the people who took part")
    if not study.get("duration"):
        missing.append("how long the study ran")
    return missing


def build_explainer(study: dict) -> dict:
    return {
        "design": DESIGN_SENTENCES[design_kind(study.get("study_type"))],
        "size": size_sentence(study.get("participants")),
        "duration": duration_sentence(study.get("duration")),
        "conclusion": conclusion_sentence(study.get("conclusion")),
        "not_stated": not_stated(study),
        "disclaimer": DISCLAIMER,
    }
```

- [ ] **Step 2: Verify the rules by hand at the boundaries**

```bash
python -c "
from pipelines.pubmed.explainer import trust_tier, duration_weeks, size_sentence
print(trust_tier({'study_type':'Randomized Controlled Trial','participants':29}))
print(trust_tier({'study_type':'Randomized Controlled Trial','participants':30}))
print(trust_tier({'study_type':'Randomized Controlled Trial','participants':None}))
print(trust_tier({'study_type':'Observational Study','participants':5}))
print(trust_tier({'study_type':None,'participants':400}))
print(round(duration_weeks('3-month'),2), round(duration_weeks('60 days'),2), duration_weeks('a while'))
print(size_sentence(None)[:40])
"
```

Expected exactly:
```
(3, 'Randomized Controlled Trial (small sample)')
(2, 'Randomized Controlled Trial')
(2, 'Randomized Controlled Trial')
(3, 'Observational Study')
(4, 'Study design not stated')
13.03 8.57 None
The number of people who took part is n
```

Note the third line: unknown size does not demote. The fourth: a 5-person observational study stays at tier 3, it does not fall into tier 4.

- [ ] **Step 3: Commit**

```bash
git add pipelines/pubmed/explainer.py
git commit -m "Add the Easy explainer composer

Deterministic prose from the record's own fields: design, sample size,
duration, the researchers' own conclusion, and what the record does not say.
Small samples demote the tier one step, floored at 3 so tier 4 keeps meaning
'design not stated'; an unknown count never demotes, because that is missing
information rather than a small study."
```

---

### Task 4: Wire into the records and the schema

**Files:**
- Modify: `pipelines/pubmed/common.py`
- Modify: `schemas/study.schema.json`

**Interfaces:**
- Consumes: `trust_tier()` and `build_explainer()` from Task 3.
- Produces: every record carries `trust_tier` (int 1–4), `trust_tier_label` (str), `easy_explainer` (object with the six keys). Task 5 renders them; Task 6 checks them.

- [ ] **Step 1: Add the fields to `STUDY_FIELDS` and compute them in `normalize_study`**

In `pipelines/pubmed/common.py`, add to `STUDY_FIELDS` immediately after `"study_type",`:

```python
    "trust_tier",
    "trust_tier_label",
    "easy_explainer",
```

Add the import at the top, after the existing imports:

```python
from pipelines.pubmed.explainer import build_explainer, trust_tier
```

Then, in `normalize_study`, replace the final two lines before `return normalized`:

```python
    normalized["pmid"] = str(normalized["pmid"] or "")
    normalized["source_url"] = normalized["source_url"] or f"https://pubmed.ncbi.nlm.nih.gov/{normalized['pmid']}/"
```

with:

```python
    normalized["pmid"] = str(normalized["pmid"] or "")
    normalized["source_url"] = normalized["source_url"] or f"https://pubmed.ncbi.nlm.nih.gov/{normalized['pmid']}/"
    # Derived last, from the settled fields, so both extraction paths and every
    # rebuild produce the same block.
    normalized["trust_tier"], normalized["trust_tier_label"] = trust_tier(normalized)
    normalized["easy_explainer"] = build_explainer(normalized)
```

- [ ] **Step 2: Add the fields to the schema**

In `schemas/study.schema.json`, add to the `required` array after `"study_type",`:

```json
    "trust_tier",
    "trust_tier_label",
    "easy_explainer",
```

And to `properties`, after the `"study_type"` line:

```json
    "trust_tier": { "type": "integer", "minimum": 1, "maximum": 4 },
    "trust_tier_label": { "type": "string", "minLength": 1 },
    "easy_explainer": {
      "type": "object",
      "additionalProperties": false,
      "required": ["design", "size", "duration", "conclusion", "not_stated", "disclaimer"],
      "properties": {
        "design": { "type": "string", "minLength": 1 },
        "size": { "type": "string", "minLength": 1 },
        "duration": { "type": ["string", "null"] },
        "conclusion": { "type": ["string", "null"] },
        "not_stated": { "type": "array", "items": { "type": "string" } },
        "disclaimer": { "type": "string", "minLength": 1 }
      }
    },
```

- [ ] **Step 3: Regenerate every record and validate**

```bash
python -m scripts.extract_studies_from_raw --all
python -m pipelines.pubmed.validate
```

Expected: `Saved 44 studies`, `Failures: 0`, then `Validated 44 study file(s) against study.schema.json.`

- [ ] **Step 4: Read three real blocks end to end**

```bash
python -c "
import json
for pm in ['41392642','42492413','39954217']:
    d=json.load(open(f'research/studies/2026/PMID{pm}.json',encoding='utf-8'))
    print(f\"--- PMID{pm}  tier {d['trust_tier']} - {d['trust_tier_label']}\")
    e=d['easy_explainer']
    for k in ('design','size','duration','conclusion'):
        print(f'  {k}: {e[k]}')
    print('  not_stated:', e['not_stated'])
"
```

Expected: PMID41392642 reads "It involved only 20 people" (not 6) and sits at tier 3 with a `(small sample)` label on an observational study — i.e. floored, not demoted to 4. PMID42492413 reads "876 people ... a large group". PMID39954217 reads the "not stated" size sentence and shows no invented number.

- [ ] **Step 5: Commit**

```bash
git add pipelines/pubmed/common.py schemas/study.schema.json research docs
git commit -m "Put the Easy explainer on every study record

Computed in normalize_study from the settled fields, so the LLM path, the
abstract-rules path and every rebuild produce identical text."
```

---

### Task 5: Render the block

**Files:**
- Modify: `scripts/generate_study_pages.py`
- Modify: `docs/_layouts/study.html`
- Modify: `docs/assets/css/style.css`

**Interfaces:**
- Consumes: `trust_tier`, `trust_tier_label`, `easy_explainer` on each record, from Task 4.
- Produces: `page.trust_tier`, `page.trust_tier_label`, `page.easy_explainer.*` in study page frontmatter, and the same three keys in `docs/_data/studies.json`.

- [ ] **Step 1: Emit the fields into frontmatter and the data file**

In `scripts/generate_study_pages.py`, inside `render_study_page`, add after the `study_type` line:

```python
        f"trust_tier: {frontmatter_value(study.get('trust_tier'))}",
        f"trust_tier_label: {frontmatter_value(study.get('trust_tier_label'))}",
        f"easy_explainer: {frontmatter_value(study.get('easy_explainer', {}))}",
```

In `public_study_summary`, add after the `"study_type"` line:

```python
        "trust_tier": study.get("trust_tier"),
        "trust_tier_label": study.get("trust_tier_label"),
        "easy_explainer": study.get("easy_explainer"),
```

- [ ] **Step 2: Render the block in the layout**

In `docs/_layouts/study.html`, insert immediately after the closing `</header>` of `.summary-header` and before `<div class="summary-body study-body">`:

```html
    <aside class="easy-explainer easy-explainer--tier-{{ page.trust_tier }}">
      <div class="easy-explainer-head">
        <h2>Easy explainer</h2>
        <span class="tier-badge tier-{{ page.trust_tier }}">
          Tier {{ page.trust_tier }} — {{ page.trust_tier_label }}
        </span>
      </div>
      <p>{{ page.easy_explainer.design }}</p>
      <p>{{ page.easy_explainer.size }}</p>
      {% if page.easy_explainer.duration %}<p>{{ page.easy_explainer.duration }}</p>{% endif %}
      {% if page.easy_explainer.conclusion %}<p>{{ page.easy_explainer.conclusion }}</p>{% endif %}
      {% if page.easy_explainer.not_stated and page.easy_explainer.not_stated.size > 0 %}
      <p class="easy-explainer-missing">
        This record does not say {{ page.easy_explainer.not_stated | join: ", or " }}.
      </p>
      {% endif %}
      <p class="easy-explainer-disclaimer">{{ page.easy_explainer.disclaimer }}</p>
    </aside>
```

- [ ] **Step 3: Add the styles**

Append to `docs/assets/css/style.css`:

```css
.easy-explainer {
  margin: 1.75rem 0 2rem;
  padding: 1.25rem 1.5rem;
  border-left: 4px solid var(--tier-4);
  background: var(--tier-4-bg);
  border-radius: 6px;
}
.easy-explainer--tier-1 { border-left-color: var(--tier-1); background: var(--tier-1-bg); }
.easy-explainer--tier-2 { border-left-color: var(--tier-2); background: var(--tier-2-bg); }
.easy-explainer--tier-3 { border-left-color: var(--tier-3); background: var(--tier-3-bg); }
.easy-explainer--tier-4 { border-left-color: var(--tier-4); background: var(--tier-4-bg); }
.easy-explainer-head {
  display: flex; flex-wrap: wrap; align-items: center; gap: .75rem;
  margin-bottom: .75rem;
}
.easy-explainer-head h2 { margin: 0; font-size: 1.05rem; }
.easy-explainer p { margin: 0 0 .6rem; line-height: 1.6; }
.easy-explainer p:last-child { margin-bottom: 0; }
.easy-explainer-missing { font-style: italic; }
.easy-explainer-disclaimer { font-size: .85rem; opacity: .8; }
```

- [ ] **Step 4: Regenerate pages and inspect the output**

```bash
python scripts/generate_study_pages.py
grep -A3 "^easy_explainer:" docs/_studies/PMID41392642*.md | head -5
```

Expected: an `easy_explainer:` frontmatter line holding a JSON object whose `size` value reads "It involved only 20 people…".

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_study_pages.py docs
git commit -m "Render the Easy explainer below the study title

Sits between the byline and the metadata list, tinted and left-bordered in
the tier colour so it stands out and the colour carries the tier meaning."
```

---

### Task 6: Invariant checker and CI

**Files:**
- Create: `scripts/check_explainer.py`
- Modify: `.github/workflows/pubmed-ingestion.yml`

**Interfaces:**
- Consumes: `build_explainer` and `trust_tier` from Task 3; the regenerated records from Task 4.
- Produces: a CI gate. No downstream consumers.

- [ ] **Step 1: Write the checker**

Create `scripts/check_explainer.py`:

```python
#!/usr/bin/env python3
"""Corpus invariants for the Easy explainer.

The block is read by caregivers deciding about their child's care, so the
failure that matters is not a crash but a confident sentence the record does
not support. These checks target exactly that.
"""

from __future__ import annotations

import argparse
import json
import re

from pipelines.pubmed.common import STUDIES_DIR
from pipelines.pubmed.explainer import base_tier, build_explainer, trust_tier

MISSING_PHRASES = {
    "the ages of the people who took part": "age_range",
    "how long the study ran": "duration",
}


def check(study: dict) -> list[str]:
    errors = []
    tier, label = study.get("trust_tier"), study.get("trust_tier_label")
    explainer = study.get("easy_explainer") or {}

    if not isinstance(tier, int) or not 1 <= tier <= 4:
        errors.append(f"trust_tier must be 1-4, got {tier!r}")
    if not label:
        errors.append("trust_tier_label is empty")
    if tier == 4 and study.get("study_type"):
        errors.append(f"tier 4 means 'design not stated', but study_type is {study['study_type']!r}")

    # A number in the size sentence with no participants value is the failure mode
    # this whole feature was designed around.
    if study.get("participants") is None and re.search(r"\d", explainer.get("size", "")):
        errors.append(f"size sentence quotes a number but participants is null: {explainer.get('size')!r}")
    if study.get("participants") is None and tier != base_tier(study.get("study_type")):
        errors.append("tier was demoted while participants is null")
    if study.get("conclusion") is None and "researchers concluded" in (explainer.get("conclusion") or ""):
        errors.append("conclusion sentence quotes researchers but conclusion is null")

    for phrase in explainer.get("not_stated", []):
        field = MISSING_PHRASES.get(phrase)
        if field is None:
            errors.append(f"unrecognised not_stated phrase: {phrase!r}")
        elif study.get(field):
            errors.append(f"not_stated claims {field} is missing, but it is {study[field]!r}")

    # Text must be reproducible from the record alone.
    if explainer != build_explainer(study):
        errors.append("easy_explainer does not match a fresh build from this record")
    if (tier, label) != trust_tier(study):
        errors.append("trust_tier/label do not match a fresh computation")
    return errors


def main() -> None:
    argparse.ArgumentParser(description="Check Easy explainer invariants.").parse_args()
    paths = sorted(STUDIES_DIR.glob("*/*.json"))
    failed = False
    for path in paths:
        study = json.loads(path.read_text(encoding="utf-8"))
        errors = check(study)
        if errors:
            failed = True
            print(f"{path}:")
            for error in errors:
                print(f"  - {error}")
    if failed:
        raise SystemExit(1)
    print(f"Easy explainer invariants hold across {len(paths)} study file(s).")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

```bash
python -m scripts.check_explainer
```

Expected: `Easy explainer invariants hold across 44 study file(s).`

- [ ] **Step 3: Prove it catches the failure it exists for**

```bash
python -c "
import json,sys; sys.path.insert(0,'.')
from scripts.check_explainer import check
s=json.load(open('research/studies/2026/PMID39954217.json',encoding='utf-8'))
s['easy_explainer']['size']='It involved 42 people, a reasonably sized group.'
print(check(s))
"
```

Expected: a list containing the `size sentence quotes a number but participants is null` error. If it returns `[]`, the check is not wired correctly.

- [ ] **Step 4: Add both checkers to CI**

In `.github/workflows/pubmed-ingestion.yml`, extend the existing coverage step block so it reads:

```yaml
      - name: Check every raw capture has a study record
        run: python -m scripts.check_raw_coverage

      - name: Check participants against the truth fixture
        run: python -m scripts.check_participants

      - name: Check Easy explainer invariants
        run: python -m scripts.check_explainer
```

- [ ] **Step 5: Commit**

```bash
git add scripts/check_explainer.py .github/workflows/pubmed-ingestion.yml
git commit -m "Gate the Easy explainer on corpus invariants

Fails when a size sentence quotes a number the record does not have, when a
tier is demoted on an unknown count, when not_stated names a populated field,
or when stored text does not match a fresh build."
```

---

### Task 7: Full regeneration, final verification, handoff

**Files:**
- Modify: `README.md`
- Modify: `specs/2026-08-31-easy-explainer-design.md` (status line only)

**Interfaces:**
- Consumes: everything above.
- Produces: pushed `main`, and the field list the `curioler-platform` session needs.

- [ ] **Step 1: Rebuild everything from raw and run every check**

```bash
python -m scripts.extract_studies_from_raw --all
python -m pipelines.pubmed.validate
python -m scripts.check_raw_coverage
python -m scripts.check_participants
python -m scripts.check_explainer
```

Expected: all five pass, 44 records.

- [ ] **Step 2: Confirm rebuilds are idempotent**

```bash
python -m scripts.extract_studies_from_raw --all >/dev/null
git diff --stat research/studies | tail -1
```

Expected: only `last_updated` differences. Any change to `easy_explainer` text between two runs means non-determinism crept in — stop and find it.

- [ ] **Step 3: Report the tier distribution**

```bash
python -c "
import json,glob,collections
r=[json.load(open(p,encoding='utf-8')) for p in glob.glob('research/studies/*/PMID*.json')]
print(collections.Counter((x['trust_tier'],x['trust_tier_label']) for x in r).most_common())
print('demoted:',sum(1 for x in r if '(small sample)' in x['trust_tier_label']))
print('participants populated:',sum(1 for x in r if x['participants'] is not None),'/',len(r))
"
```

- [ ] **Step 4: Document the fields in the README**

Add to the `## Data Rules` list in `README.md`:

```markdown
- `participants` is the total number of people enrolled, or `null` — never a single
  trial arm, and never a count of observations or of other studies.
  `python -m scripts.check_participants` holds it to a hand-read fixture of every
  abstract.
- `trust_tier`, `trust_tier_label` and `easy_explainer` are derived in
  `normalize_study()` and must never be hand-edited. Tier 4 means "design not stated";
  a small sample demotes one step but never past tier 3.
```

- [ ] **Step 5: Mark the spec implemented and commit**

Change the spec's `Status:` line to `Status: implemented 2026-08-31`.

```bash
git add README.md specs research docs
git commit -m "Regenerate all records with the Easy explainer

Documents the participants rule and the derived explainer fields, and marks
the design spec implemented."
git push origin main
```

- [ ] **Step 6: Hand off to the platform session**

Report: the three new fields (`trust_tier` int 1–4, `trust_tier_label` string, `easy_explainer` object with `design`/`size`/`duration`/`conclusion`/`not_stated`/`disclaimer`), that `trust_tier` matches the 1–4 vocabulary already used by summaries and myth-checks so existing tier rendering applies, that `duration` and `conclusion` are nullable and the block omits those paragraphs when null, that `participants` semantics changed to "total enrolled" and previously published values were wrong on roughly half the records, and the commit SHA.

---

## Self-Review

**Spec coverage:** Part 1 → Tasks 1–2. Part 2 (data model, `normalize_study` placement, schema) → Task 4. Part 3 (tier table, verbatim label, demotion floor, unknown-size rule) → Task 3 Steps 1–2, checked in Task 6. Part 4 (all five copy sections, British prose, duration normalisation, `not_stated` restricted to `age_range`/`duration`, `clinical_implications` unused) → Task 3. Part 5 (placement, tier colours) → Task 5. Part 6 (checker, no pytest) → Task 6. Part 7 (platform fields, `studies.json`) → Task 5 Step 1, Task 7 Step 6. No gaps.

**Placeholder scan:** No TBD/TODO. Every code step carries complete code; every command carries expected output.

**Type consistency:** `infer_participants` returns `int | None` throughout. `trust_tier` returns `tuple[int, str]` in Task 3 and is unpacked as such in Task 4 and compared as a tuple in Task 6. `build_explainer` returns the same six keys in Task 3, the schema in Task 4, the template in Task 5 and the checker in Task 6. `base_tier` is defined in Task 3 and imported by name in Task 6. `duration_weeks` returns `float | None` and is only compared numerically after a `None` guard.

**One risk carried knowingly:** `check_explainer` recomputes `build_explainer(study)` and compares. If a copy rule is edited without regenerating the corpus, CI fails rather than silently serving stale text. That is the intended behaviour, but it does mean copy edits and a regeneration must land in the same commit.
