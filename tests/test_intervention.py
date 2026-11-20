"""Title phrasing alone does not make something an intervention.

"Effects of X on Y" and "X improves Y" also describe risk factors and exposures.
The hand-read fixture (scripts/check_intervention.py) has no such title yet, so
these cover the shapes the next ingestion run could bring.
"""

import pytest

from scripts.extract_studies_from_raw import infer_intervention


@pytest.mark.parametrize(
    "title",
    [
        "Effects of maternal obesity on autism risk in offspring: a cohort study.",
        "Effects of sex differences on diagnostic delay in autism.",
        "Screen time increases sleep problems in autistic preschoolers.",
        "Effect of birth order on autism severity.",
        "Home Polysomnography in Children With Autism Spectrum Disorder: A Prospective Observational Study.",
    ],
)
def test_risk_factor_titles_have_no_intervention(title):
    assert infer_intervention(title, "", ["ADHD", "Biomarker"]) is None


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Effects of VR-Based Serious Games on Gross Motor Skills in Children.", "VR-Based Serious Games"),
        ("Visual Perspective Taking Training Improves Theory of Mind in Autistic Children.", "Visual Perspective Taking Training"),
        ("A Randomized Trial of Omega-3 Fatty Acids for Irritability in Autism.", "Omega-3 Fatty Acids"),
    ],
)
def test_named_interventions_are_read_from_the_title(title, expected):
    assert infer_intervention(title, "", []) == expected
