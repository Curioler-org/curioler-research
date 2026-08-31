# Curioler Research

Evidence-based research summaries for caregivers of autistic and neurodivergent children, powered by Curioler.

This repository is the canonical evidence store for:

- Plain-language research topic summaries
- Fact checks
- Structured research study JSON records
- Raw PubMed XML and abstract captures
- Generated study indexes for the website and future knowledge graph work

## Repository Layout

- `topics/` mirrors published topic summaries by domain.
- `factchecks/` mirrors published fact checks.
- `research/studies/<year>/PMID<id>.json` stores one structured study per file.
- `raw/pubmed/xml/` and `raw/pubmed/abstracts/` preserve original PubMed responses.
- `research/indexes/` contains generated indexes. Do not edit these manually.
- `pipelines/pubmed/` contains modular ingestion steps.
- `docs/` remains the GitHub Pages source so existing URLs keep working.

## PubMed Ingestion

Install dependencies once:

```bash
pip install -r requirements.txt
```

Run the full pipeline:

```bash
python -m pipelines.pubmed.ingest --limit 25
```

Run individual stages:

```bash
python -m pipelines.pubmed.discover --json
python -m pipelines.pubmed.fetch <PMID>
python -m pipelines.pubmed.extract <PMID>
python -m pipelines.pubmed.validate
python -m pipelines.pubmed.index
python scripts/generate_study_pages.py
python -m scripts.check_raw_coverage
```

Rebuild every study record from the raw captures already in `raw/pubmed/`, without
refetching from PubMed (`--all` also rebuilds PMIDs that already have a record):

```bash
python -m scripts.extract_studies_from_raw --all
```

Extraction has two paths. `pipelines.pubmed.extract` asks an LLM to fill the
interpretive fields; `scripts.extract_studies_from_raw` derives everything from the
XML and abstract with no API key. Ingestion tries the LLM first and falls back to the
abstract rules, so a fetched paper always produces a record even when the LLM call
fails, and any capture still missing a record is backfilled at the end of the run.

The daily GitHub Action uses repository secrets for PubMed and LLM access:

- `OPENROUTER_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `PUBMED_EMAIL`
- `PUBMED_TOOL_NAME`

Set `AI_PROVIDER` and `AI_MODEL` as repository variables when a provider or model override is needed.

## Data Rules

- Never overwrite raw PubMed XML or abstract files.
- Store each study as an individual JSON document.
- Use `null` for unknown scalar values and `[]` for unknown lists. Never substitute a
  guessed value for a missing one.
- Read an article's DOI from `Article/ELocationID` or `PubmedData/ArticleIdList`, never
  from a `.//ArticleId` descendant sweep: `ReferenceList` carries one DOI per cited
  reference, so a sweep returns the bibliography's DOIs.
- `study_type` is a study design or `null`; PubMed container types such as
  `Journal Article` are not designs.
- Age ranges always carry their unit (`age_min`/`age_max`/`age_unit`), because `24-60`
  months and `7-13` years are indistinguishable without it.
- `python -m pipelines.pubmed.validate` checks records against
  `schemas/study.schema.json`, which is the contract.
- Every raw capture must have a study record. `python -m scripts.check_raw_coverage`
  enforces it and the daily Action runs it, so a fetched paper cannot sit unpublished.
- XML-derived fields (`doi`, `study_type`, `year`, `title`, `journal`, `authors`,
  `mesh_terms`, `keywords`, `co_occurring_conditions`) are authoritative. The LLM
  extractor fills the interpretive fields only and cannot overwrite them.
- Regenerate indexes after ingestion instead of editing them manually.
- `participants` is the total number of people enrolled, or `null` — never a single
  trial arm, and never a count of observations or of other studies.
  `python -m scripts.check_participants` holds it to a hand-read fixture of every
  abstract.
- `trust_tier`, `trust_tier_label` and `easy_explainer` are derived in
  `normalize_study()` and must never be hand-edited. Tier 4 means "design not stated";
  a small sample demotes one step but never past tier 3.
  `python -m scripts.check_explainer` enforces the corpus invariants.
- `domain` is one of the platform's eight knowledge domains (`adaptive`, `behaviour`,
  `cognitive`, `communication`, `general`, `motor`, `sensory`, `social`) and is a
  reviewed editorial judgement, never inferred from MeSH terms or keywords. It is
  read from `config/study_domains.json` (PMID -> domain) by `normalize_study()`, so a
  PMID with no reviewed entry has no domain and fails validation rather than
  defaulting to `general`. `python -m scripts.check_domain` enforces this.
