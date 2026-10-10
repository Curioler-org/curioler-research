from tier_guard import cap_tier

LABELS = {3: "Clinical consensus or professional guideline", 4: "Expert commentary or opinion, not peer-reviewed"}


def l1_79_draft() -> dict:
    # The sources of the first topic request's draft (request 05519778), as
    # the generator should now classify them: the trial's results were known
    # only from a registry, press and a conference.
    return {
        "trust_tier": 2,
        "trust_tier_label": "Peer-reviewed study, smaller RCT, clinical trial",
        "sources": [
            {"url": "https://clinicaltrials.gov/study/x", "source_type": "registry"},
            {"url": "https://www.biospace.com/x", "source_type": "press_or_news"},
            {"url": "https://www.hcplive.com/x", "source_type": "conference"},
            {"url": "https://www.withpower.com/x", "source_type": "company"},
        ],
    }


def test_unpublished_trial_drops_to_tier_4():
    data = l1_79_draft()
    reason = cap_tier(data, LABELS)
    assert data["trust_tier"] == 4
    assert data["trust_tier_label"] == LABELS[4]
    assert reason and "from 2 to 4" in reason


def test_journal_source_keeps_the_tier():
    data = l1_79_draft()
    data["sources"].append({"url": "https://pubmed.ncbi.nlm.nih.gov/1", "source_type": "journal_article"})
    assert cap_tier(data, LABELS) is None
    assert data["trust_tier"] == 2


def test_guideline_only_drops_to_tier_3():
    data = {"trust_tier": 1, "sources": [{"source_type": "guideline"}, {"source_type": "other"}]}
    assert cap_tier(data) is not None
    assert data["trust_tier"] == 3
    assert "trust_tier_label" not in data


def test_missing_source_types_count_as_not_peer_reviewed():
    data = {"trust_tier": 1, "sources": [{"url": "https://pmc.ncbi.nlm.nih.gov/x"}]}
    cap_tier(data)
    assert data["trust_tier"] == 4


def test_tier_3_and_above_are_left_alone():
    data = {"trust_tier": 4, "sources": []}
    assert cap_tier(data) is None
    assert data["trust_tier"] == 4
