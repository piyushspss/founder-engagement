# Founder Engagement Workflow — Converged MVP Plan (v2.3 — FROZEN)

_Redesign Health take-home · Piyush Chandra · 2026-08-19 · merged from Claude v1 + ChatGPT review; v2.1 applied the orthogonal assessment dims, machine-vs-human boundary, provenance and conservative dedup_

> **v2.3 (FROZEN) — narrow semantic amendment discovered through CP5 evaluation.**
> One change only: **`potential = LOW` now requires sufficient evidence** (§4.5
> Amendment 4). CP5 v2.2 produced 37 profiles at `REVIEW / LOW / PARTIAL`, which
> asserts a negative conclusion about a founder we had not finished reading.
> Architecture, scope, screens, the broad-score formula, signal weights, the
> §4.3 coverage model (top-level weights **and** sub-components), all thresholds,
> exceptional detectors, archetypes, workflow and LLM behaviour are **unchanged**.
>
> **F-6 — ACCEPTED, no code change.** Deleting the field that *carries* a
> contradiction can legitimately RAISE confidence, because the remaining record
> becomes internally consistent. Confidence is **not required to be globally
> monotonic** under deletion. Recall safety is enforced separately and
> structurally — through evidence coverage, `data_state` and the attention
> floor. The monotonic property that is actually about safety, and that is
> enforced, is: **missing data must never make a founder easier to silently
> dismiss** (zero PRIORITY_REVIEW/REVIEW → ROUTINE transitions under ablation).
>
> ---
>
> **v2.2 (FROZEN) — semantic / evaluation amendment discovered at Checkpoint 5.**
> Three defects were exposed by the CP5 safety suite and are corrected below in
> §4.3 (Amendment 1), §4.5 (Amendments 2 and 3).
>
> **Unchanged by v2.2**: architecture (§6), product scope and the three screens
> (§3), all signal weights and the broad-score formula (§4.1), all four
> thresholds 65 / 0.6 / 30 / 40 (§4.5), the §4.3 top-level coverage weights,
> exceptional detectors and their thresholds (§4.2), archetypes (§4.4), the
> workflow/stage/decision model (§5), LLM rules (§4.2, A11), and the data model.
> No weight and no threshold was retuned. What changed is what the coverage
> components *measure* and two safety guards on the policy result.
>
> **What CP5 found:**
> 1. *(F-1)* `management_level` fed `leadership` + `career_trajectory` — 30 of
>    the 100 broad-score points — while **no** confidence coverage component read
>    it. Deleting it dropped a founder from REVIEW to ROUTINE with confidence
>    completely unchanged: evidence vanished and the system reported the same
>    certainty. → **Amendment 1**.
> 2. *(F-2)* `ROUTINE + NEEDS_INFORMATION` occurred 39 times on load_800 — the
>    machine calling a founder routine while stating it lacked the information to
>    assess them. → **Amendment 2**.
> 3. *(F-5)* At confidence 0.5, broad 29.99 asserted `MEDIUM` while broad 30.00
>    asserted `UNKNOWN` — a *higher* score producing a *more* committed claim on
>    identically untrustworthy evidence. → **Amendment 3**.

---

## 0. TL;DR

A **human-in-the-loop founder engagement workflow** for the (-1→0) funnel that replaces the Excel+ATS:

1. **Import + normalize** messy founder profiles (given JSON schema) → canonical evidence, dedup, quality flags.
2. **Assess** each founder individually: **Review Priority (0–100)**, **Potential (High/Med/Low)**, **Evidence Confidence**, **Archetype**, **Exceptional signals**, **Missing/contradictory data**.
3. **Safety policy**: uncertainty → human review; exceptional evidence → priority review; missing data ≠ negative.
4. **Priority work queue** ("who needs my attention now?") → human decision → **workflow** (Potential → Nurturing → Keep Warm 3/6/9m → re-engage → Deal / Closed) with owner, notes, audit history.
5. **Weekly operating dashboard** replacing the Excel review.

Guiding principle from fact-finding: **recall over precision**. The failure mode is designed around Redesign's asymmetric cost: uncertainty and exceptional evidence bias toward human review rather than rejection, substantially reducing the risk of silent false negatives. (Don't say "guarantee" in the interview.)

**Boundary:** the system prioritizes *attention* and *recommends* actions; humans change founder disposition and lifecycle state.

---

## 1. Fact-finding → requirements

| Learned | Implication |
|---|---|
| Criteria: premier institutions / former founder / premium health companies, etc. — "assume and propose" | Configurable rubric; tier lists + weights are **config, not code** |
| Don't miss good founders; false positives OK | Recall-first. Missing data lowers **confidence**, not potential. Low-confidence → review, never auto-low |
| Dataset tiny; generate synthetic w/ same properties | Two synthetic sets: hand-built **golden eval set** (~50) + auto **load population** (~800, demo only) |
| LinkedIn etc. → Excel → ATS; want this to replace ATS + statuses | Stage + decision + owner + notes + history live here; import JSON/CSV |
| No referral preference | Source = metadata only |
| Workflow: Potential → Nurturing → Keep Warm (3/6/9 mo) → Deal | Stage machine + keep-warm snooze/resurface |
| Weekly Excel review of counts per phase | Dashboard is first-class |
| MVP = (-1→0) funnel only; score the person, not the idea | Person-centric evidence; `funnel` field reserved for (0→1) |
| Score individually, not comparatively | Absolute rubric; no rank-based decisions |
| ≤1000/week | Deterministic core; LLM async/on-demand; SQLite fine |
| Spikiness hard to quantify | Broad Evidence + separate Exceptional Evidence path (see §4) |

---

## 2. Assumptions (say out loud)

- A1. Users: sourcing team (2–5), weekly batch review; leadership views dashboard.
- A2. "Decision" = review disposition (Potential / Not now / Needs info / Needs review) + stage moves + next action owner. No email/calendar in MVP.
- A3. (-1→0): evaluate the founder only; idea fields ignored.
- A4. Referral/source stored, not scored.
- A5. Provided schema is representative: hashed IDs, headline, rich `experience[]` w/ company metadata, `education[]`, totals, location; many nulls.
- A6. Messiness we handle: missing dates, `is_current` null vs `date_to` null, overlapping roles, degree-string variance, institution name variants, duplicate persons, inconsistent ordering, missing company sizes, contradictions (e.g., total months ≠ sum of roles).
- A6b. **Conservative dedup**: same `mdm_person_id` → same person; one strong hash match → *probable* duplicate (flag, don't merge); multiple matching hashes → high-confidence duplicate; conflicting hashes → never auto-merge. UI shows "Possible duplicate detected".
- A7. "Premier institution" / "premium health company" = editable tiered lists + fuzzy match; unknown = neutral.
- A8. Founder evidence only from **explicit** titles (Founder, Co-Founder, Founding CEO/CTO…). CEO/President/MD = leadership evidence only. Suspected-but-unconfirmed → `founder_evidence: POSSIBLE`, never `true`.
- A9. **Review Priority** = "strength of currently observable evidence that this founder deserves Redesign attention" — NOT founder quality and NOT a probability.
- A10. ≤5h; local demo; no auth; single tenant.
- A11. AI usage: (a) code gen, (b) synthetic data, (c) **narrow LLM evidence layer** — structured JSON, uses only supplied facts, can only *raise* to review, runs async/on-demand; (d) profile summary on founder page.

---

## 3. Product scope — 5 capabilities, 3 screens

**Build**
1. **Import + normalize** (JSON/CSV; dedup; quality flags; provenance)
2. **Assessment** (priority, potential, confidence, archetype, signals, exceptional evidence, missing info)
3. **Priority work queue** — home screen
4. **Workflow** — stage + decision + owner + notes + keep-warm resurfacing + audit history
5. **Weekly dashboard** — counts per stage, intake, ageing, stuck, re-engagement due, review-queue size, low-confidence %

**Screens**
- **S1 Priority Queue** (home): KPI strip (Priority Review / Re-engagement Due / Need Research / Nurturing) + table: founder, potential, confidence, archetype, why surfaced, recommended action, stage, owner.
- **S2 Founder Detail**: assessment card, normalized timeline, signals w/ weights, exceptional evidence, missing/contradictions, archetype explanation, actions (decision, stage move, keep-warm 3/6/9, owner, note), audit history.
- **S3 Pipeline + Dashboard**: Kanban by stage + charts. **Config drawer** (weights, tier lists → Recalculate) lives here or in header.

Behind the scenes: evaluation harness + tests.

**Explicitly not built**: ATS/LinkedIn/email/calendar integrations, auth, expert matching, (0→1) scoring, trained ML, embeddings/vector DB, queues/Kafka/k8s, bulk actions. Shown on the architecture slide as future slots.

---

## 4. Assessment model

### 4.1 Deterministic signals (config weights, illustrative)
| Signal | From | Normalization |
|---|---|---|
| founder_evidence (25) | explicit founder titles; tenure; company age/size | binary + capped tenure bonus |
| healthcare_depth (20) | months in health industries / tiered health companies | log-scaled, cap ~5 yrs |
| leadership (15) | `management_level`, scope (company size) | max + capped |
| career_trajectory (15) | level progression over ordered roles | slope, capped |
| education_signal (10) | tiered institutions; MD/PhD/MBA/RN etc. | max, capped; unknown = neutral |
| operating_environment (10) | company size/growth/revenue | log-scaled; missing = neutral |
| other (5) | breadth, total experience (saturating 8–20 yrs) | small, capped |

`broad_score = Σ w_i · s_i` (s_i ∈ [0,1]) → 0–100.

### 4.2 Exceptional evidence (separate path — not averaged away)
Detectors: repeat founder; exit/acquisition cue; rare domain expertise; exceptional progression; major leadership scope; exceptional technical/scientific/clinical credential. Deterministic where possible; **LLM layer** adds contextual items it finds, returning `{exceptional_signal, strength, category, evidence[], unsupported_inferences[]}` from supplied facts only.

### 4.3 Confidence (decision-relevant coverage, not field count)
Weights (**unchanged in v2.2, not retuned**): experience history 30 · current role 10 · chronology 15 · education 10 · company/domain classification 15 · founder evidence 15 · other 5 → coverage; minus contradiction penalty and inference penalty.

**AMENDMENT 1 (v2.2) — coverage must track scoring evidence.** The seven top-level weights above are unchanged. What changes is what each component *measures*. Coverage measures **the availability of the evidence needed to evaluate a dimension**, never merely the existence of an `experience[]` object.

> **Invariant:** every evidence family that materially feeds a deterministic signal must feed at least one coverage component. `management_level` cannot disappear, remove leadership and career-trajectory evidence worth 30 broad-score points, and leave confidence unchanged.

Each top-level component is the **unweighted mean of named sub-components**, all reported in the confidence breakdown, so the source → coverage matrix is readable off a live assessment:

| § 4.3 component (weight) | sub-component | raw evidence family | signals it protects |
|---|---|---|---|
| experience_history (30) | `history_depth` | `experience[]` presence / role count | all |
| | `seniority_readability` | `management_level` | leadership (15), career_trajectory (15) |
| | `tenure_readability` | `duration_months` | healthcare_depth, founder tenure, other |
| current_role (10) | `is_current_known` | `is_current`, `active_experience`, `date_to` | engagement readiness |
| chronology (15) | `start_dates_readable` | `date_from*` (inferred months half-credited) | career_trajectory, exceptional_progression |
| education (10) | `education_present` | `education[]` presence | education_signal (10) |
| | `institution_present` | `education[].institution_name` | education_signal |
| | `degree_interpretable` | `education[].degree` (parses to a known type) | education_signal, exceptional_credential |
| company_domain (15) | `industry_classified` | `company_industry`, categories/keywords | healthcare_depth (20) |
| | `scope_available` | `company_employees_count`, `company_size_range` | operating_environment (10), leadership scope |
| founder_evidence (15) | `titles_readable` | `position_title` | founder_evidence (25), A8 decidability |
| other (5) | `total_experience_stated` | `total_experience_duration_months` | other (5) |
| | `location_known` | `location_country` / `location_city` | other |
| | `breadth_inputs_readable` | `company_industry` strings | other (breadth) |

Two deliberate exclusions, both turning on **availability vs recognisability**:
- **Institution TIER is not a coverage input.** A school off the tier list is still an institution we can read, and A7 fixes unknown as a valid *neutral outcome*, not a gap. Scoring coverage on it would make confidence a measure of how large our starter list is (it would call 45.5% of load_800 education entries "missing" when the field is present). What is covered is that an institution name and an interpretable degree exist.
- **An unrecognised value reduces coverage; it never becomes negative evidence.** A `management_level` outside the known taxonomy, or an unclassifiable industry, genuinely leaves the dimension unevaluable, so coverage falls. No signal ever goes below its neutral floor.

`experience_history.history_depth` alone is what §4.5 rule 5 and `data_state = NEEDS_INFORMATION` key on, so enriching the component around it cannot change what "experience history missing/incomplete" means.

### 4.4 Archetypes (labelling layer, drives explanation not math)
Product Builder · Technical Builder · Healthcare Operator · Clinical Expert · Repeat Founder · Commercial/GTM · Scientific Expert · Hybrid. Sets which "strong signals" and "missing" items are highlighted (e.g., RN → Clinical Ops Lead = Clinical Expert; missing: founder/tech evidence; rec: REVIEW).

### 4.5 Assessment output (orthogonal dimensions) + safety policy
```
potential:          HIGH | MEDIUM | LOW | UNKNOWN
attention:          PRIORITY_REVIEW | REVIEW | ROUTINE
data_state:         SUFFICIENT | PARTIAL | NEEDS_INFORMATION
confidence:         0.00–1.00
recommended_action: CONSIDER_ENGAGEMENT | HUMAN_REVIEW | RESEARCH | NO_URGENT_ACTION
```
Dimensions are independent — a founder can be `PRIORITY_REVIEW` **and** `NEEDS_INFORMATION` at once (exactly what recall-first wants). Machine never emits "Engage"; humans set `decision` and `stage`.

**Safety policy — ordered rules (explicit, unit-tested, shown in UI):**
| # | Condition | Sets |
|---|---|---|
| 1 | Exceptional signal present | attention = PRIORITY_REVIEW |
| 2 | Broad ≥ 65 and confidence ≥ 0.6 | attention = PRIORITY_REVIEW; potential = HIGH; action = CONSIDER_ENGAGEMENT |
| 3 | Confidence < 0.6 and broad ≥ 30 | attention = REVIEW; potential = UNKNOWN/MEDIUM; action = HUMAN_REVIEW |
| 4 | Broad < 40, confidence ≥ 0.6, no exceptional | attention = ROUTINE; potential = LOW; action = NO_URGENT_ACTION (still visible, never hidden) |
| 5 | Experience history missing/incomplete | data_state = NEEDS_INFORMATION; action = RESEARCH (does not lower attention) |
| – | Else | attention = REVIEW; potential = MEDIUM |

**AMENDMENT 2 (v2.2) — incomplete data creates an attention floor.**
```
if data_state in {PARTIAL, NEEDS_INFORMATION}:  attention >= REVIEW
```
So `ROUTINE + PARTIAL` and `ROUTINE + NEEDS_INFORMATION` are **unreachable**. `PRIORITY_REVIEW` is untouched — this is a floor, never a ceiling. On the action side: `NEEDS_INFORMATION → RESEARCH`; `PARTIAL` promotes `NO_URGENT_ACTION → HUMAN_REVIEW` while **preserving stronger actions** such as `CONSIDER_ENGAGEMENT`.

> **This redefines ROUTINE.** ROUTINE is now the positive assertion that **there is sufficient evidence to be comfortable not prioritizing this founder** — not merely the absence of a reason to look. A profile we have not finished reading can no longer earn it.

**AMENDMENT 3 (v2.2) — low-confidence potential is UNKNOWN.** Using the **existing** 0.6 threshold; no new threshold is introduced.
```
confidence < 0.6                  -> potential = UNKNOWN   (regardless of broad_score)
data_state = NEEDS_INFORMATION    -> potential = UNKNOWN
```
Attention stays independent, so `PRIORITY_REVIEW + UNKNOWN` and `REVIEW + UNKNOWN` are normal outputs. This removes the F-5 inversion without moving 30/40/65/0.6. Note the second clause can override rule 2's `HIGH`: strong evidence that is provably incomplete is still not a claim we are entitled to make.

**AMENDMENT 4 (v2.3) — `potential = LOW` requires sufficient evidence.**
```
LOW is valid ONLY when:  data_state == SUFFICIENT
                       ∧ confidence >= 0.6
                       ∧ broad_score < 40
                       ∧ no exceptional evidence / no PRIORITY_REVIEW exceptional floor

PARTIAL + otherwise-LOW  ->  potential = UNKNOWN
                             attention >= REVIEW      (already, via Amendment 2)
                             action    = HUMAN_REVIEW
```
`NEEDS_INFORMATION` already yields UNKNOWN / RESEARCH and is unchanged.

> **PARTIAL does NOT globally force UNKNOWN.** Positive conclusions survive incomplete *minor* data: `PARTIAL + broad ≥ 65 ∧ confidence ≥ 0.6` remains `HIGH / PRIORITY_REVIEW / CONSIDER_ENGAGEMENT`, and the MEDIUM region stays MEDIUM. The asymmetry is deliberate: **incomplete evidence cannot support a NEGATIVE conclusion** — the missing part is exactly where the positive evidence would have been — **but sufficiently strong observed positive evidence can still support HIGH/MEDIUM**, because what was observed was still observed.

**Product definition of LOW (v2.3):** the system had **sufficient** decision-relevant evidence, confidence was at least the operating threshold, no exceptional evidence required escalation, and currently observable positive evidence was **weak**. LOW is a conclusion, not a default.

**Final ordering after v2.3.** Rules 1–5 and the `else` row run exactly as above (v2.1 verbatim), then these guards apply to the result:
1. exceptional evidence → sticky `PRIORITY_REVIEW` attention floor;
2. broad ≥ 65 ∧ confidence ≥ 0.6 → `HIGH` / `PRIORITY_REVIEW` / `CONSIDER_ENGAGEMENT`;
3. missing/incomplete experience → `NEEDS_INFORMATION` / `RESEARCH`;
4. `PARTIAL` or `NEEDS_INFORMATION` → attention floor `REVIEW`;
5. confidence < 0.6 → potential `UNKNOWN`;
6. `NEEDS_INFORMATION` → potential `UNKNOWN`;
7. **ROUTINE is valid only when** no exceptional floor ∧ confidence ≥ 0.6 ∧ `data_state == SUFFICIENT` ∧ broad < 40 under rule 4;
8. **(v2.3)** `LOW` is valid only under the same four conditions — `PARTIAL`/`NEEDS_INFORMATION` + otherwise-LOW → `UNKNOWN`.

Guards 7 and 8 are asserted at the end of every evaluation, so a violation fails loudly rather than being emitted.

LLM layer may only *raise* attention; never lowers.

**Thresholds (65 / 0.6 / 30 / 40) are initial operating hypotheses** — configurable, tuned against the synthetic safety suite, not statistically learned. If Redesign can review 300/wk → loosen; 40/wk → tighten.

### 4.5b Evidence provenance
Every signal (rule or AI) carries: `signal → value → strength → source_fields[] → type: OBSERVED | DERIVED | AI_INTERPRETED`. Example: healthcare_depth STRONG ← `experience[0].position_title`, `experience[1].position_title` (DERIVED). "Why did you conclude this?" → show it. Fact vs. judgment is visible in the UI.

### 4.6 Evaluation
- **Golden set** (~50 hand-built): 15 must-surface · 15 reasonable-low · 10 ambiguous/spiky · 10 data-quality/adversarial (dups, contradictions, missing history, CEO-not-founder, elite-school-only).
- Primary metric: **recall of must-surface** (target ≥ 0.95); also precision (info), review-queue rate, LOW-bucket leakage (must be 0 must-surface in LOW).
- **Ablation**: null out 30% of fields → recall holds, confidence drops, review queue grows. Report numbers.
- **Confidence monotonicity (v2.3, accepted scope)**: confidence is NOT globally monotonic under field deletion. Removing the field that carried a contradiction removes the contradiction penalty and may raise confidence — correctly, since the record is then internally consistent. Do not attempt to force monotonicity for contradiction-removal cases. Safety is carried by the invariant below.
- **Missing-data hard invariant (v2.2)**: over representative decision-relevant field ablations, the count of `PRIORITY_REVIEW`/`REVIEW → ROUTINE` transitions must be **0**, with **no exemption for removing the positive evidence itself**. If that evidence disappears, coverage must fall too, so `PARTIAL`/`NEEDS_INFORMATION` protects the founder from routine dismissal.
- **Caveat to state explicitly**: golden-set recall means "the system behaves consistently with our stated assumptions and safety policy under sparse/contradictory data" — NOT "97% accurate at identifying great founders." No outcome labels exist; real validation needs reviewer-labelled historical candidates or prospective reviewer feedback.
- Report deterministic-only vs deterministic+LLM separately (shows where LLM adds lift; keeps eval reproducible).
- Sensitivity: live weight changes in config drawer.

---

## 5. Founder data model

```
Founder
├── Source Profile (raw, provenance)
├── Canonical Profile (normalized)
├── Evidence (observed / derived / AI-interpreted, each with source fields)
├── Assessment (broad score, exceptional, potential, confidence, archetype, attention, data_state, recommended_action)
├── Human Decision (disposition)
└── Engagement Workflow (stage, owner, next action, keep warm, notes, history)
```

Workflow fields:

- `stage`: NEW → ASSESSMENT → POTENTIAL → NURTURING → KEEP_WARM → DEAL | CLOSED
- `decision`: NEEDS_REVIEW | POTENTIAL | NOT_NOW | NEEDS_INFORMATION
- `keep_warm_until` (3/6/9 mo) → resurfaces in queue as "Re-engagement due" → back to NURTURING
- `owner`, `next_action`, `notes[]`
- `audit_log`: who, when, field, from→to, reason

---

## 6. Architecture

```
 JSON/CSV ─► Normalizer ─► Dedup/Quality flags ─► Evidence Engine ─► Assessment ─► Safety Policy ─► SQLite
                                                  ├ deterministic signals                              │
                                                  └ LLM contextual (async/on-demand)                   │
 React/Vite UI ◄── FastAPI ◄───────────────────────────────────────────────────────────────────────────┘
   S1 Queue · S2 Detail · S3 Pipeline+Dashboard · Config drawer
   actions → stage/decision transitions + audit log + keep-warm resurfacing
```
- Python/FastAPI, Pydantic, SQLAlchemy+SQLite; `assessment/` pure functions (unit-tested); `config/weights.yaml`, `config/tiers/*.json`.
- React+Vite+Tailwind (Streamlit fallback decided at hour 1).
- Tradeoffs: rubric < ML ceiling but > trust/cold-start; no labels → ML unjustified; LLM-only too uncalibrated; SQLite no concurrency (fine); no auth. No queues/Redis/vector DB — 1000/wk doesn't justify it.

---

## 7. 5-hour plan (risk-ordered: thinking + eval before UI polish)

| Hr | Work |
|---|---|
| 0–0.5 | Scaffold; schema→Pydantic; synthetic generator (load pop) + golden set skeleton |
| 0.5–1.75 | Normalizer, signals, exceptional detectors, confidence, archetype, safety policy; unit tests; eval script |
| 1.75–3.25 | FastAPI; S1 Queue, S2 Detail, S3 Pipeline+Dashboard; config drawer |
| 3.25–3.75 | Stage/decision machine, keep-warm resurfacing, audit log |
| 3.75–4.25 | LLM evidence layer (on-demand button + batch script; mock adapter if no key); eval incl. ablation, deterministic vs +AI lift; tune |
| 4.25–5 | Stakeholder deck: learnings, assumptions, demo, eval numbers, roadmap, AI usage |

---

## 8. Roadmap (prioritized)
1. **Capture rich labels** (reviewer assessment, expert engagement, nurture, keep-warm, deal, founder declined, idea mismatch, timing, external) — separate founder-quality outcome from process outcome; then learn/calibrate the rubric.
2. **(0→1) funnel**: idea/company scorer, shared pipeline.
3. **Enrichment** (LinkedIn/Crunchbase/GitHub via hashes) to raise confidence.
4. LLM memos + reviewer-agreement tracking.
5. Integrations: Slack digest (resurfacing), calendar, CRM export.
6. Ops: Postgres, auth/roles, multi-user, data-quality monitors.
7. Data to request: explicit founder flag, exits, publications/patents, source, prior Redesign touchpoints, interest areas.

---

## 9. Interview narrative
Thought it was a scoring problem → needs-finding showed it's a prioritization + operating-workflow problem where false negatives cost more than false positives → data is rich but incomplete/contradictory and key founder qualities aren't directly observable → built human-in-the-loop workflow: rules extract reliable signals, AI adds contextual/exceptional evidence, uncertainty raises review rather than rejection, everything explainable → evaluated with purpose-built scenarios + ablation, recall of must-review founders as primary metric → next: collect real reviewer/outcome feedback, learn the rubric, enrich, add (0→1).

## 10. Open questions for the discussion
- Weekly review-queue capacity? · Keep-warm strictly 3/6/9? · Can they share their premier school/company lists? · Should experience >10 yrs old decay?
