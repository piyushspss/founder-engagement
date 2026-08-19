#!/usr/bin/env python3
"""Author data/golden/profiles.json — the 50 hand-specified golden profiles.

This script is a FIXTURE COMPILER, not an assessor. It never imports the
evidence, policy or assessment layers: it turns a compact, human-readable
scenario spec into the raw JSON schema, filling the mechanical parts (date
decomposition, duration arithmetic, stated totals, the full null-padded key set)
so that a profile intended to be COMPLETE really is complete and a profile
intended to be missing exactly one evidence family is missing exactly that one.

Every scenario, and every expectation in data/golden/cases.yaml, is authored
from PLAN v2.3 semantics BEFORE the assessor is run (CP6 anti-overfitting
freeze). Nothing here reads an assessment.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AS_OF_YEAR, AS_OF_MONTH = 2026, 8
AS_OF_INDEX = AS_OF_YEAR * 12 + (AS_OF_MONTH - 1)

EXPERIENCE_KEYS = [
    "title", "position_title", "department", "management_level", "location",
    "order_in_profile", "date_from", "date_to", "date_from_year", "date_from_month",
    "date_to_year", "date_to_month", "duration", "duration_months", "is_current",
    "active_experience", "company_id", "company_name", "company_type", "company_url",
    "company_website", "company_logo_url", "company_linkedin_url", "company_industry",
    "company_categories_and_keywords", "company_is_b2b", "company_size_range",
    "company_employees_count", "company_employees_count_change_yearly_percentage",
    "company_followers_count", "company_founded_year", "company_stock_ticker",
    "company_twitter_url", "company_facebook_url", "company_last_updated_at",
    "company_last_funding_round_date", "company_last_funding_round_amount_raised",
    "company_annual_revenue_source_1", "company_annual_revenue_source_5",
    "company_annual_revenue_currency_source_1", "company_annual_revenue_currency_source_5",
    "company_hq_city", "company_hq_state", "company_hq_street", "company_hq_zipcode",
    "company_hq_country", "company_hq_country_iso2", "company_hq_country_iso3",
    "company_hq_full_address", "company_hq_regions",
]
EDUCATION_KEYS = [
    "degree", "field_of_study", "order_in_profile", "date_from", "date_to",
    "date_from_year", "date_to_year", "school_name", "school_url", "institution_name",
    "institution_url", "institution_logo_url", "institution_city", "institution_state",
    "institution_street", "institution_zipcode", "institution_full_address",
    "institution_country_iso2", "institution_country_iso3", "institution_regions",
]
PROFILE_KEYS = [
    "mdm_person_id", "name_hash", "email_hash", "phone_hash", "linkedin_hash",
    "github_hash", "twitter_hash", "facebook_hash", "crunchbase_hash",
    "public_profile_id_hash", "professional_emails_hashed", "headline", "experience",
    "education", "total_experience_duration_months", "location_country",
    "location_state", "location_city",
]


def idx(mmyyyy: str) -> int:
    """MM/YYYY → absolute month index, for authoring role spans."""
    m, y = mmyyyy.split("/")
    return int(y) * 12 + (int(m) - 1)


def h(seed: str) -> str:
    """Deterministic stand-in for the upstream-hashed identity fields."""
    import hashlib
    return hashlib.sha256(seed.encode()).hexdigest()


def role(title, company, industry, level, dept, start, end=None, *, size=None,
         size_range=None, growth=None, revenue=None, current=None, duration=None,
         drop=(), founded=None):
    """One experience row. `drop` names fields to null out deliberately.

    Dates are emitted in BOTH supplied forms (string + decomposed) exactly as the
    source schema does. `duration_months` is computed from the span so that the
    stated total can be consistent; pass `duration` to override.
    """
    r = {k: None for k in EXPERIENCE_KEYS}
    r["position_title"] = title
    r["company_name"] = company
    r["company_industry"] = industry
    r["management_level"] = level
    r["department"] = dept
    r["company_type"] = "Privately Held"
    r["company_is_b2b"] = 1
    r["company_categories_and_keywords"] = [industry.lower()] if industry else None
    r["company_stock_ticker"] = []
    r["company_twitter_url"] = []
    r["company_facebook_url"] = []
    r["company_hq_country"] = "United States"
    r["company_hq_country_iso2"] = "US"
    r["company_hq_regions"] = ["Americas", "Northern America", "AMER"]
    r["company_founded_year"] = founded
    r["location"] = "United States"

    if start is not None:
        sm, sy = start.split("/")
        r["date_from"] = start
        r["date_from_year"], r["date_from_month"] = int(sy), int(sm)
        s = idx(start)
    else:
        s = None

    if end is not None:
        em, ey = end.split("/")
        r["date_to"] = end
        r["date_to_year"], r["date_to_month"] = int(ey), int(em)
        r["is_current"], r["active_experience"] = 0, 0
        e = idx(end)
    else:
        e = AS_OF_INDEX
        if current is None or current:
            r["is_current"], r["active_experience"] = 1, 1

    if current is False:                      # explicit "no currentness indicator"
        r["is_current"], r["active_experience"] = None, None

    if duration is not None:
        r["duration_months"] = duration
    elif s is not None:
        r["duration_months"] = max(0, e - s)

    if size is not None:
        r["company_employees_count"] = size
    if size_range is not None:
        r["company_size_range"] = size_range
    if growth is not None:
        r["company_employees_count_change_yearly_percentage"] = growth
    if revenue is not None:
        r["company_annual_revenue_source_5"] = revenue
        r["company_annual_revenue_currency_source_5"] = "USD"

    for field in drop:
        r[field] = None
    return r


def edu(institution, degree, field=None, start_year=None, end_year=None, drop=()):
    """Build one education entry; `drop` blanks fields to author a data gap."""
    e = {k: None for k in EDUCATION_KEYS}
    e["institution_name"] = institution
    e["school_name"] = institution
    e["degree"] = degree
    e["field_of_study"] = field
    e["date_from_year"], e["date_to_year"] = start_year, end_year
    e["institution_country_iso2"] = "US"
    e["institution_country_iso3"] = "USA"
    for f in drop:
        e[f] = None
    return e


def profile(case_id, headline, roles, education, *, location=("United States", "New York", "New York"),
            total="auto", hashes=None, messiness=(), notes="", raw_order=None):
    """Assemble one raw profile.

    `total="auto"` states the total that the roles actually imply (no
    contradiction); pass an int to author a deliberate TOTAL_MISMATCH, or None to
    author a missing total.
    """
    p = {k: None for k in PROFILE_KEYS}
    p["mdm_person_id"] = f"golden-{case_id}"
    p["name_hash"] = h(f"{case_id}-name")
    p["email_hash"] = h(f"{case_id}-email")
    p["linkedin_hash"] = h(f"{case_id}-linkedin")
    p["public_profile_id_hash"] = h(f"{case_id}-ppid")
    p["professional_emails_hashed"] = [h(f"{case_id}-pro")]
    p["headline"] = headline
    p["education"] = education
    p["location_country"], p["location_state"], p["location_city"] = location

    # canonical source convention: newest first, order_in_profile 1..n
    ordered = list(roles)
    if raw_order is not None:
        ordered = [roles[i] for i in raw_order]
    for i, r in enumerate(ordered):
        r["order_in_profile"] = i + 1
    p["experience"] = ordered

    if total == "auto":
        p["total_experience_duration_months"] = sum(r["duration_months"] or 0 for r in roles)
    else:
        p["total_experience_duration_months"] = total

    if hashes:
        p.update(hashes)
    p["_synthetic"] = {"source": "golden", "messiness": list(messiness), "notes": notes}
    return p


# ===========================================================================
# GROUP 1 — must_surface (15)
# ===========================================================================
CASES: dict[str, dict] = {}


def case(cid, prof, companions=()):
    """Register one golden case. Companions are extra records that must exist so
    corpus-level dedup can see them; they are not scored cases themselves."""
    CASES[cid] = {"case_id": cid, "profile": prof,
                  "companions": list(companions)}


case("MS01", profile(
    "MS01", "Co-Founder & CEO, Meridian Care Labs | digital health",
    [role("Co-Founder & CEO", "Meridian Care Labs", "Hospital & Health Care", "C-Level",
          "Executive", "01/2020", None, size=60, growth=25.0, revenue=12_000_000, founded=2020),
     role("Co-Founder & CTO", "Nurox Health", "Hospital & Health Care", "C-Level",
          "Executive", "01/2016", "12/2019", size=25, founded=2016),
     role("Senior Product Manager", "CareLoop Health", "Hospital & Health Care", "Senior",
          "Product", "01/2012", "12/2015", size=180)],
    [edu("Massachusetts Institute of Technology", "B.S. Computer Science", "Computer Science",
         2008, 2012)],
    notes="L: two DISTINCT explicit founder roles -> repeat_founder STRONG"))

case("MS02", profile(
    "MS02", "Founder & CEO, Solace Home Care",
    [role("Founder & CEO", "Solace Home Care", "Hospital & Health Care", "C-Level",
          "Executive", "01/2020", None, size=220, growth=22.0, revenue=18_000_000, founded=2020),
     role("Director of Operations", "Pinebrook Health Services", "Hospital & Health Care",
          "Director", "Operations", "01/2014", "12/2019", size=800, growth=6.0,
          revenue=95_000_000)],
    [edu("Bentley College of Business", "M.B.A.", "Business Administration", 2010, 2012)],
    notes="K + W: ONE explicit founder role. Priority via broad policy, never repeat founder"))

case("MS03", profile(
    "MS03", "Chief Medical Officer, Kingsley Regional Health",
    [role("Chief Medical Officer", "Kingsley Regional Health", "Hospital & Health Care",
          "C-Level", "Executive", "01/2019", None, size=3000, growth=6.0, revenue=400_000_000),
     role("Attending Physician", "Kingsley Regional Health", "Hospital & Health Care",
          "Senior", "Medical", "07/2012", "12/2018", size=3000),
     role("Resident Physician", "Kingsley Regional Health", "Hospital & Health Care",
          "Entry", "Medical", "07/2008", "06/2012", size=3000)],
    [edu("Baylor College of Medicine", "M.D.", "Medicine", 2004, 2008)],
    notes="MD credential + major leadership scope: two MEDIUM detectors"))

case("MS04", profile(
    "MS04", "Co-Founder, Verity Health — acquired by Optum in 2021",
    [role("Co-Founder & CEO", "Verity Health", "Hospital & Health Care", "C-Level",
          "Executive", "03/2016", None, size=45, growth=15.0, revenue=9_000_000, founded=2016)],
    [edu("Stonebridge University", "B.S. Economics", "Economics", 2008, 2012)],
    messiness=["truncated_experience_history"],
    notes="P: exceptional (exit cue in headline) + NEEDS_INFORMATION (single role)"))

case("MS05", profile(
    "MS05", "Founding CTO, Cadence Bio | genomics infrastructure",
    [role("Founding CTO", "Cadence Bio", "Biotechnology", "C-Level", "Engineering",
          "01/2019", None, size=55, growth=40.0, revenue=6_000_000, founded=2018),
     role("Senior Bioinformatics Scientist", "Helix Genomics Inc", "Biotechnology", "Senior",
          "Research", "01/2013", "12/2018", size=400, growth=10.0, revenue=40_000_000)],
    [edu("Rensselaer Polytechnic Institute", "Ph.D. Computational Biology", "Bioinformatics",
         2007, 2013)],
    location=(None, None, None),
    messiness=["missing_location"],
    notes="R: PARTIAL (location absent) + strong observed positive evidence -> HIGH survives"))

case("MS06", profile(
    "MS06", "Chief Product Officer, Northwind Health Plan",
    [role("Chief Product Officer", "Northwind Health Plan", "Health Insurance", "C-Level",
          "Product", "01/2024", None, size=2000, growth=8.0, revenue=900_000_000),
     role("VP Product", "Northwind Health Plan", "Health Insurance", "VP", "Product",
          "01/2021", "12/2023", size=2000),
     role("Director of Product", "Northwind Health Plan", "Health Insurance", "Director",
          "Product", "01/2018", "12/2020", size=2000),
     role("Product Manager", "Northwind Health Plan", "Health Insurance", "Manager",
          "Product", "01/2015", "12/2017", size=2000)],
    [edu("University of Chicago", "M.B.A.", "Business Administration", 2012, 2014)],
    notes="must_surface WITHOUT an exceptional flag: one MEDIUM detector is not exceptional"))

case("MS07", profile(
    "MS07", "VP Operations, Cedar Valley Health Network",
    [role("VP Operations", "Cedar Valley Health Network", "Hospital & Health Care", "VP",
          "Operations", "01/2024", None, size=5200, growth=4.0, revenue=1_200_000_000),
     role("Director of Operations", "Cedar Valley Health Network", "Hospital & Health Care",
          "Director", "Operations", "01/2021", "12/2023", size=5200),
     role("Operations Manager", "Cedar Valley Health Network", "Hospital & Health Care",
          "Manager", "Operations", "01/2017", "12/2020", size=5200),
     role("Operations Analyst", "Cedar Valley Health Network", "Hospital & Health Care",
          "Entry", "Operations", "01/2014", "12/2016", size=5200)],
    [edu("Emory University", "M.B.A.", "Health Administration", 2011, 2013)],
    notes="12y health operator, clean chronology"))

case("MS08", profile(
    "MS08", "VP Corporate Development, Teladoc Health",
    [role("VP Corporate Development", "Teladoc Health", "Hospital & Health Care", "VP",
          "Strategy", "01/2023", None, size=5000, growth=5.0, revenue=2_400_000_000),
     role("Co-Founder & CEO (acquired by Teladoc Health)", "Brightpath Telecare",
          "Hospital & Health Care", "C-Level", "Executive", "06/2016", "12/2022", size=90,
          founded=2016)],
    [edu("Stanford University", "B.S. Symbolic Systems", "Symbolic Systems", 2008, 2012)],
    notes="deterministic exit cue read verbatim from position_title"))

case("MS09", profile(
    "MS09", "Co-Founder & CEO, Waypoint Labs",
    [role("Co-Founder & CEO", "Waypoint Labs", None, "C-Level", "Executive", "01/2019",
          None, current=False, duration=91),
     role("Co-Founder", "Alder & Finch", None, "C-Level", "Executive", "01/2013", "12/2018")],
    [],
    location=(None, None, None), total=None,
    messiness=["no_company_metadata", "no_education", "no_totals", "no_currentness"],
    notes="O: exceptional (repeat founder) + confidence < 0.6 -> PRIORITY_REVIEW / UNKNOWN"))

case("MS10", profile(
    "MS10", "Engineering Lead, Lumen Health Systems",
    [role("Engineering Lead", "Lumen Health Systems", "Hospital & Health Care", "Lead",
          "Engineering", "01/2024", None, size=300, growth=18.0, revenue=45_000_000),
     role("Senior Software Engineer", "Lumen Health Systems", "Hospital & Health Care",
          "Senior", "Engineering", "01/2022", "12/2023", size=300),
     role("Software Engineer II", "Lumen Health Systems", "Hospital & Health Care",
          "Specialist", "Engineering", "01/2020", "12/2021", size=300),
     role("Software Engineer", "Lumen Health Systems", "Hospital & Health Care", "Entry",
          "Engineering", "01/2018", "12/2019", size=300)],
    [edu("Drexel Polytechnic School", "B.S. Computer Engineering", "Computer Engineering",
         2014, 2018)],
    notes="H: 3 resolved steps inside 6 years; spacing keeps the >=2-in-3y rule from firing"))

case("MS11", profile(
    "MS11", "Director of Clinical Operations, Harbor Health Partners",
    [role("Director of Clinical Operations", "Harbor Health Partners", "Hospital & Health Care",
          "Director", "Clinical Operations", "01/2022", None, size=900, growth=12.0,
          revenue=140_000_000),
     role("Clinical Operations Lead", "St. Anselm Medical Center", "Hospital & Health Care",
          "Lead", "Clinical Operations", "01/2017", "12/2021", size=1800, growth=5.0,
          revenue=300_000_000),
     role("Registered Nurse", "St. Anselm Medical Center", "Hospital & Health Care",
          "Specialist", "Nursing", "01/2012", "12/2016", size=1800)],
    [edu("Villanova Health Sciences College", "B.S.N. Nursing", "Nursing", 2008, 2012)],
    notes="V: deep clinical/domain expert, no founder history — must not be silently LOW"))

case("MS12", profile(
    "MS12", "Founder & CEO, Ardent Health Labs",
    [role("Founder & CEO", "Ardent Health Labs", "Hospital & Health Care", "C-Level",
          "Executive", None, None, size=150, current=False, duration=60, growth=10.0),
     role("Director of Operations", "Ardent Health Labs", "Hospital & Health Care", "Director",
          "Operations", None, None, size=150, current=False, duration=48),
     role("Operations Manager", "Rowan Care Group", "Hospital & Health Care", "Manager",
          "Operations", None, None, size=90, current=False, duration=36)],
    [edu("Kettering College of Business", "B.S. Business", "Business", 2004, 2008)],
    total=None,
    messiness=["all_dates_missing", "no_totals", "no_currentness"],
    notes="founder evidence intact, chronology gone: must not drop out of the queue"))

case("MS13", profile(
    "MS13", "Principal Scientist, Genomics — Emberline Biosciences",
    [role("Principal Scientist, Genomics", "Emberline Biosciences", "Biotechnology", "Lead",
          "Research", "01/2021", None, size=1200, growth=10.0, revenue=300_000_000),
     role("Research Scientist", "Emberline Biosciences", "Biotechnology", "Senior",
          "Research", "01/2016", "12/2020", size=1200)],
    [edu("Johns Hopkins University", "Ph.D. Genomics", "Genomics", 2010, 2016)],
    notes="rare domain + terminal credential: exceptional, but broad < 65 so potential is MEDIUM"))

case("MS14", profile(
    "MS14", "Co-Founder & COO, Ledgerline",
    [role("Co-Founder & COO", "Ledgerline Inc", "Financial Services", "C-Level", "Executive",
          "01/2019", None, size=40, growth=30.0, revenue=5_000_000, founded=2019),
     role("Operations Manager", "Trellis Health Group", "Hospital & Health Care", "Manager",
          "Operations", "01/2014", "12/2018", size=600, growth=9.0, revenue=70_000_000)],
    [edu("Fordham Business Institute", "B.A. Economics", "Economics", 2010, 2014)],
    notes="cross-domain: explicit founder outside health, 5y health operating history"))

case("MS15", profile(
    "MS15", "VP Sales, Cardinal Benefit Group",
    [role("VP Sales", "Cardinal Benefit Group", "Health Insurance", "VP", "Sales",
          "01/2023", None, size=1500, growth=7.0, revenue=600_000_000),
     role("Director of Sales", "Cardinal Benefit Group", "Health Insurance", "Director",
          "Sales", "01/2019", "12/2022", size=1500),
     role("Account Executive", "Cardinal Benefit Group", "Health Insurance", "Specialist",
          "Sales", "01/2015", "12/2018", size=1500)],
    [edu("Emory University", "M.B.A.", "Business Administration", 2012, 2014)],
    notes="commercial leader at a large health insurer"))


# ===========================================================================
# GROUP 2 — reasonable_low (15). Deliberately COMPLETE profiles: coverage 1.0,
# no contradictions, no inferences — so that a LOW conclusion is entitled to be
# made at all (PLAN v2.3 Amendment 4).
# ===========================================================================
case("RL01", profile(
    "RL01", "Operations Analyst at Northline Freight",
    [role("Operations Analyst", "Northline Freight", "Logistics and Supply Chain", "Entry",
          "Operations", "01/2024", None, size=45),
     role("Operations Assistant", "Northline Freight", "Logistics and Supply Chain", "Entry",
          "Operations", "01/2023", "12/2023", size=45)],
    [edu("Boise Valley State College", "B.S. Business Administration", "Business", 2019, 2023)]))

case("RL02", profile(
    "RL02", "Store Manager, Copperfield Retail",
    [role("Store Manager", "Copperfield Retail", "Retail", "Manager", "Operations",
          "01/2023", None, size=80),
     role("Store Manager", "Harlow Goods", "Retail", "Manager", "Operations",
          "01/2019", "12/2022", size=80)],
    [edu("Boise Valley State College", "B.A. Communications", "Communications", 2014, 2018)]))

case("RL03", profile(
    "RL03", "Marketing Coordinator at Pinegrove Agency",
    [role("Marketing Coordinator", "Pinegrove Agency", "Marketing and Advertising", "Entry",
          "Marketing", "01/2025", None, size=60),
     role("Marketing Intern", "Pinegrove Agency", "Marketing and Advertising", "Training",
          "Marketing", "06/2024", "12/2024", size=60)],
    [edu("Cascade Community University", "B.A. Marketing", "Marketing", 2020, 2024)]))

case("RL04", profile(
    "RL04", "Staff Accountant",
    [role("Staff Accountant", "Weatherby & Co", "Accounting", "Specialist", "Finance",
          "01/2022", None, size=300),
     role("Staff Accountant", "Grantham Partners", "Accounting", "Specialist", "Finance",
          "01/2019", "12/2021", size=300)],
    [edu("Cascade Community University", "B.S. Accounting", "Accounting", 2015, 2019)]))

case("RL05", profile(
    "RL05", "Customer Support Specialist",
    [role("Customer Support Specialist", "Vantage Software", "Computer Software", "Specialist",
          "Customer Success", "01/2024", None, size=120),
     role("Customer Support Associate", "Vantage Software", "Computer Software", "Entry",
          "Customer Success", "01/2021", "12/2023", size=120)],
    [edu("Cascade Community University", "B.A. English", "English", 2016, 2020)]))

case("RL06", profile(
    "RL06", "Software Engineer at Tanager Systems",
    [role("Software Engineer", "Tanager Systems", "Computer Software", "Entry", "Engineering",
          "01/2025", None, size=140),
     role("Junior Software Engineer", "Tanager Systems", "Computer Software", "Entry",
          "Engineering", "01/2024", "12/2024", size=140)],
    [edu("Ashford Technical College", "B.S. Computer Science", "Computer Science", 2020, 2024)]))

case("RL07", profile(
    "RL07", "Senior Administrative Assistant, Redbank Community Hospital",
    [role("Senior Administrative Assistant", "Redbank Community Hospital",
          "Hospital & Health Care", "Specialist", "Administration", "01/2022", None, size=240),
     role("Administrative Assistant", "Redbank Community Hospital", "Hospital & Health Care",
          "Entry", "Administration", "01/2019", "12/2021", size=240)],
    [edu("Cascade Community University", "B.A. Sociology", "Sociology", 2014, 2018)],
    notes="health EMPLOYER but no leadership/scope: tests where the 20-point health signal lands"))

case("RL08", profile(
    "RL08", "Graphic Designer",
    [role("Graphic Designer", "Fennel Studio", "Graphic Design", None, "Design",
          "01/2022", None, size=15),
     role("Junior Graphic Designer", "Marrow Design House", "Graphic Design", None, "Design",
          "01/2018", "12/2021", size=30)],
    [edu("Ashford Technical College", "B.A. Visual Design", "Visual Design", 2014, 2018)],
    messiness=["unrecognised_industry", "no_management_level"],
    notes="A + Q: industry PRESENT but unrecognised -> UNKNOWN (not non-health); "
          "PARTIAL + weak evidence -> UNKNOWN, never LOW"))

case("RL09", profile(
    "RL09", "Warehouse Supervisor",
    [role("Warehouse Supervisor", "Calder Distribution", "Logistics and Supply Chain",
          "Manager", "Operations", "01/2021", None, size=110),
     role("Warehouse Supervisor", "Pell Logistics", "Logistics and Supply Chain", "Manager",
          "Operations", "01/2017", "12/2020", size=110)],
    [edu("Boise Valley State College", "B.S. Business", "Business", 2012, 2016)]))

case("RL10", profile(
    "RL10", "Middle School Teacher",
    [role("Middle School Teacher", "Ridgeline School District", "Primary/Secondary Education",
          "Specialist", "Education", "01/2021", None, size=200),
     role("Elementary School Teacher", "Ridgeline School District",
          "Primary/Secondary Education", "Specialist", "Education", "01/2016", "12/2020",
          size=200)],
    [edu("Cascade Community University", "M.S. Education", "Education", 2013, 2015)]))

case("RL11", profile(
    "RL11", "Personal Banker, Calloway Savings Bank",
    [role("Personal Banker", "Calloway Savings Bank", "Banking", "Specialist", "Finance",
          "01/2023", None, size=900),
     role("Bank Teller", "Calloway Savings Bank", "Banking", "Entry", "Finance",
          "01/2019", "12/2022", size=900)],
    [edu("Boise Valley State College", "B.S. Finance", "Finance", 2015, 2019)],
    notes="F: ONE ordinary promotion — positive broad trajectory, no exceptional progression"))

case("RL12", profile(
    "RL12", "Field Sales Representative",
    [role("Field Sales Representative", "Halcott Supply", "Wholesale", "Entry", "Sales",
          "01/2024", None, size=35),
     role("Field Sales Representative", "Bramble Tools", "Wholesale", "Entry", "Sales",
          "01/2022", "12/2023", size=35)],
    [edu("Ashford Technical College", "B.A. Business", "Business", 2017, 2021)]))

case("RL13", profile(
    "RL13", "General Manager, Ember & Oak",
    [role("General Manager", "Ember & Oak", "Restaurants", "Manager", "Operations",
          "01/2020", None, size=150),
     role("General Manager", "Saltwater Grill", "Restaurants", "Manager", "Operations",
          "01/2014", "12/2019", size=150)],
    [edu("Cascade Community University", "B.A. Hospitality", "Hospitality", 2009, 2013)]))

case("RL14", profile(
    "RL14", "IT Support Specialist, Redbank Community Hospital",
    [role("IT Support Specialist", "Redbank Community Hospital", "Hospital & Health Care",
          "Specialist", "Information Technology", "01/2024", None, size=240),
     role("IT Support Specialist", "Redbank Community Hospital", "Hospital & Health Care",
          "Specialist", "Information Technology", "01/2021", "12/2023", size=240)],
    [edu("Ashford Technical College", "B.S. Information Systems", "Information Systems",
         2016, 2020)],
    notes="health employer, Specialist scope only, no progression"))

case("RL15", profile(
    "RL15", "Paralegal",
    [role("Paralegal", "Kestrel & Vane LLP", "Legal Services", "Specialist", "Legal",
          "01/2022", None, size=180),
     role("Paralegal", "Ottway Legal Group", "Legal Services", "Specialist", "Legal",
          "01/2019", "12/2021", size=180)],
    [edu("Ashford Technical College", "B.A. Legal Studies", "Legal Studies", 2015, 2019)],
    notes="B (half): unlisted institution contributes ZERO positive evidence, no penalty"))


# ===========================================================================
# GROUP 3 — ambiguous_spiky (10)
# ===========================================================================
case("AS01", profile(
    "AS01", "Senior Engineer",
    [role("Senior Engineer", "Aster Labs", "Computer Software", "Senior", "Engineering",
          "01/2025", None, size=8, current=False),
     role("Senior Engineer", "Bellamy AI", "Computer Software", "Senior", "Engineering",
          "01/2023", "12/2024", size=12),
     role("Senior Engineer", "Cobble Works", "Computer Software", "Senior", "Engineering",
          "01/2022", "12/2022", size=20)],
    [edu("Ashford Technical College", "B.S. Computer Science", "Computer Science", 2017, 2021)],
    messiness=["no_currentness_on_latest_role"],
    notes="spiky builder or churn — the machine is not entitled to decide"))

case("AS02", profile(
    "AS02", "Marketing Coordinator at Brightline Media",
    [role("Marketing Coordinator", "Brightline Media", "Marketing and Advertising", "Entry",
          "Marketing", "01/2021", None, size=90),
     role("VP Operations", "Halcyon Health Partners", "Hospital & Health Care", "VP",
          "Operations", "01/2011", "12/2011", size=700),
     role("Operations Manager", "Halcyon Health Partners", "Hospital & Health Care",
          "Manager", "Operations", "01/2010", "12/2010", size=700),
     role("Operations Analyst", "Halcyon Health Partners", "Hospital & Health Care", "Entry",
          "Operations", "01/2008", "12/2009", size=700)],
    [edu("Boise Valley State College", "B.S. Business", "Business", 2004, 2008)],
    messiness=["nine_year_gap"],
    notes="I: one independently well-supported pair (Entry->VP in 3y) satisfies exceptional "
          "progression while the post-gap pairs are unresolvable"))

case("AS03", profile(
    "AS03", "Founder & builder | health tech",
    [role("Head of Growth", "Cobalt Health", "Hospital & Health Care", "Head", "Growth",
          "01/2022", None, size=40, growth=20.0),
     role("Growth Manager", "Pallas Software", "Computer Software", "Manager", "Growth",
          "01/2019", "12/2021", size=60)],
    [edu("Ashford Technical College", "B.S. Marketing", "Marketing", 2015, 2019)],
    messiness=["headline_claims_founder"],
    notes="A8: a headline is self-reported — POSSIBLE only, never founder evidence"))

case("AS04", profile(
    "AS04", "Regulatory Affairs Lead, Arden Medical Devices",
    [role("Regulatory Affairs Lead", "Arden Medical Devices", "Medical Devices", "Lead",
          "Operations", "01/2016", None, size=700, growth=6.0),
     role("Quality Engineer", "Arden Medical Devices", "Medical Devices", "Specialist",
          "Operations", "01/2008", "12/2015", size=700)],
    [edu("Ashford Technical College", "B.S. Biomedical Engineering", "Biomedical Engineering",
         2004, 2008)],
    notes="C: `Lead` is real leadership evidence but does NOT satisfy a Manager-or-above "
          "archetype gate"))

case("AS05", profile(
    "AS05", "Senior Medical Physicist, Ridgeway Cancer Institute",
    [role("Senior Medical Physicist, Radiation Oncology", "Ridgeway Cancer Institute",
          "Hospital & Health Care", "Senior", "Clinical", "01/2021", None, size=400),
     role("Medical Physicist", "Ridgeway Cancer Institute", "Hospital & Health Care",
          "Specialist", "Clinical", "01/2015", "12/2020", size=400)],
    [edu("Kearney College of Applied Sciences", "Ph.D. Medical Physics",
         "Radiation Oncology Physics", 2009, 2015)],
    notes="B: unlisted institution contributes ZERO; the PhD still contributes evidence"))

case("AS06", profile(
    "AS06", "Director of Operations, Nimbus Labs",
    [role("Director of Operations", "Nimbus Labs", "Computer Software", "Director",
          "Operations", "01/2025", None, size=12),
     role("Operations Associate", "Nimbus Labs", "Computer Software", "Entry", "Operations",
          "01/2022", "12/2024", size=12)],
    [edu("Ashford Technical College", "B.S. Business", "Business", 2018, 2022)],
    notes="G: >=2 resolved steps inside 3 years -> exceptional_progression MEDIUM, at a "
          "12-person company"))

case("AS07", profile(
    "AS07", "Senior Product Manager, Cobalt Health Software",
    [role("Senior Product Manager", "Cobalt Health Software", "Hospital & Health Care",
          "Senior", "Product", "01/2024", None, size=150),
     role("Product Manager", "Cobalt Health Software", "Hospital & Health Care", "Manager",
          "Product", "01/2019", "12/2023", size=150),
     role("Registered Nurse", "Fairview Community Hospital", "Hospital & Health Care",
          "Specialist", "Nursing", "01/2012", "12/2018", size=900)],
    [edu("Villanova Health Sciences College", "B.S.N. Nursing", "Nursing", 2008, 2012)],
    messiness=["provider_level_regression_on_a_real_promotion"],
    notes="E: provider levels say Manager->Senior (a regression); the titles say a same-family "
          "promotion. Canonical resolution is positive, and 1 step in 5y is NOT exceptional"))

case("AS08", profile(
    "AS08", "Nonprofit program leader",
    [role("Program Manager", "Riverstone Community Services",
          "Nonprofit Organization Management", "Manager", "Operations", "01/2024", None,
          size=60),
     role("Founding Member", "Open Door Health Collective",
          "Nonprofit Organization Management", "Specialist", "Operations", "01/2019",
          "12/2023", size=12)],
    [edu("Cascade Community University", "B.A. Public Policy", "Public Policy", 2015, 2019)],
    notes="A8: 'Founding Member' is POSSIBLE, and POSSIBLE scores 0.0"))

case("AS09", profile(
    "AS09", "Co-Founder & CEO, Verge Systems",
    [role("Co-Founder & CEO", "Verge Systems", None, "C-Level", "Executive", "01/2021",
          None, current=False),
     role("Senior Engineer", "Halden Tech", None, "Senior", "Engineering", "01/2016",
          "12/2020")],
    [], location=(None, None, None), total=None,
    messiness=["no_company_metadata", "no_education", "no_totals", "no_currentness"],
    notes="N: the rule-3 shape — broad well above 30, confidence below 0.6"))

case("AS10", profile(
    "AS10", "Advisor to early-stage teams",
    [role("Advisor", "Beacon Works", "Computer Software", "Specialist", "Strategy",
          "01/2024", None, size=25),
     role("Advisor", "Cobalt Ventures", "Computer Software", "Specialist", "Strategy",
          "01/2023", None),
     role("Advisor", "Trellis Data", "Computer Software", "Specialist", "Strategy",
          "01/2023", None),
     role("Advisor", "Marrow Labs", "Computer Software", "Specialist", "Strategy",
          "01/2022", None, size=40),
     role("Advisor", "Quill Health", "Hospital & Health Care", "Specialist", "Strategy",
          "01/2024", "12/2025")],
    [edu("Cascade Community University", "M.B.A.", "Business Administration", 2016, 2018)],
    messiness=["five_concurrent_roles", "missing_company_sizes"],
    notes="portfolio advisor: heavy overlap, no operating role"))


# ===========================================================================
# GROUP 4 — data_quality_adversarial (10)
# ===========================================================================
def companion(cid, headline, roles, education, hashes):
    """A non-case record that exists only to give a dedup case something to
    match (or conflict) against."""
    return profile(cid, headline, roles, education, hashes=hashes)


case("DQ01", profile(
    "DQ01", "Clinical Program Manager, Alder Health System",
    [role("Clinical Program Manager", "Alder Health System", "Hospital & Health Care",
          "Manager", "Clinical Operations", "01/2021", None, size=600, growth=5.0),
     role("Clinical Program Specialist", "Alder Health System", "Hospital & Health Care",
          "Specialist", "Clinical Operations", "01/2016", "12/2020", size=600)],
    [edu("Villanova Health Sciences College", "B.S.N. Nursing", "Nursing", 2012, 2016)],
    notes="A6b: ONE strong hash shared -> PROBABLE duplicate, flagged, never merged"),
    companions=[companion(
        "DQ01b", "Clinical Program Manager",
        [role("Clinical Program Manager", "Alder Health System", "Hospital & Health Care",
              "Manager", "Clinical Operations", "01/2021", None, size=600)],
        [edu("Villanova Health Sciences College", "B.S.N. Nursing", "Nursing", 2012, 2016)],
        hashes={"linkedin_hash": h("DQ01-linkedin")})])

case("DQ02", profile(
    "DQ02", "Facilities Coordinator, Marlow Property Group",
    [role("Facilities Coordinator", "Marlow Property Group", "Real Estate", "Specialist",
          "Operations", "01/2022", None, size=70),
     role("Facilities Assistant", "Marlow Property Group", "Real Estate", "Entry",
          "Operations", "01/2018", "12/2021", size=70)],
    [edu("Boise Valley State College", "B.A. Business", "Business", 2014, 2018)],
    notes="A6b: THREE strong hashes shared -> HIGH_CONFIDENCE duplicate, still not merged; "
          "the duplicate flag must not move any assessment dimension"),
    companions=[companion(
        "DQ02b", "Facilities Coordinator",
        [role("Facilities Coordinator", "Marlow Property Group", "Real Estate", "Specialist",
              "Operations", "01/2022", None, size=70)],
        [edu("Boise Valley State College", "B.A. Business", "Business", 2014, 2018)],
        hashes={"linkedin_hash": h("DQ02-linkedin"), "email_hash": h("DQ02-email"),
                "public_profile_id_hash": h("DQ02-ppid")})])

case("DQ03", profile(
    "DQ03", "Logistics Coordinator",
    [role("Logistics Coordinator", "Pell Logistics", "Logistics and Supply Chain",
          "Specialist", "Operations", "01/2022", None, size=110),
     role("Logistics Coordinator", "Calder Distribution", "Logistics and Supply Chain",
          "Specialist", "Operations", "01/2018", "12/2021", size=110)],
    [edu("Boise Valley State College", "B.S. Business", "Business", 2014, 2018)],
    notes="A6b: same weak hash, CONFLICTING strong hashes -> never merged, never asserted"),
    companions=[companion(
        "DQ03b", "Logistics Coordinator",
        [role("Logistics Coordinator", "Pell Logistics", "Logistics and Supply Chain",
              "Specialist", "Operations", "01/2022", None, size=110)],
        [edu("Boise Valley State College", "B.S. Business", "Business", 2014, 2018)],
        hashes={"name_hash": h("DQ03-name")})])

case("DQ04", profile(
    "DQ04", "Clinical Operations Manager, Verity Regional Health",
    [role("Clinical Operations Manager", "Verity Regional Health", "Hospital & Health Care",
          "Manager", "Clinical Operations", "01/2020", None, size=4200,
          size_range="201-500 employees", growth=5.0, revenue=800_000_000),
     role("Clinical Operations Specialist", "Verity Regional Health", "Hospital & Health Care",
          "Specialist", "Clinical Operations", "01/2014", "12/2019", size=4200,
          size_range="1001-5000 employees")],
    [edu("Cascade Community University", "B.S. Health Administration", "Health Administration",
         2010, 2014)],
    total=193,   # sum of roles is 151; +42 months is a deliberate contradiction
    messiness=["total_mismatch", "size_range_mismatch"],
    notes="D + T: complete but self-contradictory. data_state stays SUFFICIENT (coverage is "
          "about availability); confidence falls; raw values are preserved"))

case("DQ05", profile(
    "DQ05", "Chief Executive Officer, Waterline Freight",
    [role("Chief Executive Officer", "Waterline Freight Co", "Logistics and Supply Chain",
          "C-Level", "Executive", "01/2018", None, size=14),
     role("President", "Waterline Freight Co", "Logistics and Supply Chain", "C-Level",
          "Executive", "01/2010", "12/2017", size=9)],
    [edu("Boise Valley State College", "B.S. Business", "Business", 2006, 2010)],
    notes="J: CEO/President are LEADERSHIP evidence only — never founder evidence (A8)"))

case("DQ06", profile(
    "DQ06", "Harvard graduate",
    [], [edu("Harvard University", "B.A. History", "History", 2018, 2022)],
    total=None,
    messiness=["no_experience_history"],
    notes="U: elite school alone must never produce an exceptional signal"))

case("DQ07", profile(
    "DQ07", "Healthcare operations leader",
    [], [edu("Pacific Northwest College", "M.S. Health Administration", "Health Administration",
             2014, 2016)],
    total=None,
    messiness=["no_experience_history"],
    notes="rule 5: NEEDS_INFORMATION + RESEARCH; attention is not lowered"))

case("DQ08", profile(
    "DQ08", "Senior Engineer",
    [role("Senior Engineer", "Halloway Systems", "Computer Software", "Senior", "Engineering",
          None, None, size=250, current=False, duration=40),
     role("Senior Engineer", "Ondine Software", "Computer Software", "Senior", "Engineering",
          None, None, size=250, current=False, duration=38),
     role("Software Engineer", "Ondine Software", "Computer Software", "Senior", "Engineering",
          None, None, size=250, current=False, duration=36),
     role("Software Engineer", "Braddock Data", "Computer Software", "Senior", "Engineering",
          None, None, size=250, current=False, duration=36)],
    [edu("Ashford Technical College", "B.S. Computer Science", "Computer Science", 2008, 2012)],
    messiness=["all_dates_null", "no_currentness"],
    notes="chronology and trajectory unavailable; confidence collapses, attention does not"))

case("DQ09", profile(
    "DQ09", "Co-Founder & CEO, Tessera Health",
    [role("Co-Founder", "Tessera Health", "Hospital & Health Care", "C-Level", "Executive",
          "03/2021", None, size=30, growth=25.0),
     role("Co-Founder & CEO", "Tessera Health", "Hospital & Health Care", "C-Level",
          "Executive", "03/2021", None, size=30, growth=25.0),
     role("Head of Product", "Loomis Health", "Hospital & Health Care", "Head", "Product",
          "01/2018", "12/2020", size=200)],
    [edu("Ashford Technical College", "B.S. Computer Science", "Computer Science", 2010, 2014)],
    raw_order=[2, 0, 1],
    messiness=["duplicate_founder_row", "overlapping_roles", "out_of_order_array"],
    notes="M: two rows describing ONE founding must not manufacture a Repeat Founder"))

case("DQ10", profile(
    "DQ10", "Software Engineer, Kestrel Systems",
    [role("Senior Software Engineer", "Kestrel Systems", "Computer Software", "Senior",
          "Engineering", "01/2023", None, size=160),
     role("Software Engineer", "Kestrel Systems", "Computer Software", "Specialist",
          "Engineering", "01/2019", "12/2022", size=160)],
    [edu("M.I.T.", "B.S. Computer Science", "Computer Science", 2015, 2019)],
    messiness=["institution_name_variant"],
    notes="A7: a fuzzy institution variant resolves to the tier list and costs an inference "
          "penalty, because the match is a judgment"))


def main() -> None:
    """Emit `data/golden/profiles.json` from the authored cases.

    The golden set is FROZEN: expected outcomes in `cases.yaml` were authored
    and hashed BEFORE the assessor was ever run against them, and neither file
    may be edited to make a failing case pass."""
    out = []
    for cid, entry in CASES.items():
        out.append({"case_id": cid, "profile": entry["profile"],
                    "companions": entry["companions"]})
    path = ROOT / "data" / "golden" / "profiles.json"
    path.write_text(json.dumps(out, indent=2, sort_keys=False) + "\n")
    n_comp = sum(len(e["companions"]) for e in CASES.values())
    print(f"wrote {path} — {len(out)} cases, {n_comp} dedup companion profiles")
    from collections import Counter
    print(Counter(cid[:2] for cid in CASES))


if __name__ == "__main__":
    main()
