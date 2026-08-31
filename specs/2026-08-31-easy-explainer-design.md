# Easy explainer block — design

Date: 2026-08-31
Status: implemented 2026-08-31

## Purpose

Study pages are written for caregivers of neurodivergent children, but they currently
present a paper's metadata without saying how much weight it can carry. A parent
reading a 15-person pilot and a 900-person cohort sees the same page furniture.

The Easy explainer is a plain-language block, directly below the title and the
PMID/DOI/journal byline, that says what kind of study this was, how much confidence
that earns, what is missing from the record, and what the researchers themselves
concluded.

## Governing constraint

This is health content that caregivers may act on. Every rule below is subordinate to
one requirement: **the block must never state something the source does not support.**
Where a fact is unavailable the block says so in plain words. `null` is always a
correct answer; a plausible-sounding guess is not.

This is the same rule the DOI defect broke, restated for generated prose.

---

## Part 1 — Fix `participants` first

The explainer's central claim depends on sample size, and `participants` is currently
unreliable. It is produced by `PARTICIPANT_PATTERNS` in
`scripts/extract_studies_from_raw.py`, which takes the first `n = X` in the abstract.
In a trial abstract that is almost always one arm.

Confirmed wrong by reading the abstracts:

| PMID | stored | source text | true total |
|---|---|---|---|
| 41392642 | 6 | "n = 6, 7%" of eighty *studies* rated inadequate | 20 children |
| 42224253 | 414 | "414 video *observations*" | 177 children |
| 40178785 | 20 | experimental *arm* | 40 ("Forty children") |
| 42363339 | 15 | "n=15/*group*", two groups | 30 ("Thirty ... cases") |
| 42491294 | 18 | intervention *group* only | larger |
| 42410944 | 16 | one of three training *groups* | larger |

Classifying all 28 populated values by match context: 13 matched in a per-arm or
not-a-person context. A further 16 records are null. At most ~15 of 44 are trustworthy.

### New rule

`participants` means **the total number of people enrolled in the study**, or `null`.

Accept a candidate only when it is adjacent to a person noun (`children`, `adults`,
`adolescents`, `youth`, `participants`, `patients`, `individuals`, `subjects`,
`toddlers`, `infants`, `preschoolers`, `cases`, `caregivers`, `parents`, `dyads`,
`families`) and matches one of:

1. a spelled-out total — `Forty children`, `Eighty-seven autistic children`,
   `Thirty diagnosed ASD cases`. Currently missed entirely, and these recover exactly
   the totals the digit patterns get wrong.
2. `a total of N children`
3. `N children were randomised | enrolled | recruited | assigned | included`
4. `randomised | enrolled | recruited N children`

Reject, yielding `null`:

- the match sits in per-arm context: `group`, `arm`, `per group`, `/group`,
  `subgroup`, `each`
- the counted noun is not people: `observations`, `studies`, `articles`, `videos`,
  `records`, `sessions`, `samples`, `images`
- two candidate totals disagree and nothing marks either as the total

Spelled-out numbers are converted by an explicit word-to-number map covering one
through twenty, the tens to ninety, and hyphenated compounds (`Eighty-seven`).
Anything outside that map is not a candidate.

Coverage is expected to be near today's 28 but correct. If precision forces coverage
lower, lower and correct is the accepted trade.

### Verification

Every one of the 44 abstracts is read by hand and its true total recorded in
`specs/fixtures/participants-truth.json`. The parser must, for every record, either
match the recorded total or return `null`. A third answer is a failure. This fixture
is checked in so the guarantee survives future pattern edits.

---

## Part 2 — Data model

New module `pipelines/pubmed/explainer.py`, exposing `build_explainer(study) -> dict`
and `trust_tier(study) -> tuple[int, str]`.

Called from `normalize_study()` in `pipelines/pubmed/common.py`, so both extraction
paths (LLM and abstract-rules) and every rebuild produce it identically, and it is
recomputed whenever the underlying fields change.

Three new fields on every study record:

```json
"trust_tier": 2,
"trust_tier_label": "Randomized Controlled Trial",
"easy_explainer": {
  "design": "This was a randomised controlled trial...",
  "size": "It involved 40 people...",
  "duration": "The study ran for 12 weeks...",
  "conclusion": "The researchers concluded: \"...\"",
  "not_stated": ["the ages of the people who took part"],
  "disclaimer": "This is a plain-language summary of one paper's abstract..."
}
```

`design`, `size` and `disclaimer` are always strings. `duration` and `conclusion` are
`string | null`. `not_stated` is always an array, empty when nothing is missing.

Named parts rather than one blob, so the platform can style, reorder or omit
individual sentences without parsing prose.

Schema: `easy_explainer` is an object with `additionalProperties: false` and all six
keys required. `trust_tier` is an integer 1–4. `trust_tier_label` is a string.

---

## Part 3 — Trust tier

### Base tier, from `study_type`

| `study_type` | tier |
|---|---|
| Meta-Analysis, Systematic Review | 1 |
| Randomized Controlled Trial | 2 |
| Adaptive / Pragmatic / Controlled Clinical Trial, Clinical Trial + phases | 2 |
| Observational Study | 3 |
| Case Reports | 3 |
| `null` | 4 |

`trust_tier_label` is the record's `study_type` string **verbatim** — "Randomized
Controlled Trial", not a re-spelled paraphrase — with `Study design not stated` used
when `study_type` is null. The study-design badge in the page header shows the same
string, and the two sit a few lines apart, so any paraphrase would read as a
discrepancy. This differs slightly from the label wording on summaries
("Systematic review or meta-analysis"); agreement within one page wins over agreement
across content types.

This reuses the tier vocabulary and the `--tier-N` / `--tier-N-bg` colours already in
`docs/assets/css/style.css` and already used by summaries and myth-checks, so a
caregiver learns one colour language across the site.

### Small-sample demotion

When `participants` is known and **below 30**, the tier drops by one step, and the
label gains a ` (small sample)` suffix — so an amber badge on a randomised trial
explains itself rather than looking like an error.

Two boundaries make this rule safe:

- **The demotion floors at tier 3.** Tier 4 means *"design not stated"* everywhere
  else on the site. Demoting a small observational study into tier 4 would conflate
  "small" with "unknown" and corrupt an existing site-wide meaning.
- **Unknown size never demotes.** A `null` participant count is absence of
  information, not evidence of a small study. The tier stays at its design value and
  the `size` sentence says the count is not stated.

The demotion threshold is deliberately the same 30 used by the `size` copy band, so
the badge and the prose always agree.

---

## Part 4 — Copy rules

Tone follows the existing myth-checks: warm, direct, short sentences, no jargon left
unexplained.

Spelling is British, which is what the published prose already uses — `behaviour` and
`behavioural` outnumber the American forms 58 to 17 across `docs/_myth_checks` and
`docs/_summaries`, and most of the American instances sit inside quoted paper titles.
The one exception is `trust_tier_label`, which quotes the MeSH `study_type` verbatim
per Part 3.

### `design`

- **Trial:** "This was a randomised controlled trial — people were assigned to
  treatments by chance, which is the most reliable way to tell whether a treatment
  itself caused a change."
- **Observational:** "This was an observational study — researchers watched what
  happened rather than assigning treatments. It can show that two things happen
  together, but it cannot show that one caused the other."
- **Review / meta-analysis:** "This pooled the results of several earlier studies,
  which usually gives a steadier picture than any single study can."
- **Case report:** "This describes one case or a small handful of cases. It can raise
  a question worth studying, but it cannot tell you what happens for most people."
- **`null`:** "This record does not state what kind of study this was, so how much
  weight it carries cannot be judged from this page."

### `size`

| `participants` | sentence |
|---|---|
| < 30 | "It involved only N people. With a group this small, results can shift a lot by chance, so treat this as an early signal rather than an answer." |
| 30–99 | "It involved N people — a modest group, enough to be interesting but not enough to settle a question on its own." |
| 100–499 | "It involved N people, a reasonably sized group for this kind of research." |
| ≥ 500 | "It involved N people, which is a large group for autism research and makes the findings steadier." |
| `null` | "The number of people who took part is not stated in this record, so the result cannot be judged on size." |

### `duration`

Present: "The study ran for {duration}."

`duration` is a free string (`"8 weeks"`, `"3-month"`, `"60 days"`, `"20-week"`), so
the short-window clause needs an explicit normalisation. Read the leading number and
unit and convert to weeks: days ÷ 7, weeks × 1, months × 4.345, years × 52.18. When
the result is **12 weeks or less**, append: " That is a short window, so it says
nothing about whether the effects last." When the string cannot be parsed into a
number and a known unit, the clause is omitted — an unparsed duration is not evidence
of a short one.

Null: the field is `null` and "how long the study ran" is added to `not_stated`.

### `conclusion`

Present: `The researchers concluded: "{conclusion}"` — the paper's own CONCLUSION
section, quoted and attributed to them, trimmed to its first two sentences if longer.

Null (22 of 44 records): "The abstract does not include a conclusions section, so this
page does not state what the researchers concluded."

`clinical_implications` is deliberately **not** used. It is populated on 44/44 but is
partly generated boilerplate ("May be relevant to X in Y, based on abstract-reported
findings"), and presenting a template sentence as a finding is exactly what this block
exists to prevent.

### `not_stated`

Only fields that have **no sentence of their own** appear here, so the block never
says the same thing twice:

| field | phrase |
|---|---|
| `age_range` | "the ages of the people who took part" |
| `duration` | "how long the study ran" |

A null `participants` is already spoken to by the `size` sentence, and a null
`conclusion` by the `conclusion` sentence; neither is repeated in this list.

### `disclaimer`

Fixed string, on every record: "This is a plain-language summary of one paper's
abstract, not medical advice. Talk to your child's clinician before changing anything."

---

## Part 5 — Rendering

In `docs/_layouts/study.html`, immediately after the `.summary-header` element (which
holds the title and the PMID/DOI/journal byline) and before the Metadata list.

```html
<aside class="easy-explainer tier-bg-{{ page.trust_tier }}">
  <h2>Easy explainer</h2>
  <span class="tier-badge tier-{{ page.trust_tier }}">
    Tier {{ page.trust_tier }} — {{ page.trust_tier_label }}
  </span>
  ... design, size, duration, conclusion paragraphs ...
  ... not_stated list, rendered only when non-empty ...
  <p class="easy-explainer-disclaimer">{{ page.easy_explainer.disclaimer }}</p>
</aside>
```

New CSS in `docs/assets/css/style.css`: tinted background from the existing
`--tier-N-bg` variable and a 4px left border in `--tier-N`, so the block stands out
and its colour carries the tier meaning. The existing `.tier-badge` and `.tier-N`
rules are reused unchanged.

The confidence badge removed earlier from the header is not reinstated; the tier badge
lives inside the block.

---

## Part 6 — Verification

`scripts/check_explainer.py`, in the style of the existing `scripts/check_raw_coverage.py`,
run in the daily workflow. It fails when, across the corpus:

- any `size` sentence contains a digit while `participants` is `null`
- any record lacks `trust_tier`, `trust_tier_label` or `easy_explainer`
- `trust_tier` is outside 1–4, or is 4 while `study_type` is non-null
- a `not_stated` entry names a field that is actually populated
- a `conclusion` sentence exists while the record's `conclusion` is `null`
- a tier is demoted while `participants` is `null`

Plus the participants truth-fixture check from Part 1.

No pytest. This repo has no test framework, and a corpus invariant checker matches the
pattern already established by `check_raw_coverage.py`.

---

## Part 7 — Platform coordination

Three new fields for the `curioler-platform` session: `trust_tier`,
`trust_tier_label`, `easy_explainer`. All three are added to `docs/_data/studies.json`
via `public_study_summary()` as well as the individual study records.

`trust_tier` and `trust_tier_label` match the names and the 1–4 range already used by
summaries and myth-checks, so the platform's existing tier rendering applies.

---

## Out of scope

- Any "what this means for your child" advice line. The myth-checks carry one, but
  those are reviewed before publishing; auto-generated per-study guidance across a
  growing corpus is health advice nobody has signed off.
- Rewriting `clinical_implications`, `limitations` or `primary_outcomes`.
- Changing the discovery window (`max_results: 25`), tracked separately.
