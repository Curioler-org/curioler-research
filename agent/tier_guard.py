"""The code backstop for the trust-tier rule.

Blueprint Knowledge-Architecture.md §Trust Tiers (2026-10-10): Tier 1-2 need
published, peer-reviewed research that studied the topic itself; unpublished
results (press releases, news, conference talks, trial-registry listings,
preprints, company pages) cap at Tier 4.

Whether a source studied the topic is the model's judgment and lives in the
prompts. What code can check is the floor under it: a Tier 1-2 draft must
cite at least one source the model itself classified as peer-reviewed. If it
does not, the tier is lowered here and the run says so, whatever the model
argued.
"""

from __future__ import annotations

PEER_REVIEWED = {"journal_article", "systematic_review"}
CONSENSUS = {"guideline"}

SOURCE_TYPES = (
    "systematic_review",  # systematic review or meta-analysis in a journal
    "journal_article",    # any other peer-reviewed, published study
    "guideline",          # professional guideline or consensus statement
    "preprint",           # medRxiv, bioRxiv, Research Square, SSRN ...
    "registry",           # ClinicalTrials.gov, CTRI, ISRCTN ...
    "conference",         # conference presentation, poster or abstract
    "press_or_news",      # press release, news story, trade press
    "company",            # a maker's or seller's own page
    "other",              # clinic blog, charity page, anything else
)

SOURCE_TYPE_PROMPT = (
    'Give every source a "source_type", exactly one of: '
    + ", ".join(f'"{t}"' for t in SOURCE_TYPES)
    + '. "journal_article" and "systematic_review" mean published in a '
    "peer-reviewed journal; a trial whose results are known only from a "
    'registry, a press release or a conference is "registry", '
    '"press_or_news" or "conference", never "journal_article".'
)


def cap_tier(data: dict, labels: dict[int, str] | None = None) -> str | None:
    """Lower a Tier 1-2 tier that no peer-reviewed source supports.

    Changes `data` in place. Returns a one-line reason when it lowered the
    tier, None when the tier stands. `labels` maps tier to the label the
    caller writes beside it; omit it for outputs that carry no label.
    """
    tier = data.get("trust_tier")
    if not isinstance(tier, int) or tier > 2:
        return None

    types = {str(s.get("source_type", "")).strip() for s in data.get("sources") or []}
    if types & PEER_REVIEWED:
        return None

    new_tier = 3 if types & CONSENSUS else 4
    data["trust_tier"] = new_tier
    if labels and "trust_tier_label" in data:
        data["trust_tier_label"] = labels[new_tier]
    found = ", ".join(sorted(t for t in types if t)) or "none given"
    return (
        f"Trust tier lowered from {tier} to {new_tier}: no source is a "
        f"peer-reviewed journal article (source types: {found})."
    )
