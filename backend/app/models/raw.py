"""Pydantic v2 models for the RAW founder profile schema.

Mirrors data/raw/sample.json exactly. Every field is optional/nullable: the
source data is messy and PLAN A5/A6 require that absence is representable, never
an import error. Unknown extra fields are preserved (extra="allow") so nothing in
the source is silently dropped.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Raw(BaseModel):
    """Base for raw schemas. `extra="allow"` deliberately: an unrecognised
    supplier field is KEPT so it stays citable and auditable, rather than being
    silently dropped on the way in."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class RawExperience(_Raw):
    """One supplied experience entry, unmodified. Every field is optional —
    absence is normal and is handled downstream as missing data, not as zero."""

    title: str | None = None
    position_title: str | None = None
    department: str | None = None
    management_level: str | None = None
    location: str | None = None
    order_in_profile: int | None = None

    # dates: both the string form ("03/2023") and the decomposed form appear
    date_from: str | None = None
    date_to: str | None = None
    date_from_year: int | None = None
    date_from_month: int | None = None
    date_to_year: int | None = None
    date_to_month: int | None = None
    duration: str | None = None
    duration_months: int | None = None

    # currentness: two independent, sometimes contradictory, indicators
    is_current: int | None = None
    active_experience: int | None = None

    # company
    company_id: str | None = None
    company_name: str | None = None
    company_type: str | None = None
    company_url: str | None = None
    company_website: str | None = None
    company_logo_url: str | None = None
    company_linkedin_url: str | None = None
    company_industry: str | None = None
    company_categories_and_keywords: list[str] | None = None
    company_is_b2b: int | None = None
    company_size_range: str | None = None
    company_employees_count: int | None = None
    company_employees_count_change_yearly_percentage: float | None = None
    company_followers_count: int | None = None
    company_founded_year: int | None = None
    company_stock_ticker: list[str] | None = None
    company_twitter_url: list[str] | None = None
    company_facebook_url: list[str] | None = None
    company_last_updated_at: str | None = None
    company_last_funding_round_date: str | None = None
    company_last_funding_round_amount_raised: float | None = None
    company_annual_revenue_source_1: float | None = None
    company_annual_revenue_source_5: float | None = None
    company_annual_revenue_currency_source_1: str | None = None
    company_annual_revenue_currency_source_5: str | None = None

    # company HQ
    company_hq_city: str | None = None
    company_hq_state: str | None = None
    company_hq_street: str | None = None
    company_hq_zipcode: str | None = None
    company_hq_country: str | None = None
    company_hq_country_iso2: str | None = None
    company_hq_country_iso3: str | None = None
    company_hq_full_address: str | None = None
    company_hq_regions: list[str] | None = None


class RawEducation(_Raw):
    """One supplied education entry, unmodified."""

    degree: str | None = None
    field_of_study: str | None = None
    order_in_profile: int | None = None

    date_from: str | None = None
    date_to: str | None = None
    date_from_year: int | None = None
    date_to_year: int | None = None

    school_name: str | None = None
    school_url: str | None = None
    institution_name: str | None = None
    institution_url: str | None = None
    institution_logo_url: str | None = None
    institution_city: str | None = None
    institution_state: str | None = None
    institution_street: str | None = None
    institution_zipcode: str | None = None
    institution_full_address: str | None = None
    institution_country_iso2: str | None = None
    institution_country_iso3: str | None = None
    institution_regions: list[str] | None = None


class SyntheticTag(_Raw):
    """Present ONLY on generated data. Never on real records."""

    source: Literal["load", "golden"] | str | None = None
    messiness: list[str] = Field(default_factory=list)
    notes: str | None = None


class RawProfile(_Raw):
    """One supplied founder record, as received.

    This is the stored source of truth: `/rescore` re-runs from RAW rather than
    from the canonical profile, because tier lists and taxonomies change
    NORMALIZATION and not merely scoring. Identity hashes live here and are
    withheld from the LLM payload by `prompt.WITHHELD_RAW_FIELDS`."""

    mdm_person_id: str | None = None

    # identity hashes (PII is pre-hashed upstream)
    name_hash: str | None = None
    email_hash: str | None = None
    phone_hash: str | None = None
    linkedin_hash: str | None = None
    github_hash: str | None = None
    twitter_hash: str | None = None
    facebook_hash: str | None = None
    crunchbase_hash: str | None = None
    public_profile_id_hash: str | None = None
    professional_emails_hashed: list[str] | None = None

    headline: str | None = None
    experience: list[RawExperience] | None = None
    education: list[RawEducation] | None = None
    total_experience_duration_months: int | None = None

    location_country: str | None = None
    location_state: str | None = None
    location_city: str | None = None

    synthetic: SyntheticTag | None = Field(default=None, alias="_synthetic")

    @property
    def is_synthetic(self) -> bool:
        """True for generated demo/load records, which carry a `_synthetic` tag.
        Nothing synthetic is ever presented as a real candidate."""
        return self.synthetic is not None

    def raw_dict(self) -> dict[str, Any]:
        """Round-trip back to the source shape. `_synthetic` only appears when
        the record actually carries the tag, so real data stays byte-shaped."""
        out = self.model_dump(by_alias=True, exclude_none=False)
        if out.get("_synthetic") is None:
            out.pop("_synthetic", None)
        return out


def load_profiles(path: str) -> list[RawProfile]:
    """Load a JSON array of raw profiles. Raises on schema violation."""
    import json

    with open(path) as fh:
        payload = json.load(fh)
    if not isinstance(payload, list):
        raise ValueError(f"{path}: expected a JSON array of profiles")
    return [RawProfile.model_validate(item) for item in payload]
