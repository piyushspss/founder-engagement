"""Fix 2: an industry string present but unrecognised by the starter taxonomy is
UNKNOWN, not "not healthcare"."""

import pytest

from app.evidence import compute_confidence, compute_signals
from app.models.canonical import FlagCode, Ternary
from app.models.raw import RawProfile
from app.normalize import load_config, normalize

CFG = load_config()


def role(**kw):
    b = {"position_title": "Analyst", "company_name": "Northwind Co",
         "company_industry": "Hospital & Health Care", "management_level": "Manager",
         "company_employees_count": 120, "company_size_range": "51-200 employees",
         "date_from": "01/2018", "date_from_year": 2018, "date_from_month": 1,
         "date_to": "01/2022", "date_to_year": 2022, "date_to_month": 1,
         "duration_months": 48}
    b.update(kw)
    return b


def prof(**kw):
    base = {"mdm_person_id": "p", "headline": "t", "experience": [], "education": [],
            "total_experience_duration_months": 48, "location_country": "United States"}
    base.update(kw)
    return normalize(RawProfile.model_validate(base), CFG)


@pytest.mark.parametrize("industry", ["Hospital & Health Care", "Medical Devices",
                                      "Pharmaceuticals", "Biotechnology"])
def test_recognised_health_is_yes(industry):
    assert prof(experience=[role(company_industry=industry)]).roles[0].health_flag is Ternary.YES


@pytest.mark.parametrize("industry", ["Computer Software", "Financial Services",
                                      "Retail", "Logistics and Supply Chain"])
def test_recognised_non_health_is_no(industry):
    assert prof(experience=[role(company_industry=industry)]).roles[0].health_flag is Ternary.NO


@pytest.mark.parametrize("industry", ["Widget Fabrication", "Artisanal Cheese",
                                      "Quantum Basketweaving"])
def test_unrecognised_present_industry_is_unknown_not_no(industry):
    c = prof(experience=[role(company_industry=industry, company_categories_and_keywords=[])])
    assert c.roles[0].health_flag is Ternary.UNKNOWN
    flag = next(f for f in c.quality_flags if f.code == FlagCode.UNKNOWN_INDUSTRY)
    assert "not in the starter taxonomy" in flag.detail


def test_missing_industry_is_unknown():
    c = prof(experience=[role(company_industry=None, company_categories_and_keywords=[])])
    assert c.roles[0].health_flag is Ternary.UNKNOWN


def test_unknown_yields_zero_healthcare_evidence_same_as_non_health():
    unknown = compute_signals(prof(experience=[role(company_industry="Widget Fabrication",
                                                    company_categories_and_keywords=[])]), CFG)[1]
    nonhealth = compute_signals(prof(experience=[role(company_industry="Retail")]), CFG)[1]
    assert unknown.value == nonhealth.value == 0.0


def test_unknown_is_never_negative():
    unknown = compute_signals(prof(experience=[role(company_industry="Widget Fabrication",
                                                    company_categories_and_keywords=[])]), CFG)[1]
    assert unknown.value >= 0.0


def test_unknown_does_not_claim_company_domain_coverage():
    """The whole point of the fix: we may not bank confidence for a
    classification we did not actually make."""
    classified = compute_confidence(prof(experience=[role(company_industry="Retail")]), CFG)
    unclassified = compute_confidence(
        prof(experience=[role(company_industry="Widget Fabrication",
                              company_categories_and_keywords=[])]), CFG)
    # v2.2 Amendment 1 split this component into industry_classified +
    # scope_available, so the CP3 assertion now lives on the sub-component it
    # was always about. The intent is unchanged: an unmade classification banks
    # no coverage. The role still carries a company size, which is why the
    # top-level mean is 0.5 rather than 0.0.
    assert classified.coverage_subcomponents[
        "company_domain_classification"]["industry_classified"] == 1.0
    assert unclassified.coverage_subcomponents[
        "company_domain_classification"]["industry_classified"] == 0.0
    assert unclassified.coverage_components["company_domain_classification"] < \
        classified.coverage_components["company_domain_classification"]
    assert unclassified.confidence < classified.confidence


def test_recognised_non_health_still_claims_full_coverage():
    cb = compute_confidence(prof(experience=[role(company_industry="Computer Software")]), CFG)
    assert cb.coverage_subcomponents[
        "company_domain_classification"]["industry_classified"] == 1.0


def test_health_keywords_still_rescue_a_missing_industry():
    c = prof(experience=[role(company_industry=None,
                              company_categories_and_keywords=["digital health"])])
    assert c.roles[0].health_flag is Ternary.YES
