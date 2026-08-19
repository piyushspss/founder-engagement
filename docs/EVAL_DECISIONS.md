# Evaluation Decisions

Every golden-set failure gets classified here before any code or config changes:

* **(a) implementation violates intended policy** → fix the code. Log it.
* **(b) the test/assumption is wrong** → report it, propose the test change with
  reasoning, and leave the case failing until a human approves the change.

Weights and thresholds are **never** tuned to make an individual case pass
(PLAN §4.6, runbook working rules).

| # | Case | Classification | Reasoning | Action | Approved by |
|---|---|---|---|---|---|
| — | — | — | No golden-set runs yet (profiles authored in Checkpoint 6). | — | — |
| CP4-1 | `test_repeat_founder_archetype_takes_precedence` (my own unit test, not a golden case) | (b) the test assumption was wrong | I assumed a two-time founder is labelled `Repeat Founder`. Under the frozen `archetypes.yaml` a repeat founder **at healthcare companies with an `Executive` department** also satisfies Healthcare Operator, and two material matches trigger the configured Hybrid rule. The config is what it is; my expectation was the thing that was wrong. | Test split in two: one asserting `Repeat Founder` when it is the only material match, one **documenting** the Hybrid absorption. No config changed. | pending reviewer |
| CP4-2 (SUPERSEDED by CP4-R3 — reviewer ruled `Lead < Manager`; RN now labels `Clinical Expert`) | RN → Clinical Operations supplied profile labels `Hybrid`, not `Clinical Expert` | reported, not resolved | See CP4 oddity O-1 in `CHECKPOINT_LOG.md`. Turns on whether `management_level_at_least: Manager` is evaluated on the coarse ordinal ladder (`Lead` ties `Manager` → Hybrid) or on the leadership `level_scores` ordering (`Lead` 0.42 < `Manager` 0.45 → Clinical Expert). Both ladders exist in the frozen config and disagree. | **No change made.** Implementation reuses the single existing ordinal ladder; the test asserts only the parts not in dispute. Awaiting reviewer decision. | pending reviewer |
| CP4-R1 | `test_not_exceptional_progression_when_cp3_could_not_resolve_the_ladder` | (b) my test assumption was too strong | I had gated the whole detector on the broad `career_trajectory` being observed. The reviewer specified CP3 semantics **per role pair**, which is strictly more precise: an unresolvable pair asserts nothing, but a resolvable pair elsewhere in the same CV is still real evidence. | Split into two tests: all-pairs-unresolvable → silent; unresolvable pair does not silence a resolvable one. | pending reviewer |
| CP4-R2 | `test_repeat_founder_in_healthcare_is_absorbed_into_hybrid` | (a) implementation violated intended policy | The test documented the Hybrid-absorption behaviour that CP4-R4 corrects. | Replaced with `test_repeat_founder_keeps_the_primary_label_and_retains_co_matches`. | pending reviewer |

---

## CP5 decisions

**CP5-1 — rule 3's potential is UNKNOWN, not MEDIUM (interpretation I-1).**
Classification: (b)-adjacent — the frozen table permits either, so this is an interpretation, not
a test change. Reasoning: rule 3 fires precisely because confidence is below the bar at which we
are willing to make a claim; `MEDIUM` is a claim about founder quality, `UNKNOWN` is not. Choosing
MEDIUM would additionally make `potential` vary with `broad_score` under low confidence, which
lets the score determine a dimension it is explicitly not allowed to determine. No second
threshold was introduced. Documented in `app/policy/safety.py`.

**CP5-2 — the `else` row completes `potential` (interpretation I-2).** Rules 1 and 5 set no
potential, so reading `else` as "no rule fired at all" would leave an exceptional founder with no
potential at all. `else` fires when rules 2–4 assigned none. Consequence, accepted and reported:
an exceptional founder with an unremarkable score lands PRIORITY_REVIEW ∧ MEDIUM.

**CP5-3 — "experience missing/incomplete" = the §4.3 coverage component < 1.0 (interpretation
I-3).** Reuses the frozen confidence model rather than defining a second notion of "incomplete",
and guarantees rule 5 and the data_state ladder cannot disagree. One role counts as incomplete.

**CP5-4 — F-1 is NOT fixed at CP5.** The missing-data property fails because `management_level`
and `duration_months` carry ~30 broad points while no §4.3 coverage component reads them, so their
loss costs score and zero confidence. Classification: **(a) implementation-independent — the
defect is in the frozen §4.3 coverage weights, not in the CP5 code.** Fixing it means adding a
seniority/tenure coverage component to §4.3, which is a plan change and outside CP5's scope. No
threshold and no weight was touched. The behaviour is pinned by `test_L8_FINDING_...` so a future
fix shows up as a deliberate test change rather than a silent drift. **Awaiting human decision.**

**CP5-5 — F-2 (ROUTINE ∧ NEEDS_INFORMATION) implemented as frozen.** The §4.5 table says rule 5
"does not lower attention". It does not say rule 5 raises attention. Implemented literally.
Reported as a finding because a recall-first reading would arguably raise it to REVIEW.
**Awaiting human decision; not changed.**

**CP5-6 — no threshold, weight or tier list was modified at CP5.** Verified by
`test_thresholds_are_the_frozen_operating_hypotheses` and the CP3-era
`test_signal_weights_were_not_touched`.

---

## CP5 revision 1 decisions (PLAN v2.2 / RUNBOOK v1.2)

**CP5-7 — CP5-4 is now RESOLVED by approved plan amendment, not by tuning.** F-1 was classified at
CP5 as a defect in the frozen §4.3 coverage model. The human amended §4.3 (Amendment 1) and §4.5
(Amendment 2). No weight and no threshold changed. The v2.1 finding test
(`test_L8_FINDING_evidence_only_fields_can_move_review_to_routine`) was **replaced** by
fix-verification tests, which is a legitimate test change because the approved amendment changed
the intended behaviour — not because the test was inconvenient.

**CP5-8 — CP5-5 (F-2) resolved by Amendment 2.** `ROUTINE + NEEDS_INFORMATION` is now unreachable.

**CP5-9 — F-5 resolved by Amendment 3 on the existing 0.6 threshold.** No new threshold.

**CP5-10 — institution tier is deliberately excluded from coverage.** Classification: (b) — a
design decision, recorded because it is the one place Amendment 1's letter ("every evidence family
must affect coverage") was read against its intent. Coverage measures *availability*; tier
membership measures *our starter list's size*. Including it would mark 45.5% of load_800's
education entries as missing when the field is present, and A7 already fixes unknown as a valid
neutral outcome. `institution_present` and `degree_interpretable` cover the family instead.

**CP5-11 — three CP3/CP4-era tests re-pointed, intent preserved.** `test_industry_recognition`'s
coverage assertions moved from the composite component to the `industry_classified` sub-component
(the thing they were always about); two policy tests updated for guards 5/6. Classification: (b),
caused by the approved amendment. No assertion was weakened to pass.

**CP5-12 — F-6 (contradiction-carrier deletion can raise confidence) NOT fixed.** Classification:
(b) — the behaviour is semantically correct (the record really is self-consistent afterwards) and
is never a safety failure (0 attention downgrades). Fixing it would mean penalising confidence for
a contradiction that no longer exists, or tracking "fields that were once present", neither of
which is in the frozen plan. Pinned by `test_F6_*` and the CP3 monotonicity property is now
explicitly scoped. **Awaiting human decision.**

**CP5-13 — F-7 (REVIEW ∧ LOW) and F-8 (ROUTINE at 1.6%) implemented as frozen and reported.**
Both are direct consequences of the approved amendments. Neither was tuned.

---

## CP5 revision 2 decisions (PLAN v2.3 / RUNBOOK v1.3)

**CP5-14 — F-6 ACCEPTED, superseding CP5-12.** Confidence is not required to be globally monotonic
under deletion when the removed field carried the contradiction. No code change; the interpretation
is documented in PLAN §4.5/§4.6 and `policy/safety.py`. The `test_F6_*` tests are retained as
documentation of accepted behaviour rather than as an open finding. Re-verified: 0 of the 42
confidence-increase ablations reach ROUTINE or LOW.

**CP5-15 — F-7 resolved by Amendment 4 (guard 8).** Classification: (a) — the implementation was
faithful to v2.2, but v2.2's semantics let a negative conclusion rest on incomplete evidence. The
human amended the plan; no weight, threshold or coverage sub-component was touched. `LOW ∧ PARTIAL`
37 → 0.

**CP5-16 — PARTIAL deliberately does NOT force UNKNOWN.** Recorded because it is the one place
Amendment 4 could be over-applied. Incomplete evidence cannot support a negative conclusion; it can
leave a positive one standing. Proved by `test_v23_partial_preserves_high_and_medium_but_not_low`
and by 121 HIGH ∧ PARTIAL / 204 MEDIUM ∧ PARTIAL surviving on load_800.

**CP5-17 — the source→coverage model was NOT touched in revision 2**, per the review instruction.
The only code change is guard 8 in `policy/safety.py`.

---

# CP6 — Golden set evaluation

## GOLDEN_SET_PRE_EVAL_FREEZE

Recorded **before** `scripts/eval.py` existed (verified: `ls scripts/eval.py` → No such file or
directory at the moment these hashes were taken) and therefore before the assessor was ever run
against the golden set.

| artefact | SHA-256 |
|---|---|
| `data/golden/cases.yaml` | `6e128c9d1cdebfa77d7273cdced5df48305b5836460c4824aae8ae906232d8cf` |
| `data/golden/profiles.json` | `8de59bea693eb00eceea6d4cc894f685089808bc5be8f94b1ce4127cce7d3c96` |

**Timestamp (UTC):** 2026-08-19T16:24:43Z
**Command:** `shasum -a 256 data/golden/cases.yaml data/golden/profiles.json`

Both files hold, at this hash: all 50 scenario descriptions, all 50 complete raw profiles, all 50
`expected {attention, potential, data_state, action}` blocks, all `expected_evidence` semantic
assertions, all plain-language rationales and all `expected_reason` assumption/rule IDs.

### What was permitted before the freeze, and what was not

**Permitted and performed — fixture validation at the NORMALIZATION layer only.** After writing the
profiles I ran a check that printed institution tier + degree type, industry → `health_flag`,
founder-title classification, the normalizer's flag lists and the dedup relations, to confirm that
each profile *is the scenario its description claims* (e.g. that the invented school
"Kearney College of Applied Sciences" really does resolve to UNKNOWN rather than fuzzy-matching a
tier list entry, and that "Graphic Design" really does classify UNKNOWN rather than non-health).
It printed **no** `broad_score`, `confidence`, `coverage`, `attention`, `potential`, `data_state`
or `recommended_action`. Expectations were derived from PLAN v2.3 semantics and hand-computed
signal arithmetic, never from an assessment.

**Not permitted, and not performed:** running the assessor, or any policy output, before the
hashes above were recorded.

### Authoring revisions to CP1 stub expectations (all pre-freeze)

The CP1 skeleton's expectations were written against PLAN **v2.1**. Amendments 2, 3 and 4 changed
what several of those stubs should expect, and some stubs used permissive value LISTS that would
have made a case unfalsifiable. Every case now carries a single expected value per dimension, and
each changed expectation carries a `stub_revision:` line naming the reason. The full list:

| case | CP1 stub expectation | authored v2.3 expectation | reason |
|---|---|---|---|
| MS04 | potential HIGH/MEDIUM/UNKNOWN | UNKNOWN | guard 6: NEEDS_INFORMATION → UNKNOWN |
| MS06 | PRIORITY_REVIEW via rule 1 | PRIORITY_REVIEW via rule 2, `exceptional_flag: false` | one MEDIUM detector is not exceptional at the frozen `medium_count: 2` |
| MS10 | PRIORITY_REVIEW via rule 1 | REVIEW / MEDIUM | same: single MEDIUM detector |
| MS12 | PRIORITY_REVIEW / NEEDS_INFORMATION | REVIEW / UNKNOWN / PARTIAL | I-3′: a three-role history is not a *missing* history; no detector fires |
| RL07 | ROUTINE **or** REVIEW | REVIEW / MEDIUM | list → determinate value |
| RL08 | ROUTINE/LOW permitted | REVIEW / UNKNOWN / PARTIAL | guard 8: PARTIAL + weak evidence may not be LOW |
| RL14 | ROUTINE **or** REVIEW | ROUTINE / LOW | list → determinate value |
| AS02 | PARTIAL/NEEDS_INFORMATION | SUFFICIENT | the frozen coverage model has no career-gap detector |
| AS03 | PARTIAL/NEEDS_INFORMATION | SUFFICIENT | an inference penalty lowers confidence, not coverage |
| AS06 | PRIORITY_REVIEW or REVIEW | ROUTINE / LOW | single MEDIUM detector; broad well below 40 |
| AS08 | REVIEW | ROUTINE / LOW | founder evidence correctly 0; remaining evidence weak on complete data |
| DQ04 | PARTIAL/NEEDS_INFORMATION | SUFFICIENT | contradictions lower confidence, not coverage |
| DQ06 | ROUTINE permitted | REVIEW | guard 4: ROUTINE + NEEDS_INFORMATION is unreachable |
| all others | value lists | single values | a list cannot fail, and this set exists to be able to fail |

No weight, threshold (30/40/65/0.6), detector parameter, tier list or config value was touched at
any point in this authoring step.

## CP6 failure adjudication

**Failing cases: none.** All 50 golden cases matched their pre-registered expectations on all four
dimensions (`attention`, `potential`, `data_state`, `recommended_action`) *and* on every
`expected_evidence` semantic assertion (detector fired / not fired, signal exactly zero, signal
strictly positive, contradiction present, inference present, quality flag present, duplicate
relation, archetype membership).

Consequently there is **no `(a)` entry and no `(b)` entry to make**. No code was changed. No
expectation was changed after the freeze. No weight, threshold (30 / 40 / 65 / 0.6), detector
parameter or tier list was touched — the rubric hash is `41bffa7056f4` both before and after the
evaluation, and the only files modified during CP6 are `CHECKPOINT_LOG.md`, `EVAL_DECISIONS.md`,
`EVAL_REPORT.md`, `data/golden/cases.yaml`, `data/golden/profiles.json`, `scripts/author_golden.py`
and `scripts/eval.py`.

### CP6-1 — one change WAS made during CP6, to the measuring instrument (not the system)

The first version of the §8 F-6 probe nulled only the *string* form of a date field
(`date_to`) and left the decomposed `date_to_year` / `date_to_month` intact. Because the schema
carries dates twice, the deletion it claimed to perform did not actually happen, and four probe
rows reported "+0.000, contradiction not resolved" for a removal that was never made. Classified as
a defect **in `scripts/eval.py`**, not in the product: the assessor behaved correctly throughout;
the instrument was lying about the input it fed. Fixed by nulling every supplied form of the field
together. No product code, config or expectation was involved. Reported here because a measuring
instrument that under-reports a safety-relevant phenomenon is exactly the kind of thing that should
never be corrected silently.

### Results that are technically consistent with the frozen semantics but SURPRISING

Required by §5 of the CP6 brief. **None of these is being fixed or tuned at CP6.** Each is a
property of the frozen model, surfaced by the golden set doing its job.

| id | observation | why it follows from the frozen semantics | why it is still worth a human decision |
|---|---|---|---|
| **F-10** | **AS10**: deleting every start date RAISES confidence by **+0.150** (0.655 → 0.805). | The contradiction penalty cap (0.30) is larger than the whole `chronology` coverage weight (0.15), so removing ten OVERLAP contradictions buys more than losing the entire chronology costs. This is F-6 (accepted) in its starkest form. | The record that says nothing about *when* anything happened is scored as more trustworthy than the one that says something contradictory. Attention and potential are unmoved (REVIEW / UNKNOWN), so the safety property holds — but the *number* shown to a reviewer is counter-intuitive. A reviewer decision on whether the contradiction cap should be bounded by the coverage it displaces. |
| **F-11** | **RL07 (47.3, REVIEW) vs RL14 (36.7, ROUTINE)**: same employer type, same health exposure, same Specialist scope. The entire difference is one promotion step. | `healthcare_depth` saturates at ~5 years (20 of 100 points) and measures *exposure*, not seniority, so any sustained health employment starts a profile halfway to the routine threshold; one trajectory step then decides the band. | Two of fifteen reasonable_low cases escalated, both for this reason. If Redesign's reviewers do not want hospital administrative staff in the queue, the lever is the `healthcare_depth` weight or an exposure-vs-seniority split — a rubric decision, not a threshold nudge. |
| **F-12** | **RL03**: an intern → coordinator step over **7 months** saturates `career_trajectory` at the full 15 points. | The signal is a slope (steps ÷ years) capped at 0.5 levels/year, with no minimum time base. A short interval makes the denominator tiny. | A new graduate scores maximum trajectory evidence. It does not change RL03's outcome (still ROUTINE / LOW), but on a stronger profile it would. The exceptional detector has step/window rules that prevent exactly this; the broad signal has none. |
| **F-13** | **AS06**: `exceptional_progression` fires (4 steps in 3 years) and the profile still lands **ROUTINE / LOW**. | One MEDIUM detector is not exceptional at the frozen `medium_count: 2`, and at a 12-person company with no health, founder or scope evidence the broad score is 34. Both halves are correct. | A reviewer opening this founder sees a fired exceptional detector next to "no urgent action". That is defensible (small-pond title inflation), but the UI must show the detector *and* the reason it did not escalate — a CP8 requirement, not a scoring change. |
| **F-14** | **AS02**: a **nine-year** unexplained career gap produces no flag, no contradiction and no coverage reduction — `data_state = SUFFICIENT`. | The frozen §4.3 coverage model measures the availability of evidence families. A gap is not an absent field; every field present is present. There is no gap detector in the plan. | Arguably the single most reviewer-relevant fact about that CV, and the machine says nothing about it. Candidate for the roadmap, not for a CP6 patch. |
| **F-15** | **MS12**: broad score **73.7** with every date field null across all three roles. | `founder_evidence`, `healthcare_depth` and `leadership` read titles, durations and levels; only `career_trajectory` needs dates, and it correctly reports nothing. | The score looks like a strong founder while chronology is entirely unknown. The policy handles it correctly — confidence 0.583 forces UNKNOWN and REVIEW — which is precisely why `broad_score` must never be displayed without its confidence. |
| **F-16** | Under 30% ablation the golden set produced **zero** confidence increases, while the isolated probe produced four. | A random 30% draw usually removes a contradiction *and* several coverage families at once, and the coverage loss dominates. | Not a defect, but it means the ablation table alone cannot answer the F-6 question. That is why §8 of the report exists; the same caveat applies to reading CP5's load_800 ablation. |

### Queue capacity — REPORTED, NOT TUNED (§8 of the CP6 brief)

Baseline review-queue rate on the golden set is **62.0% (31/50)**; under 30% ablation it rises to
a mean of **98.4%**. Under sparse data almost everyone becomes a human's problem — which is what
recall-first *means*, and it is the direct cost of Amendment 2's attention floor. **No threshold
was modified.** Reviewer capacity remains an open stakeholder variable (PLAN §10): the golden set
is deliberately enriched for hard cases and is not a population estimate, but the direction is
real and CP5's load_800 showed the same shape (787 of 800 at REVIEW or above).

### F-9 confirmation on the golden set

`UNKNOWN` is 10 of 50 at baseline and a mean of **41.2 of 50** under ablation — it becomes the
majority potential band the moment data is sparse. Per the accepted F-9 ruling this rate was **not
tuned**, and the CP8 requirement stands: `UNKNOWN` is an unmade judgment and must not be presented
as worse than `LOW`.

---

## CP7 — persistence/API decisions (no scoring change)

CP7 changed no weight, threshold, detector, archetype, normalization rule or golden expectation.
The frozen default model was re-evaluated after the API/config refactor and reproduced CP6 exactly:
recall 1.000 (15/15), ROUTINE leakage 0, 50/50 expectations, golden hashes unchanged.

| id | decision | classification | reasoning |
|---|---|---|---|
| **CP7-1** | `rubric_version` widened from a 12-char prefix to the full 64-char SHA-256. | (b) — the CP7 brief specifies a deterministic SHA-256 of the complete effective config. | Representation, not content. The hash still covers exactly the four rubric sections. `test_assessment.py`'s `len == 12` assertion became `== 64`. |
| **CP7-2** | The DB counter is `founders.assessment_version` (int); the engine's `"cp5.1"` string is persisted as `engine_version`. | (b) — a name collision between the frozen model and the CP7 schema. | Renaming the frozen `Assessment.assessment_version` field was not an option; adding a separate column was. Both are exposed in `assessment_metadata`. |
| **F-17** | `load_800_assessed.json` is a **pre-dedup** artefact; the CP7 pipeline's dedup stage moves 20 founders' confidence by −0.10. | (b) — the reference artefact predates the specified pipeline order, the implementation is correct. | `scripts/cp5_report.py` used per-record `normalize()`; CP7's import is specified as `raw → validate → normalize → dedup → assess`. The 20 affected founders are exactly the `NEVER`-relation pairs, which legitimately carry `CONFLICTING_IDENTITY_HASHES`. 780/780 non-duplicate founders match the frozen file exactly; no attention or potential value moved. `scripts/eval.py` already ran `normalize_corpus`, so CP6's numbers never depended on the artefact. **No code was tuned to close the gap.** |

---

## CP10 — PROMPT FREEZE (recorded BEFORE the first golden-set AI batch)

This is the LLM equivalent of the CP6 golden freeze. The instruction set below was hashed and
recorded **before** any golden-set AI evaluation was run. After the first evaluation the prompt must
not be tuned against golden outcomes and quietly re-run; a prompt-exposed problem is reported and
classified, not optimized away without reviewer approval.

| field | value |
|---|---|
| `prompt_version` | `cp10.1` |
| SHA-256 of the complete instruction set | `50e3a4ef68af10dd161c1282cedc6401e5f79b73430a1a26d188ed1b880b3a76` |
| hash covers | system prompt + schema instruction + JSON response schema + version string |
| source | `backend/app/llm/prompt.py` (`prompt_sha256()`) |
| provider / model for the real run | **not run — no `ANTHROPIC_API_KEY` and no `anthropic` package in this environment** |
| deterministic gate provider | `mock` / `mock-deterministic-v1` (no-finding mode) |
| recorded at | 2026-08-19T18:04:31Z |

**Determinism caveat recorded at freeze time.** Current Claude models **reject** `temperature`,
`top_p` and `top_k` — there is no sampling knob to pin, so bit-for-bit reproducibility cannot be
claimed for a real-provider run and is not claimed anywhere in this checkpoint. The lowest practical
variability the API offers is a low `effort` level plus a strict JSON schema; both are set in
`AnthropicAdapter` and both are echoed into every result's `metadata.settings`. The deterministic
gate is the **MockAdapter**, which is genuinely reproducible (fixed model id, fixed timestamp, no
sampling); real-provider results are exploratory and are labelled as such.

---

## CP8 / CP9 — presentation and workflow decisions (no scoring change)

Recorded here for completeness; the full narrative is in `CHECKPOINT_LOG.md`. Neither checkpoint
touched a weight, threshold, detector, archetype, coverage sub-component, normalization rule or
golden expectation, and both reproduced the CP6 default evaluation exactly.

| id | decision | classification | reasoning |
|---|---|---|---|
| **CP8-1** | `UNKNOWN` is rendered as an **unmade judgment**, never as a worse `LOW` — different chip, different copy, different colour family, never red, never a sort key. | (b) — a presentation decision forced by the accepted F-9 ruling. | The policy is entitled to say "I have not finished reading this". A UI that colours that red converts a statement about *our* evidence into a claim about the *founder*, which is exactly the false-negative failure the whole design is built to avoid. |
| **CP8-2** | A detector **cue** and the aggregate **override** are two separate on-screen statements (F-13). | (b) — presentation. | `AS06` fires `exceptional_progression` and still lands ROUTINE/LOW. Showing only the cue implies an escalation that did not happen; showing only the outcome hides evidence the reviewer should see. |
| **CP8-3** | There is **no "accept the recommendation" shortcut** in the UI. | (b) — a deliberate omission, recorded because it is a feature a reviewer would expect. | A one-click accept would make the machine's recommended action into the human decision by default, collapsing the authority boundary the product exists to enforce. Disposition and stage are separate acts with separate reasons and separate API calls. |
| **CP8-4** | Saving configuration never rescores; a founder whose stored `rubric_version` differs from the effective one reads **"Assessment needs recalculation"**. | (b) — presentation of the CP7 contract. | The alternative — silently showing stale numbers as current — is the one behaviour that would make the rubric-version machinery pointless. |
| **F-18** | `/rescore`'s `assessments_changed` counts assessments **rewritten**, not conclusions **moved**. Reported, not changed. | (b) — a read-model metric, correct for what it measures, mis-readable by its name. | `rubric_version` lives inside the compared assessment JSON, so a config change makes the count equal the population. UI copy was corrected in CP9 rather than the API contract being changed mid-build. Confirmed again at CP11: the live rescore reported `assessments_changed: 800` with `human_state_touched: false`. |
| **F-19** | The Kanban renders 25 cards per column and displays the true column count. | (b) — accepted display cap. | 800 seeded founders sit in `NEW`. A cap that states the real count is honest; a silent filter would not be. |
| **CP9-1** | Due-state is **workflow/time-derived** and is kept in a different field from machine reasoning (`workflow_reasons` vs `why_surfaced`). | (b) — a modelling decision the frozen plan left open. | A keep-warm date arriving is a human commitment coming round, not the model changing its mind. Merging them would let the passage of time look like new evidence. `machine attention: ROUTINE` alongside `workflow: Re-engagement due` is not a contradiction. |
| **CP9-2** | `as_of` is a **read-time lens** and writes nothing; an unparseable date is a 422, never a silent fallback to today. | (b) — interpretation. | Proved by hashing all four tables before and after nine reads across three simulated dates. A simulation that quietly wrote rows would corrupt the audit trail it exists to demonstrate. |
| **CP9-3** | `stuck_days` is an operational display threshold and deliberately does **not** enter `rubric_version`. | (b) — versioning scope. | The rubric hash covers evidence-and-scoring config only. Letting a dashboard display knob change it would make every founder read "needs recalculation" because someone widened a column. |
| **F-20** | Future-dated stuck counts on the synthetic population are fixture-time artifacts (`stage_changed_at` all in 2026). Accepted, not tuned. | (b) — correct arithmetic on synthetic data. | Re-confirmed at CP11: `simulate_time.py` at `as_of=2026-11-19` reports 799 stuck. Worth naming out loud when presenting a simulated-date dashboard. |
| **F-21** | `simulate_time.py` requires a founder already in `KEEP_WARM` and refuses to create one. | (a)-adjacent, deliberate. | Moving a founder is a human act. A demo script that manufactures human workflow state would be demonstrating something the product does not do. Confirmed at CP11 — the script exits with that exact message on a freshly seeded DB, and the demo script in `docs/PRESENTATION.md` therefore puts the human keep-warm move *before* the time simulation. |

---

## CP10 — AI layer decisions

The prompt freeze above was recorded **before** the first golden-set AI batch. These are the design
decisions that constrain the layer, all of which hold in the CP11 final run.

| id | decision | classification | reasoning |
|---|---|---|---|
| **CP10-1** | **The AI layer is raise-only.** `raise_only()` is a MAX against the deterministic attention, tested exhaustively over every (attention × proposed floor) pair. | (b) — an authority decision, not a test change. | It follows directly from the asymmetric business cost: a false negative (a missed exceptional founder) costs more than an extra human review. A layer that can only add reviewer attention has a bounded worst case — wasted review time. A layer that could lower attention would have an unbounded one, and we have no calibration evidence entitling it to that. |
| **CP10-2** | **Invalid AI source paths are discarded, never repaired.** A cited path that does not exist on *this* founder, or holds no value, kills the claim; cross-profile citations are rejected by name. | (b) — a grounding decision. | "Repairing" a citation to a nearby field means the system, not the model, is choosing the evidence — and then a hallucinated claim arrives wearing a valid provenance path. Failing closed keeps provenance meaningful. Silent repair is the single most dangerous convenience available here. |
| **CP10-3** | **Unsupported inferences are retained as diagnostics only** — never a Signal, never scored, never shown as established evidence. | (b) — presentation and scope. | They are the most informative thing about model behaviour (they show where it reaches past its evidence) and the most dangerous thing to present as fact. Keeping them visible-but-inert gets the diagnostic value without the authority. |
| **CP10-4** | **The AI overlay is ephemeral and non-persistent.** Returned by the endpoint; no AI column, no AI field in `Assessment`, no audit event, no `RESCORE` event. | (b) — a persistence decision. | Persisting an unvalidated interpretation makes it indistinguishable from observed evidence on the next read, and it would enter `assessment_version` history as if it were part of the rubric. Ephemerality is what makes "the deterministic assessment is the source of truth" a structural fact rather than a promise. Re-verified at CP11 against the live API: after `POST /ai_check`, stored `AI_INTERPRETED` signals = 0, audit events = 0, decision = `None`, stage = `NEW`. |
| **CP10-5** | **The AI layer may not set disposition or lifecycle stage**, and the result model cannot express one. | (b) — authority boundary, enforced by type. | Asserted by `test_result_model_cannot_express_a_human_decision`. Making it unrepresentable is stronger than making it disallowed. |
| **CP10-6** | **Identity hashes are withheld** from the model (email, LinkedIn, phone, github, crunchbase, name, `mdm_person_id`). No web search, no enrichment, no outside knowledge. | (b) — data minimisation. | The layer's job is contextual interpretation of *supplied facts*. Identity keys add no interpretive value and are the only fields that could turn a local interpretation task into an identity-resolution one. |
| **CP10-7** | **The prompt is frozen, versioned and hashed** (`cp10.1` / `50e3a4ef…`), asserted by test, and was **never tuned against golden outcomes**. | (b) — the LLM equivalent of the CP6 golden freeze. | Without it, "the AI layer helps" becomes unfalsifiable: any disappointing batch can be fixed by editing the prompt until the numbers improve. The freeze is what makes a future lift measurement mean anything. |
| **CP10-8** | **Real-provider lift is NOT measured.** No `ANTHROPIC_API_KEY` and no `anthropic` package were available; the no-op MockAdapter is the only evaluation that was run. | (a)-adjacent — an environment limitation, reported rather than worked around. | The tempting alternative was to present the no-op PASS as though it validated the AI layer. It does not: it proves only non-interference. Stated in `EVAL_REPORT.md` §9, `README.md` and `docs/PRESENTATION.md` §F. |
| **F-22** | Bit-for-bit reproducibility of a real provider run is **not claimed**. | (b) — a limit of the provider, recorded. | `temperature`, `top_p` and `top_k` are rejected by current Claude models, so there is no sampling knob to pin. The deterministic gate is the MockAdapter; `effort: low` plus a strict JSON schema is the lowest practical variability available, and both are echoed into every result's `metadata.settings`. |
| **F-23** | The grounding check is a **contradiction detector, not a truth check**. | (b) — a known limit of the validator, not papered over. | It proves a cited path exists and holds a value, and it fails closed when a quoted literal is absent from the values cited. It cannot establish that an *unquoted paraphrase* is entailed by those values. Everything it cannot prove is left visible to the human reading the claim — which is the correct response to a validator with a known ceiling. |
| **F-24** | `GET /config` gained a read-only `ai_layer` **status** block. | (b) — one additive, non-rubric API field. | Provider, availability, prompt version and prompt hash, so the UI can label the optional action honestly *before* a person spends a call on it. It is status, not configuration: it enters no rubric section, no `rubric_version`, and no `PUT`. Verified at CP11: with no key it reports `available: false`, `detail: "ANTHROPIC_API_KEY is not set"`, and the rubric hash is unchanged at `4714815e84e4c2ca…`. |

---

# CP11 — final regression adjudication

One test failed on the final clean run. It is classified here before the fix, under the same
(a)/(b) rule as every earlier checkpoint.

**CP11-1 — `test_mvp_stage_path` asserted a keep-warm date against the LOCAL calendar day.**

Classification: **(b) — the test's assumption was wrong; the product is correct.**

*Symptom.* `assert body["keep_warm_until"] == add_months(date.today(), 6).isoformat()` failed with
expected `2027-02-20`, actual `2027-02-19`.

*Diagnosis.* The product dates everything from UTC: `workflow_service.set_stage` anchors keep-warm on
`stamp.date()` where `stamp = utcnow()`, and `views.py` resolves a default `as_of` the same way
(`as_of or utcnow().date()`). The test used `datetime.date.today()` — **local** time, the only
local-clock reference anywhere in the suite. The machine running the final regression is in IST
(UTC+05:30) and the local date had rolled to 2026-08-20 while UTC was still 2026-08-19, so the test
and the product disagreed by exactly one day.

*Why this is (b), not (a).* CP9 documents timezone-independence as an intended property — "no clock
or browser timezone takes part". A UTC-anchored product with a locally-anchored test is a test that
is wrong for 5.5 hours a day in this timezone (and some window in every timezone east of UTC); it
was passing in earlier checkpoints only because those runs happened before the local date rolled
over. Changing the *product* to local time would have made the same test pass while breaking the
documented property and making stored dates depend on where the server sits.

*Fix.* The assertion now reads `add_months(utcnow().date(), 6)` — the same clock the product uses.
The assertion is still an exact-value assertion on a specific date; nothing was weakened, widened to
a range, or made tolerant of a one-day error. The only change is *which* clock both sides read.

*Scope.* One line plus one import in `backend/tests/test_api_workflow.py`. No product code, config,
weight, threshold, golden case or prompt was touched. `test_resurfacing.py:171` also calls
`date.today()`, but passes it in as an explicit `as_of` value — any date works there, so it is not
affected. Full suite after the fix: **1536 passed**.

**CP11-2 — the measuring instruments were extended; the system was not.**

`scripts/ai_batch.py` gained a `compare()` function (the body of its own `main()`, extracted) and
`scripts/eval.py` calls it to render §9 of `EVAL_REPORT.md`. Classification: **(b) — instrument
change, in the spirit of CP6-1.** The motive is anti-drift: the CP10 AI numbers were previously
transcribed into prose by hand, which is exactly how a report starts disagreeing with the code that
produced it. `make eval` now regenerates the AI comparison from the same instrument the CP10 gate
used, key-free and offline. `scripts/eval.py` also now prints explicit baseline→mean ablation deltas
for confidence and review-queue rate, which were previously only inferable from the table. Verified
no drift: the deterministic §1–§8 numbers, the golden hashes and the 1536-test suite are unchanged.

**CP11-3 — no overfitting occurred at CP11, and nothing was tuned to improve a final number.**

| thing that could have been tuned | state at CP11 |
|---|---|
| signal weights, thresholds (65 / 0.6 / 30 / 40) | untouched — effective rubric hash `4714815e84e4c2caa9f0795f3dbf16101d88378200c416ae2184d1a1515d18aa`, the frozen default |
| golden cases | untouched — `cases.yaml` `6e128c9d…`, `profiles.json` `8de59bea…`, both matching the pre-eval freeze recorded at CP6 |
| prompt | untouched — `cp10.1` / `50e3a4ef…`, matching the CP10 freeze |
| tier lists, health taxonomy, archetype rules | untouched |
| golden expectations | untouched |
| detector parameters | untouched |

A config weight *was* changed live during the CP11 demo dry-run (`education_signal` 10 → 4) to prove
that rescoring cannot mutate human state. It was changed back in the same session and the effective
rubric hash was verified equal to the frozen default afterwards; the demo database was then rebuilt
from scratch (`rm founder.db && make seed`) so the handoff state is the documented one.

---

## POST-CP11 — cp10.2, a follow-up experiment (NOT a fix to cp10.1)

**CP10.2-1 — cp10.1 is preserved intact and its conclusion is unchanged.**

The cp10.1 prompt text, `PROMPT_VERSION`, `prompt_sha256()`
(`50e3a4ef68af10dd161c1282cedc6401e5f79b73430a1a26d188ed1b880b3a76`), response schema,
aggregation rule (`overlay.py`), service and evaluation script are **byte-unchanged**.
The five-call real-provider run remains the **development / discovery** set and its
recommendation remains **C — DO NOT ENABLE**. No checkpoint record has been rewritten to
imply otherwise; `docs/CP10_1_PRESERVED.md` records the freeze, the plan, the outcome and
one honest gap (the per-call stdout was never written to a file and is not in the repo).

**CP10.2-2 — the observed failure was a scale mismatch, and the response is architectural,
not a prompt tweak.** cp10.1 fed the model's self-rated `strength` into a rule calibrated
for detectors, so `2 × MEDIUM → PRIORITY_REVIEW` fired on grounded-but-mundane facts.
cp10.2 separates **grounding** (validator-owned, per finding) from **notability**
(`novelty`, a request the deterministic `contextual_policy` adjudicates), removes the
`MEDIUM` rung entirely, adds a structural **relationship** gate (citations must span ≥2
fact groups), caps AI movement at **one attention level**, and makes accumulation
impossible. Classification: **(b) — the cp10.1 design was wrong about where the decision
belonged**, not (a) a mis-set threshold.

**CP10.2-3 — additive only; deterministic behaviour is untouched.** New modules
(`contextual_prompt`, `contextual_types`, `contextual_policy`, `contextual_service`,
`contextual_mock`) plus one enum member (`DiscardReason.INVALID_NOVELTY`, which cp10.1
can never emit) and one subclass (`ContextualOpenAIAdapter`). No weight, threshold,
normalization rule, confidence semantic, detector, archetype, safety-policy rule,
workflow rule, golden case or golden expectation changed. Verified after the work:
backend suite **1688 passed**; `make eval` **50/50, recall 1.000, ROUTINE leakage 0**;
golden hashes `6e128c9d…` / `8de59bea…` and effective rubric `4714815e…` unchanged.

**CP10.2-4 — frozen before spending.** `cp10.2` /
`10d0bbe12e8b0ce4b92fd644718ce6f0bf314f9a61588742ea0e6ca77c7000dd`, asserted by test and
re-checked by the evaluator, which aborts before any paid call on a mismatch. The 30-case
holdout, its deterministic redistribution rule and the success criteria were all declared
before the first real cp10.2 call. Details in `docs/CP10_2_DESIGN.md`.

**CP10.2-5 — evaluation-governance amendment, accepted before any paid call.** No frozen
component changed: prompt, prompt semantics, schema semantics, contextual policy,
authority policy, holdout membership, model, reasoning effort, deterministic system,
golden cases, thresholds and weights are all byte-identical to the accepted
implementation (proved by the manifest's per-file SHA-256 round-trip). Four governance
changes: (i) classifications produced by the implementing AI assistant are recorded as
`PROVISIONAL_ANALYST_CLASSIFICATION` and explicitly *not* described as human labels or
ground truth — no second provider call judges anything, and the raw claim, why_notable,
citations, fact groups and both verdicts are retained so they can be independently
overturned; (ii) the numeric success criteria are frozen (≥11/13 controls un-escalated,
≥3 headroom cases with USEFUL_CONTEXTUAL findings, ≥2 JUSTIFIED escalations among them,
≤2 FALSE_POSITIVE escalations, JUSTIFIED > FALSE_POSITIVE) as **evaluation criteria
only**, wired into no scoring path; (iii) `docs/cp10_2_experiment_manifest.json` freezes
the whole experiment rather than just the prompt, and the evaluator aborts before
spending if any of the nine hashed components has moved; (iv) F-23 is retained verbatim —
grounding validates *provenance integrity*, not semantic entailment for arbitrary
paraphrases, and semantic overreach is reported separately from provenance.

**CP10.2-6 — optional stopping is designed out.** The holdout runs all 30 pre-declared
cases. The only stop conditions are a hard safety-invariant failure, the cost ceiling, a
provider/auth failure, or an implementation defect. `safety_breach()` reads structural
facts only; no utility number is consulted anywhere in the decision to make the next
call, so "results look good/bad/settled" is not merely disallowed but unreachable. A
defect stops the run with results preserved — nothing is fixed and resumed inside the
same holdout.

---

## POST-CP11 — REAL-PROVIDER DECISION LEDGER (OpenAI, `gpt-5-mini-2025-08-07`)

Appended after both real-provider experiments completed. Prior entries are unchanged and remain
statements of what was true when written. Evidence:
[`EVAL_REPORT_REAL_PROVIDER.md`](EVAL_REPORT_REAL_PROVIDER.md),
[`cp10_2_experiment_manifest.json`](cp10_2_experiment_manifest.json),
[`cp10_2_holdout_raw.jsonl`](cp10_2_holdout_raw.jsonl).

**RP-1 — cp10.1: do not enable AI attention authority.**

*Observation.* The LLM's self-rated `strength` does not share the semantics of deterministic detector
strength. A detector's `MEDIUM` means "a specific, named detector fired"; the model used `MEDIUM` for
"true and well grounded".

*Decision.* **Do not enable cp10.1 attention authority. C — DO NOT ENABLE.**

*Reason.* Grounded-but-mundane facts could trigger the deterministic exceptional aggregation
(`2 × MEDIUM → PRIORITY_REVIEW`); in a 5-call discovery run one clearly ordinary founder was promoted
ROUTINE → PRIORITY_REVIEW and net new useful surfaces were 0. Safety, grounding, persistence
boundaries and the tested injection case all held — the failure was calibration, not containment.
**Grounded ≠ notable.** This finding is preserved as observed and is not softened by cp10.2.

**RP-2 — cp10.2: retain as evidence of contextual-assistant potential; do not enable automatic
escalation.**

*Observation.* Separating grounding, relational context, novelty and deterministic authority
eliminated the observed cp10.1 queue-pollution mode: 29 of 35 findings were grounded-but-mundane and
**none** moved attention; 13/13 controls stayed un-escalated (10/10 of the parsable responses).

*Decision.* **Retain cp10.2 as evidence of contextual-assistant potential. Do not enable automatic
attention escalation.** Recommendation **B — PROMISING, NEEDS HUMAN-LABELLED VALIDATION**.

*Reason.* The frozen escalation gates failed: 0 justified escalations (required ≥2) and 1
false-positive, so justified > false-positive is false. The sole escalation restated a detector that
had already fired, overriding a deliberate deterministic decision with no new information. Useful
contextual observations did clear their gate (4/10 headroom cases), which is what earned the
display-only role. **Notable ≠ positive evidence deserving higher priority.**

**RP-3 — deployment authority.**

> **Rules prioritize. AI notices. Humans interpret.**
> The model proposes contextual meaning; deterministic policy and humans govern authority.

Until reviewer-labelled validation exists: the deterministic system owns priority; AI findings may be
shown as **experimental contextual observations**; humans interpret their significance; AI does not
change disposition or workflow; AI-generated contextual evidence does **not** automatically change
attention. The cp10.2 code still contains the bounded one-level raise — that is what the holdout
tested — so this is a deployment posture, not a claim about the implementation.

**RP-4 — the next validation step is human labels, not prompt tuning.**

Prompt tuning against these 30 outputs would be overfitting to a synthetic sample judged by
provisional AI-assisted classifications. The next meaningful validation is reviewer-labelled data:
*was this AI observation useful? · was it already obvious from the profile? · did it change reviewer
understanding? · did it change the engagement decision? · was it positive, negative or ambiguous?*
Only after that feedback should additional AI authority be reconsidered.

**RP-5 — malformed structured-output contract (3/30).**

*Observation.* `RL04`, `RL09` and `RL12` returned 13–14 `source_fields` against a Pydantic contract
allowing 12, so the whole response was rejected. The system failed closed to deterministic behaviour
and reported the failure honestly.

*Decision.* Recorded as a **production-hardening item, not a tuning decision**: provider
structured-output guidance should be aligned with application field-cardinality constraints before
production use. Not fixed here, and the holdout was **not** re-run afterwards — the frozen evaluation
evidence stands as observed, including its 3/30 malformed rate.
