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
```

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
- Use `null` for unknown scalar values and `[]` for unknown lists.
- Regenerate indexes after ingestion instead of editing them manually.
