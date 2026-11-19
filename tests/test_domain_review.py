"""A raw capture with no reviewed domain waits for review; it is not a failure.

`domain` is a founder-reviewed editorial judgement read from
config/study_domains.json, so a paper fetched today cannot have one until someone
reviews it. Before this rule was explicit, every new capture failed schema
validation in the backfill and the coverage check turned the daily run red.
"""

from pipelines.pubmed import ingest
from scripts import check_raw_coverage


def test_coverage_separates_awaiting_review_from_real_orphans():
    raw = {"1", "2", "3", "4"}
    recorded = {"1"}
    reviewed = {"1": "general", "2": "motor"}

    orphans, awaiting = check_raw_coverage.classify(raw, recorded, reviewed)

    # PMID2 has a reviewed domain but no record: extraction really failed.
    assert orphans == ["2"]
    # PMID3 and PMID4 were never reviewed, so they cannot have a record yet.
    assert awaiting == ["3", "4"]


def test_backfill_reports_unreviewed_capture_instead_of_failing(monkeypatch):
    monkeypatch.setattr(ingest, "raw_pmids", lambda: ["10", "11"])
    monkeypatch.setattr(ingest, "load_study_domains", lambda: {"10": "social"})
    monkeypatch.setattr(ingest, "raw_title", lambda pmid: f"Title {pmid}")
    built = []

    def fake_build(pmid):
        built.append(pmid)
        return {"pmid": pmid, "doi": None, "domain": "social"}

    monkeypatch.setattr(ingest, "build_study", fake_build)
    monkeypatch.setattr(ingest, "validate_study", lambda study: [])
    monkeypatch.setattr(ingest, "save_study", lambda study: f"PMID{study['pmid']}.json")
    summary = ingest.new_summary()

    ingest.backfill_orphans(summary, seen_pmids=set(), seen_dois=set())

    assert built == ["10"]
    assert summary["backfilled"] == 1
    assert summary["validation_failures"] == 0
    assert summary["awaiting_domain_review"] == [{"pmid": "11", "title": "Title 11"}]
