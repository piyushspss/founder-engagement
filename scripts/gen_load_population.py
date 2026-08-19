#!/usr/bin/env python3
"""Generate the synthetic LOAD population -> data/synthetic/load_800.json.

Purpose (PLAN §1, "Dataset tiny; generate synthetic w/ same properties"): a
~800-profile population for demo, load and distribution checks. This is NOT the
evaluation set — the hand-built golden set (data/golden/) is authored separately
in Checkpoint 6 and is the only thing eval numbers are computed on.

Design rules:
  * Schema is identical to data/raw/sample.json (same keys, same types).
  * Per-field null rates are taken from the observed sample: a field that is
    always null in the sample stays null; a field always populated in the sample
    stays populated EXCEPT where a messiness injection deliberately removes it.
  * Every record carries a top-level "_synthetic" tag naming its messiness, so
    synthetic data can never be mistaken for real data.
  * Messiness types are exactly PLAN A6: missing dates, is_current null vs
    date_to null, overlapping roles, degree-string variance, institution name
    variants, duplicate persons (matching / conflicting hashes), out-of-order
    experiences, total months != sum of roles.

Usage: python scripts/gen_load_population.py [--n 800] [--seed 20260819]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "raw" / "sample.json"
OUT = ROOT / "data" / "synthetic" / "load_800.json"

TODAY_YEAR, TODAY_MONTH = 2026, 8

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------
HEALTH_INDUSTRIES = [
    "Hospital & Health Care", "Medical Devices", "Pharmaceuticals",
    "Biotechnology", "Mental Health Care", "Health Insurance",
    "Health, Wellness and Fitness", "Medical Practice",
]
NONHEALTH_INDUSTRIES = [
    "Computer Software", "Information Technology and Services", "Financial Services",
    "Management Consulting", "Retail", "Logistics and Supply Chain",
    "Marketing and Advertising", "Telecommunications",
]
SIZE_RANGES = [
    ("1-10 employees", 1, 10), ("11-50 employees", 11, 50),
    ("51-200 employees", 51, 200), ("201-500 employees", 201, 500),
    ("501-1000 employees", 501, 1000), ("1001-5000 employees", 1001, 5000),
    ("5001-10000 employees", 5001, 10000), ("10001+ employees", 10001, 60000),
]
MGMT_LEVELS = ["Training", "Entry", "Specialist", "Senior", "Manager", "Director", "VP", "C-Level"]

COMPANY_PREFIX = [
    "Fieldstone", "Marlowe", "Bright Path", "Cobalt Ridge", "Sable Creek", "Northwind",
    "Larkspur", "Ironwood", "Quiet Harbor", "Redstone", "Alder", "Beacon Hill",
    "Copperline", "Dunmore", "Everglade", "Foxglove", "Grayling", "Hollowell",
    "Juniper", "Kestrel", "Lantern", "Meridian", "Nightingale", "Orchard",
    "Pinecrest", "Quarry", "Rosewood", "Stillwater", "Thornbury", "Umberly",
    "Vireo", "Westmark", "Yarrow", "Zephyr", "Amberline", "Blackwater",
]
HEALTH_SUFFIX = ["Health", "Health Systems", "Care", "Medical Group", "Regional Hospital",
                 "Therapeutics", "Diagnostics", "Bio", "Clinical Partners", "Health Network"]
TECH_SUFFIX = ["Analytics", "Labs", "Systems", "Software", "Technologies", "Data", "Digital", "Works"]

TIER1_HEALTH = ["Mayo Clinic", "Cleveland Clinic", "Kaiser Permanente", "Optum",
                "Flatiron Health", "Teladoc Health", "Oscar Health", "Tempus"]
TIER2_HEALTH = ["Athenahealth", "One Medical", "Omada Health", "Spring Health",
                "Carbon Health", "Cedar", "Komodo Health", "Included Health"]

TIER1_SCHOOLS = ["Harvard University", "Stanford University",
                 "Massachusetts Institute of Technology", "Johns Hopkins University",
                 "University of Pennsylvania", "Yale University", "Duke University"]
TIER2_SCHOOLS = ["Cornell University", "Northwestern University", "University of Michigan",
                 "Carnegie Mellon University", "Emory University", "New York University"]
UNKNOWN_SCHOOLS = ["Cobalt Ridge University", "Sable Creek State University",
                   "Larkspur College", "Ironwood State University", "Quiet Harbor University",
                   "Dunmore College", "Grayling State University", "Pinecrest University"]

# PLAN A6: institution name variants (fuzzy-match targets)
SCHOOL_VARIANTS = {
    "Massachusetts Institute of Technology": ["MIT", "M.I.T.", "Massachusetts Inst. of Technology"],
    "Harvard University": ["Harvard", "Harvard Business School", "Harvard Univ."],
    "Stanford University": ["Stanford", "Stanford GSB", "Stanford Univ"],
    "University of Pennsylvania": ["Penn", "The Wharton School", "UPenn"],
    "Johns Hopkins University": ["Johns Hopkins", "JHU", "Johns Hopkins Univ."],
    "Carnegie Mellon University": ["CMU", "Carnegie-Mellon University"],
    "New York University": ["NYU", "New York Univ"],
}

# PLAN A6: degree-string variance — many spellings of the same credential
DEGREE_VARIANTS = {
    "BS": ["Bachelor's degree, {field}", "BS, {field}", "B.S. {field}", "Bachelor of Science, {field}",
           "Bachelors {field}", "BSc {field}"],
    "BA": ["Bachelor of Arts, {field}", "BA, {field}", "B.A. in {field}", "Bachelor's degree, {field}"],
    "BSN": ["Bachelor of Science in Nursing", "BSN", "B.S.N., Nursing", "Bachelor's degree, Nursing"],
    "RN": ["Registered Nurse (RN)", "RN", "Nursing Diploma, Registered Nurse", "R.N."],
    "MBA": ["MBA", "Master of Business Administration", "M.B.A., {field}",
            "Master's degree, Business Administration", "MBA, {field}"],
    "MS": ["Master of Science, {field}", "MS, {field}", "M.S. {field}", "Master's degree, {field}", "MSc {field}"],
    "MD": ["Doctor of Medicine (MD)", "MD", "M.D.", "Doctor of Medicine, {field}"],
    "DO": ["Doctor of Osteopathic Medicine (DO)", "DO", "D.O."],
    "PhD": ["PhD, {field}", "Doctor of Philosophy (PhD), {field}", "Ph.D. {field}",
            "Doctorate, {field}"],
    "OTHER": ["Certificate, {field}", "Coursework, {field}", "{field}", "Postgraduate Diploma, {field}"],
}

CITIES = [("Austin", "Texas"), ("Denver", "Colorado"), ("Boston", "Massachusetts"),
          ("New York", "New York"), ("Chicago", "Illinois"), ("San Francisco", "California"),
          ("Seattle", "Washington"), ("Nashville", "Tennessee"), ("Cincinnati", "Ohio"),
          ("Atlanta", "Georgia"), ("Minneapolis", "Minnesota"), ("Philadelphia", "Pennsylvania")]

DEPARTMENTS = {
    "product": "Product", "engineering": "Engineering", "clinical": "Nursing",
    "medical": "Medical", "operations": "Operations", "sales": "Sales",
    "marketing": "Marketing", "research": "Research", "finance": "Finance",
    "executive": "Executive",
}

# --------------------------------------------------------------------------
# Personas: (name, weight, spec)
# --------------------------------------------------------------------------
PERSONAS = [
    "repeat_founder", "single_founder", "founder_early", "clinical_rn", "clinician_md",
    "healthcare_operator", "product_builder", "technical_builder", "commercial_gtm",
    "scientific_researcher", "ceo_not_founder", "junior_thin", "career_switcher",
]
PERSONA_WEIGHTS = [3, 7, 4, 9, 5, 11, 14, 13, 9, 5, 5, 10, 5]


def _hash(*parts: object) -> str:
    """Deterministic fake identity hash. Seeded, so the population is
    reproducible — and fake, so no value here identifies a real person."""
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


class Gen:
    """Seeded generator for synthetic profile parts.

    Every draw goes through the injected `rng`, so the whole population is
    reproducible from `--seed` alone."""

    def __init__(self, rng: random.Random):
        self.rng = rng

    # ---------------- companies ----------------
    def company(self, health: bool, big: bool | None = None, tiered: bool = False) -> dict:
        """A synthetic company: name, industry, size, revenue, growth."""
        rng = self.rng
        if tiered and health:
            name = rng.choice(TIER1_HEALTH if rng.random() < 0.4 else TIER2_HEALTH)
            # named health systems/payers are not randomly "Biotechnology"
            industry = rng.choices(
                ["Hospital & Health Care", "Health Insurance", "Medical Practice"],
                weights=[6, 2, 2])[0]
        else:
            pre = rng.choice(COMPANY_PREFIX)
            name = f"{pre} {rng.choice(HEALTH_SUFFIX if health else TECH_SUFFIX)}"
            industry = rng.choice(HEALTH_INDUSTRIES if health else NONHEALTH_INDUSTRIES)
        if big is None:
            idx = rng.choices(range(len(SIZE_RANGES)), weights=[6, 12, 20, 18, 14, 14, 9, 7])[0]
        else:
            idx = rng.randint(5, 7) if big else rng.randint(0, 3)
        size_range, lo, hi = SIZE_RANGES[idx]
        employees = rng.randint(lo, hi)
        city, state = rng.choice(CITIES)
        founded = rng.randint(1960, 2022) if rng.random() < 0.9 else None
        revenue = int(employees * rng.uniform(35000, 220000)) if rng.random() < 0.85 else None
        return {
            "name": name, "industry": industry, "size_range": size_range,
            "employees": employees, "city": city, "state": state, "founded": founded,
            "revenue": revenue, "growth": round(rng.uniform(-8, 45), 1) if rng.random() < 0.8 else None,
            "followers": int(employees * rng.uniform(10, 40)),
        }

    def experience_block(self, comp: dict, title: str, dept: str, level: str,
                         start: tuple[int, int], end: tuple[int, int] | None,
                         order: int, is_current: bool) -> dict:
        """One synthetic `experience[]` entry in the supplied raw schema."""
        sy, sm = start
        if end is None:
            ey, em = TODAY_YEAR, TODAY_MONTH
        else:
            ey, em = end
        months = max(1, (ey - sy) * 12 + (em - sm))
        e = {
            "title": None,
            "date_to": None if end is None else f"{end[1]:02d}/{end[0]}",
            "duration": None,
            "location": f"{comp['city']}, {comp['state']}",
            "date_from": f"{sm:02d}/{sy}",
            "company_id": None,
            "department": dept,
            "is_current": 1 if is_current else None,
            "company_url": None,
            "company_name": comp["name"],
            "company_type": self.rng.choice(["Privately Held", "Privately Held", "Public Company",
                                             "Nonprofit", "Partnership"]),
            "date_to_year": None if end is None else end[0],
            "date_to_month": None if end is None else end[1],
            "company_is_b2b": self.rng.choice([1, 1, 0]),
            "date_from_year": sy,
            "position_title": title,
            "company_hq_city": comp["city"],
            "company_website": None,
            "date_from_month": sm,
            "duration_months": months,
            "company_hq_state": comp["state"],
            "company_industry": comp["industry"],
            "company_logo_url": None,
            "management_level": level,
            "order_in_profile": order,
            "active_experience": 1 if is_current else None,
            "company_hq_street": None,
            "company_hq_country": "United States",
            "company_hq_regions": ["Americas", "Northern America", "AMER"],
            "company_hq_zipcode": None,
            "company_size_range": comp["size_range"],
            "company_twitter_url": [],
            "company_facebook_url": [],
            "company_founded_year": comp["founded"],
            "company_linkedin_url": None,
            "company_stock_ticker": [],
            "company_employees_count": comp["employees"],
            "company_followers_count": comp["followers"],
            "company_hq_country_iso2": "US",
            "company_hq_country_iso3": "USA",
            "company_hq_full_address": None,
            "company_last_updated_at": "2026-04-25",
            "company_annual_revenue_source_1": None,
            "company_annual_revenue_source_5": comp["revenue"],
            "company_categories_and_keywords": [comp["industry"].lower()],
            "company_last_funding_round_date": None,
            "company_annual_revenue_currency_source_1": None,
            "company_annual_revenue_currency_source_5": "USD" if comp["revenue"] else None,
            "company_last_funding_round_amount_raised": None,
            "company_employees_count_change_yearly_percentage": comp["growth"],
        }
        return e

    def education_entry(self, institution: str, degree_key: str, field: str,
                        end_year: int, order: int, variant: bool) -> dict:
        """One synthetic `education[]` entry. `variant=True` may emit a real-world
        NAME VARIANT, which is what exercises fuzzy institution matching."""
        rng = self.rng
        name = institution
        if variant and institution in SCHOOL_VARIANTS and rng.random() < 0.7:
            name = rng.choice(SCHOOL_VARIANTS[institution])
        degree = rng.choice(DEGREE_VARIANTS[degree_key]).format(field=field)
        city, state = rng.choice(CITIES)
        years = 4 if degree_key in ("BS", "BA", "BSN") else rng.choice([1, 2, 2, 3, 5])
        return {
            "degree": degree,
            "date_to": None,
            "date_from": None,
            "school_url": None,
            "school_name": None,
            "date_to_year": end_year,
            "date_from_year": end_year - years,
            "field_of_study": field,
            "institution_url": None,
            "institution_city": city,
            "institution_name": name,
            "order_in_profile": order,
            "institution_state": state,
            "institution_street": None,
            "institution_regions": ["Americas", "Northern America", "AMER"],
            "institution_zipcode": None,
            "institution_logo_url": None,
            "institution_country_iso2": "US",
            "institution_country_iso3": "USA",
            "institution_full_address": None,
        }


# --------------------------------------------------------------------------
# Persona -> career track
# --------------------------------------------------------------------------
TRACKS: dict[str, dict] = {
    "repeat_founder": dict(
        titles=[("Co-Founder & CEO", "Executive", "C-Level"), ("Founder & CTO", "Executive", "C-Level"),
                ("Senior Engineer", "Engineering", "Senior")],
        health_bias=0.6, n_roles=(3, 4), degrees=["BS", "MBA"], school_tier=(0.35, 0.3)),
    "single_founder": dict(
        titles=[("Founder & CEO", "Executive", "C-Level"), ("Director of Product", "Product", "Director"),
                ("Product Manager", "Product", "Manager")],
        health_bias=0.6, n_roles=(2, 4), degrees=["BS", "MBA"], school_tier=(0.3, 0.3)),
    "founder_early": dict(
        titles=[("Founding Engineer", "Engineering", "Senior"), ("Software Engineer", "Engineering", "Entry")],
        health_bias=0.4, n_roles=(2, 3), degrees=["BS"], school_tier=(0.2, 0.3)),
    "clinical_rn": dict(
        titles=[("Clinical Operations Lead", "Operations", "Manager"),
                ("Registered Nurse", "Nursing", "Specialist"),
                ("Staff Nurse", "Nursing", "Entry")],
        health_bias=1.0, n_roles=(2, 3), degrees=["BSN", "RN"], school_tier=(0.05, 0.15)),
    "clinician_md": dict(
        titles=[("Chief Medical Officer", "Medical", "C-Level"), ("Attending Physician", "Medical", "Specialist"),
                ("Resident Physician", "Medical", "Training")],
        health_bias=1.0, n_roles=(2, 4), degrees=["MD", "BS"], school_tier=(0.45, 0.3)),
    "healthcare_operator": dict(
        titles=[("VP of Operations", "Operations", "VP"), ("Director of Operations", "Operations", "Director"),
                ("Operations Manager", "Operations", "Manager"), ("Operations Analyst", "Operations", "Entry")],
        health_bias=0.9, n_roles=(2, 4), degrees=["BS", "MBA"], school_tier=(0.2, 0.35)),
    "product_builder": dict(
        titles=[("VP of Product", "Product", "VP"), ("Director of Product", "Product", "Director"),
                ("Senior Product Manager", "Product", "Senior"), ("Product Manager", "Product", "Manager"),
                ("Associate Product Manager", "Product", "Entry")],
        health_bias=0.5, n_roles=(2, 4), degrees=["BS", "MBA"], school_tier=(0.2, 0.3)),
    "technical_builder": dict(
        titles=[("VP of Engineering", "Engineering", "VP"), ("Engineering Manager", "Engineering", "Manager"),
                ("Staff Software Engineer", "Engineering", "Senior"),
                ("Software Engineer", "Engineering", "Entry")],
        health_bias=0.4, n_roles=(2, 4), degrees=["BS", "MS"], school_tier=(0.25, 0.3)),
    "commercial_gtm": dict(
        titles=[("VP of Sales", "Sales", "VP"), ("Director of Business Development", "Sales", "Director"),
                ("Account Executive", "Sales", "Senior"), ("Marketing Manager", "Marketing", "Manager")],
        health_bias=0.5, n_roles=(2, 4), degrees=["BA", "MBA"], school_tier=(0.15, 0.3)),
    "scientific_researcher": dict(
        titles=[("Principal Scientist", "Research", "Senior"), ("Research Scientist", "Research", "Specialist"),
                ("Postdoctoral Researcher", "Research", "Training")],
        health_bias=0.95, n_roles=(2, 3), degrees=["PhD", "BS"], school_tier=(0.5, 0.3)),
    "ceo_not_founder": dict(  # A8 adversarial: leadership evidence, NOT founder evidence
        titles=[("Chief Executive Officer", "Executive", "C-Level"), ("President", "Executive", "C-Level"),
                ("Managing Director", "Executive", "Director")],
        health_bias=0.6, n_roles=(2, 3), degrees=["BS", "MBA"], school_tier=(0.3, 0.3)),
    "junior_thin": dict(
        titles=[("Analyst", "Operations", "Entry"), ("Associate", "Operations", "Entry"),
                ("Coordinator", "Operations", "Training")],
        health_bias=0.4, n_roles=(1, 2), degrees=["BA", "BS"], school_tier=(0.08, 0.2)),
    "career_switcher": dict(
        titles=[("Product Manager", "Product", "Manager"), ("Registered Nurse", "Nursing", "Specialist"),
                ("Staff Nurse", "Nursing", "Entry")],
        health_bias=0.7, n_roles=(2, 3), degrees=["BSN", "MBA"], school_tier=(0.15, 0.3)),
}

FIELDS_OF_STUDY = ["Computer Science", "Biology", "Nursing", "Business Administration",
                   "Public Health", "Biomedical Engineering", "Economics", "Chemistry",
                   "Health Administration", "Neuroscience", "Statistics", "Marketing"]

HEADLINES = {
    "repeat_founder": "Co-Founder & CEO | Health Technology",
    "single_founder": "Founder & CEO, Digital Health",
    "founder_early": "Founding Engineer",
    "clinical_rn": "Clinical Operations Leader, RN",
    "clinician_md": "Physician Executive",
    "healthcare_operator": "Healthcare Operations Leader",
    "product_builder": "Product Manager, Health Technology",
    "technical_builder": "Engineering Leader",
    "commercial_gtm": "Commercial Leader, Healthcare",
    "scientific_researcher": "Research Scientist",
    "ceo_not_founder": "Chief Executive Officer",
    "junior_thin": "Operations Analyst",
    "career_switcher": "RN turned Product Manager",
}


def build_profile(g: Gen, persona: str, idx: int) -> dict:
    """One complete synthetic founder for `persona`.

    Always carries a top-level `_synthetic` tag, so no generated record can be
    mistaken for a real candidate anywhere downstream."""
    rng = g.rng
    spec = TRACKS[persona]
    n_roles = rng.randint(*spec["n_roles"])
    titles = spec["titles"][:n_roles]

    # Build the career backwards from today.
    roles = []
    cursor_y, cursor_m = TODAY_YEAR, TODAY_MONTH
    for i, (title, dept, level) in enumerate(titles):
        tenure = rng.randint(14, 74)
        sy = cursor_y - tenure // 12
        sm = cursor_m - tenure % 12
        if sm <= 0:
            sm += 12
            sy -= 1
        end = None if i == 0 else (cursor_y, cursor_m)
        health = rng.random() < spec["health_bias"]
        tiered = health and rng.random() < 0.18
        big = True if level in ("C-Level", "VP") and rng.random() < 0.35 else None
        comp = g.company(health=health, big=big, tiered=tiered)
        roles.append(g.experience_block(comp, title, dept, level, (sy, sm), end,
                                        order=i + 1, is_current=(i == 0)))
        cursor_y, cursor_m = sy, sm
        if rng.random() < 0.35:  # employment gap
            cursor_m -= rng.randint(1, 8)
            while cursor_m <= 0:
                cursor_m += 12
                cursor_y -= 1

    # education
    p1, p2 = spec["school_tier"]
    r = rng.random()
    school = (rng.choice(TIER1_SCHOOLS) if r < p1
              else rng.choice(TIER2_SCHOOLS) if r < p1 + p2
              else rng.choice(UNKNOWN_SCHOOLS))
    grad_year = min(TODAY_YEAR - 1, roles[-1]["date_from_year"] - rng.randint(0, 2))
    edu = []
    for j, dk in enumerate(spec["degrees"]):
        field = ("Nursing" if dk in ("BSN", "RN")
                 else "Business Administration" if dk == "MBA"
                 else rng.choice(FIELDS_OF_STUDY))
        inst = school if j == 0 else (rng.choice(TIER1_SCHOOLS + TIER2_SCHOOLS + UNKNOWN_SCHOOLS)
                                      if rng.random() < 0.5 else school)
        end_year = min(TODAY_YEAR, grad_year + j * rng.randint(2, 8))
        edu.append(g.education_entry(inst, dk, field, end_year, order=j + 1, variant=True))

    total_months = sum(r_["duration_months"] for r_ in roles)
    city, state = rng.choice(CITIES)
    pid = str(uuid.UUID(int=rng.getrandbits(128), version=4))
    return {
        "mdm_person_id": pid,
        "name_hash": _hash("name", pid),
        "email_hash": _hash("email", pid),
        "phone_hash": None,
        "linkedin_hash": _hash("li", pid),
        "github_hash": None,
        "twitter_hash": None,
        "facebook_hash": None,
        "crunchbase_hash": None,
        "public_profile_id_hash": _hash("pub", pid),
        "professional_emails_hashed": [_hash("pe1", pid), _hash("pe2", pid)],
        "headline": HEADLINES[persona],
        "experience": roles,
        "education": edu,
        "total_experience_duration_months": total_months,
        "location_country": "United States",
        "location_state": state,
        "location_city": city,
        "_synthetic": {"source": "load", "persona": persona, "messiness": []},
    }


# --------------------------------------------------------------------------
# Messiness injections (PLAN A6)
# --------------------------------------------------------------------------
def inject(rec: dict, rng: random.Random) -> None:
    """Apply realistic messiness in place (PLAN A6): missing dates, conflicting
    totals, size mismatches, duplicates, name variants.

    Every injection appends its tag to `_synthetic.messiness[]`, and `main()`
    self-checks that each claimed tag actually manifests — a fixture that lies
    about its own messiness would silently weaken every test that uses it."""
    tags = rec["_synthetic"]["messiness"]
    exp = rec["experience"]

    if exp and rng.random() < 0.18:  # missing dates
        e = rng.choice(exp)
        e["date_from"] = None
        e["date_from_month"] = None
        if rng.random() < 0.5:
            e["date_from_year"] = None
        tags.append("MISSING_DATES")

    if exp and rng.random() < 0.20:  # is_current null vs date_to null
        e = exp[0]
        if rng.random() < 0.5:
            e["is_current"] = None          # date_to null but is_current null
            e["active_experience"] = 1
        else:
            e["is_current"] = 1             # says current AND has an end date
            e["date_to"] = f"{rng.randint(1,12):02d}/{TODAY_YEAR - 1}"
            e["date_to_year"] = TODAY_YEAR - 1
            e["date_to_month"] = rng.randint(1, 12)
        tags.append("AMBIGUOUS_CURRENT")

    if len(exp) >= 2 and rng.random() < 0.15:  # overlapping roles
        a, b = exp[0], exp[1]
        if b.get("date_to_year") and a.get("date_from_year"):
            b["date_to_year"] = a["date_from_year"] + 1
            b["date_to"] = f"{b['date_to_month'] or 6:02d}/{b['date_to_year']}"
            tags.append("OVERLAPPING_ROLES")

    if len(exp) >= 2 and rng.random() < 0.22:  # out-of-order experiences
        rng.shuffle(exp)
        for i, e in enumerate(exp):
            e["order_in_profile"] = i + 1
        tags.append("OUT_OF_ORDER")

    if rng.random() < 0.20:  # total months != sum of roles
        delta = rng.choice([-31, -19, -11, 13, 24, 37])
        rec["total_experience_duration_months"] = max(
            1, (rec["total_experience_duration_months"] or 0) + delta)
        tags.append("TOTAL_MISMATCH")

    if rec["education"] and rng.random() < 0.12:  # missing education entirely
        rec["education"] = []
        tags.append("NO_EDUCATION")

    if rng.random() < 0.06:  # missing experience history (PLAN §4.5 rule 5)
        rec["experience"] = []
        exp = rec["experience"]
        # drop role-level tags: they no longer describe anything in the record
        rec["_synthetic"]["messiness"] = [
            t for t in tags
            if t not in {"MISSING_DATES", "AMBIGUOUS_CURRENT", "OVERLAPPING_ROLES",
                         "OUT_OF_ORDER", "MISSING_COMPANY_METADATA",
                         "MISSING_MANAGEMENT_LEVEL"}
        ]
        tags = rec["_synthetic"]["messiness"]
        tags.append("NO_EXPERIENCE_HISTORY")

    if exp and rng.random() < 0.15:  # missing company classification metadata
        e = rng.choice(exp)
        e["company_industry"] = None
        e["company_size_range"] = None
        e["company_employees_count"] = None
        e["company_categories_and_keywords"] = []
        tags.append("MISSING_COMPANY_METADATA")

    if exp and rng.random() < 0.12:  # missing management level
        rng.choice(exp)["management_level"] = None
        tags.append("MISSING_MANAGEMENT_LEVEL")

    # institution variants / degree variance are produced at generation time
    for ed in rec["education"]:
        canon = None
        for k, vs in SCHOOL_VARIANTS.items():
            if ed["institution_name"] in vs:
                canon = k
        if canon:
            tags.append("INSTITUTION_NAME_VARIANT")
            break
    if rec["education"]:
        tags.append("DEGREE_STRING_VARIANCE")


def make_duplicates(base: dict, rng: random.Random, kind: str) -> dict:
    """kind: 'matching_one' | 'matching_multi' | 'conflicting'."""
    dup = json.loads(json.dumps(base))
    dup["mdm_person_id"] = str(uuid.UUID(int=rng.getrandbits(128), version=4))
    new_pid = dup["mdm_person_id"]
    dup["_synthetic"] = {"source": "load", "persona": base["_synthetic"]["persona"],
                         "messiness": list(base["_synthetic"]["messiness"]),
                         "duplicate_of": base["mdm_person_id"], "duplicate_kind": kind}
    if kind == "matching_one":
        # only linkedin_hash matches -> PROBABLE (flag, never merge)
        dup["email_hash"] = _hash("email", new_pid)
        dup["public_profile_id_hash"] = _hash("pub", new_pid)
        dup["name_hash"] = _hash("name", new_pid)
        dup["professional_emails_hashed"] = [_hash("pe1", new_pid)]
        dup["_synthetic"]["messiness"].append("DUPLICATE_MATCHING_HASH_ONE")
    elif kind == "matching_multi":
        # linkedin + email + public profile all match -> HIGH_CONFIDENCE (still no auto-merge)
        dup["_synthetic"]["messiness"].append("DUPLICATE_MATCHING_HASH_MULTI")
    else:  # conflicting: same name hash, different linkedin AND different email -> NEVER merge
        dup["linkedin_hash"] = _hash("li-conflict", new_pid)
        dup["email_hash"] = _hash("email-conflict", new_pid)
        dup["public_profile_id_hash"] = _hash("pub-conflict", new_pid)
        dup["_synthetic"]["messiness"].append("DUPLICATE_CONFLICTING_HASHES")
    # duplicates are usually captured at a different time -> slightly different content
    if dup["experience"] and rng.random() < 0.7:
        dup["experience"] = dup["experience"][: max(1, len(dup["experience"]) - 1)]
        dup["total_experience_duration_months"] = sum(
            e["duration_months"] or 0 for e in dup["experience"])
        # the total was just recomputed, so any inherited mismatch tag is stale
        dup["_synthetic"]["messiness"] = [
            t for t in dup["_synthetic"]["messiness"] if t != "TOTAL_MISMATCH"]
    return dup


# --------------------------------------------------------------------------
def null_rates(records: list[dict]) -> dict[str, float]:
    """Top-level + experience-level null rate per field (list/[] counts as null)."""
    out: dict[str, list[int]] = {}

    def note(key, val):
        """Tally one field observation, counting null/empty as absent."""
        cnt = out.setdefault(key, [0, 0])
        cnt[1] += 1
        if val is None or val == [] or val == "":
            cnt[0] += 1

    for r in records:
        for k, v in r.items():
            if k == "_synthetic":
                continue
            note(k, v)
        for e in r.get("experience") or []:
            for k, v in e.items():
                note(f"experience[].{k}", v)
        for ed in r.get("education") or []:
            for k, v in ed.items():
                note(f"education[].{k}", v)
    return {k: v[0] / v[1] for k, v in out.items() if v[1]}


def _observable_overlap(exp: list[dict]) -> bool:
    """Can an overlap still be READ off this record? Mirrors what any consumer
    can see: a role needs a start date, and an end date or a duration."""
    spans = []
    for e in exp:
        y, m = e.get("date_from_year"), e.get("date_from_month") or 7
        if not y:
            continue
        start = y * 12 + (m - 1)
        if e.get("date_to_year"):
            end = e["date_to_year"] * 12 + ((e.get("date_to_month") or 7) - 1)
        else:
            end = start + (e.get("duration_months") or 0)
        spans.append((start, max(end, start)))
    spans.sort()
    return any(spans[i + 1][0] < spans[i][1] for i in range(len(spans) - 1))


def reconcile_tags(rec: dict) -> None:
    """Injections and duplicate-trimming can invalidate each other (e.g. trimming
    a duplicate's roles recomputes the total, erasing a TOTAL_MISMATCH). Drop any
    mechanically-checkable tag that no longer manifests, so `_synthetic.messiness`
    is always a truthful description of the record it sits on."""
    tags = rec["_synthetic"]["messiness"]
    exp = rec.get("experience") or []
    total = rec.get("total_experience_duration_months") or 0
    s_roles = sum(e.get("duration_months") or 0 for e in exp)
    keep = []
    for t in tags:
        if t == "TOTAL_MISMATCH" and (not exp or total == s_roles):
            continue
        if t == "NO_EDUCATION" and rec.get("education"):
            continue
        if t in {"AMBIGUOUS_CURRENT", "OUT_OF_ORDER", "OVERLAPPING_ROLES",
                 "MISSING_DATES"} and not exp:
            continue
        if t == "OUT_OF_ORDER" and len(exp) < 2:
            continue
        if t == "AMBIGUOUS_CURRENT" and not any(
                (not e.get("date_to") and not e.get("date_to_year"))
                or ((e.get("is_current") or e.get("active_experience"))
                    and (e.get("date_to") or e.get("date_to_year")))
                for e in exp):
            # duplicate role-trimming removed the role the ambiguity lived on
            continue
        if t == "OVERLAPPING_ROLES" and not _observable_overlap(exp):
            # a later MISSING_DATES injection, or duplicate role-trimming, removed
            # the dates the overlap was expressed in: it is no longer observable
            continue
        if t == "MISSING_COMPANY_METADATA" and exp and all(
                e.get("company_industry") for e in exp):
            continue
        if t == "MISSING_MANAGEMENT_LEVEL" and exp and all(
                e.get("management_level") for e in exp):
            continue
        if t == "MISSING_DATES" and exp and all(
                e.get("date_from_year") and e.get("date_from_month") for e in exp):
            continue
        if t == "DEGREE_STRING_VARIANCE" and not rec.get("education"):
            continue
        if t == "INSTITUTION_NAME_VARIANT" and not any(
                ed.get("institution_name") in vs
                for ed in rec.get("education") or []
                for vs in SCHOOL_VARIANTS.values()):
            continue
        keep.append(t)
    rec["_synthetic"]["messiness"] = keep


def check_tags_are_truthful(records: list[dict]) -> None:
    """A messiness tag that does not manifest in the record is a lie about the
    data. Assert the ones that are mechanically checkable."""
    bad: list[str] = []
    for r in records:
        tags = set(r["_synthetic"]["messiness"])
        exp = r.get("experience") or []
        total = r.get("total_experience_duration_months") or 0
        s_roles = sum(e.get("duration_months") or 0 for e in exp)
        pid = r["mdm_person_id"][:8]
        if "TOTAL_MISMATCH" in tags and (not exp or total == s_roles):
            bad.append(f"{pid}: TOTAL_MISMATCH but total==sum ({total})")
        if "NO_EXPERIENCE_HISTORY" in tags and exp:
            bad.append(f"{pid}: NO_EXPERIENCE_HISTORY but {len(exp)} roles")
        if "NO_EDUCATION" in tags and r.get("education"):
            bad.append(f"{pid}: NO_EDUCATION but education present")
        if tags & {"AMBIGUOUS_CURRENT", "OUT_OF_ORDER", "OVERLAPPING_ROLES",
                   "MISSING_DATES"} and not exp:
            bad.append(f"{pid}: role-level tag with no roles")
        if "MISSING_COMPANY_METADATA" in tags and exp and all(
                e.get("company_industry") for e in exp):
            bad.append(f"{pid}: MISSING_COMPANY_METADATA but all industries present")
    if bad:
        raise AssertionError("untruthful _synthetic tags:\n  " + "\n  ".join(bad[:20]))
    print(f"tag self-check: OK ({len(records)} records, every messiness tag manifests)")


def main() -> None:
    """Regenerate the synthetic load population. Seeded and reproducible.

    Demo/load/distribution use ONLY — no evaluation metric is ever computed
    from this file; those come exclusively from the golden set."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--seed", type=int, default=20260819)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    rng = random.Random(args.seed)
    g = Gen(rng)

    records: list[dict] = []
    n_base = args.n - 40  # leave room for duplicate partners
    for i in range(n_base):
        persona = rng.choices(PERSONAS, weights=PERSONA_WEIGHTS)[0]
        rec = build_profile(g, persona, i)
        inject(rec, rng)
        records.append(rec)

    # duplicates: 15 probable (one hash), 15 high-confidence (multi hash), 10 conflicting
    plan = [("matching_one", 15), ("matching_multi", 15), ("conflicting", 10)]
    for kind, count in plan:
        for base in rng.sample(records[:n_base], count):
            records.append(make_duplicates(base, rng, kind))

    rng.shuffle(records)
    for rec in records:
        reconcile_tags(rec)
    check_tags_are_truthful(records)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(records, fh, indent=1)

    sample = json.load(open(SAMPLE))
    sr, lr = null_rates(sample), null_rates(records)
    print(f"wrote {args.out}: {len(records)} profiles (seed={args.seed})")
    from collections import Counter
    print("personas:", dict(Counter(r["_synthetic"]["persona"] for r in records)))
    mess = Counter(m for r in records for m in r["_synthetic"]["messiness"])
    print("messiness:", dict(mess))
    print(f"{'field':<52}{'sample':>8}{'load':>8}")
    for k in sorted(sr, key=lambda x: (-abs(sr[x] - lr.get(x, 1.0)), x))[:20]:
        print(f"{k:<52}{sr[k]:>8.2f}{lr.get(k, float('nan')):>8.2f}")


if __name__ == "__main__":
    main()
