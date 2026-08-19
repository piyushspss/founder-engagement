# Founder Engagement Workflow — Stakeholder Presentation

_Redesign Health take-home · Piyush Chandra · Senior Director, Applied AI_

Content source for a 10–15 minute presentation. `PLAN.md` v2.3 (FROZEN) is the source of truth for
the model; `EVAL_REPORT.md` holds the measured numbers; `EVAL_DECISIONS.md` holds every adjudicated
decision. Every number in this document is a real number from the final run.

---

## First 2 Minutes

Say roughly this, conversationally:

1. When I read the brief, I thought I was being asked to build a founder-scoring model.
2. Fact-finding changed the problem definition on me — the bottleneck isn't scoring, it's
   prioritization and the operating workflow around it.
3. The cost structure is asymmetric: missing a great founder is much worse than reviewing an extra
   candidate. That one sentence drove almost every design decision.
4. The data is genuinely rich, and genuinely incomplete and contradictory — missing dates, null
   `is_current`, overlapping roles, duplicate people, totals that don't add up.
5. So I built a recall-first, human-in-the-loop system rather than a ranker.
6. Deterministic logic handles the evidence we can specify reliably — titles, tenure, domain
   exposure, progression, scope, credentials — and it shows its work on every claim.
7. Uncertainty **increases review** rather than silently lowering someone. A profile we haven't
   finished reading can't be called low potential.
8. Humans keep the business decisions: disposition and lifecycle stage are human-only, by
   construction, not by convention.
9. AI is in there as a bounded contextual second set of eyes. After testing it with a real provider,
   I'd keep its observations display-only for now — deterministic logic retains prioritization
   authority, and humans interpret the context.
10. What the MVP demonstrates is policy consistency and workflow value. What it does **not**
    demonstrate is predictive accuracy about founders — that needs real outcome labels, and that's
    the next step.

---

## A. Problem framing

> **I initially thought this was a founder-scoring problem. Fact-finding showed it was actually a
> prioritization and operating-workflow problem where the cost of missing an exceptional founder is
> higher than the cost of reviewing an extra candidate.**

The current workflow:

```text
LinkedIn / sourcing sources
        ↓
Excel
        ↓
ATS
        ↓
manual review
        ↓
nurturing / keep-warm
        ↓
periodic spreadsheet review
```

The pain isn't "we don't have a score." The pain is that attention is allocated by whoever opens the
spreadsheet, state lives in three places, keep-warm commitments are remembered by hand, and there is
no record of *why* anyone concluded anything. A model score dropped into that workflow doesn't fix
it — and a model that silently ranks people out actively makes the expensive failure mode worse.

---

## B. What I learned in fact-finding

* **Recall over precision.** Don't miss good founders; false positives are acceptable.
* **Score the person, not the idea** — the `(-1→0)` funnel evaluates the founder. Idea fields are
  out of scope and reserved for `(0→1)`.
* **No special referral scoring preference.** Source is metadata, stored and never scored.
* **Messy and incomplete data is normal, not exceptional.** Any design that assumes clean records
  is designing for a dataset that doesn't exist.
* **"Spikiness" matters but doesn't reduce to one scalar.** Exceptional evidence needs its own path,
  or the average washes it out.
* **The weekly workflow and resurfacing are first-class needs**, not reporting garnish.
* **The system has to replace operational tracking**, not merely provide a model score.

---

## C. Assumptions (A1–A11, said out loud)

These are assumptions, not findings. Every one is testable and reversible — see §K.

| # | Assumption |
|---|---|
| **A1** | **Users and team size:** sourcing team of 2–5, weekly batch review; leadership views the dashboard. |
| **A2** | "Decision" = review disposition (Potential / Not now / Needs info / Needs review) + stage moves + next-action owner. No email or calendar in the MVP. |
| **A3** | **`(-1→0)` scope:** evaluate the founder only; idea fields ignored. |
| **A4** | **Referral/source is stored, not scored.** |
| **A5** | **The provided schema is representative** — hashed IDs, headline, rich `experience[]` with company metadata, `education[]`, totals, location, and many nulls. |
| **A6** | **Messiness we handle:** missing dates, `is_current` null vs `date_to` null, overlapping roles, degree-string variance, institution name variants, duplicate persons, inconsistent ordering, missing company sizes, contradictions (total months ≠ sum of roles). |
| **A6b** | **Conservative dedup:** same `mdm_person_id` → same person; one strong hash match → *probable* duplicate (flag, don't merge); multiple matches → high-confidence duplicate; **conflicting hashes → never auto-merge.** |
| **A7** | **"Premier institution" / "premium health company" = editable tiered lists** + fuzzy match. Unknown is **neutral**, never negative. |
| **A8** | **Explicit founder-title rule:** founder evidence comes only from explicit titles (Founder, Co-Founder, Founding CEO/CTO…). CEO/President/MD = leadership evidence only. Suspected-but-unconfirmed → `founder_evidence: POSSIBLE`, never `true`. |
| **A9** | **Review Priority is not founder quality and not a probability.** It is "strength of currently observable evidence that this founder deserves Redesign attention." |
| **A10** | **Local, single-tenant MVP:** ≤5h build, no auth. |
| **A11** | **Bounded AI usage:** (a) code generation, (b) synthetic data, (c) a narrow LLM evidence layer — structured JSON, supplied facts only, can only *raise* to review, on-demand, (d) profile summary. |

> **Post-evaluation update to A11.** A11 is reproduced faithfully from the frozen plan and states the
> *original AI authority hypothesis* — a narrow evidence layer that could raise to review.
> Real-provider testing later narrowed the **recommended deployment posture** to display-only
> contextual observations; see **§F2**. The assumption is left as written because the chronology is
> the point: hypothesis → experiment → evidence → changed deployment decision.

The four I'd underline in the room: **A9** (the score is not a quality claim), **A8** (we don't
guess who founded something), **A7** (unknown is neutral), **A4** (referrals get no thumb on the
scale).

---

## D. Solution — five capabilities

1. **Import + normalization** — JSON/CSV → canonical profile, conservative dedup, data-quality
   flags, provenance on every field.
2. **Explainable assessment** — Review Priority (0–100), potential, evidence confidence, archetype,
   exceptional signals, missing/contradictory data. Every signal carries its source fields and
   whether it is `OBSERVED`, `DERIVED` or `AI_INTERPRETED`.
3. **Safety policy / attention prioritization** — ordered, unit-tested rules and guards; uncertainty
   raises review; missing data is never negative evidence.
4. **Human engagement workflow** — disposition, stage machine, owner, next action, notes, keep-warm
   3/6/9 months, re-engagement resurfacing, full audit trail.
5. **Operating dashboard** — the weekly Excel review, replaced.

The four output dimensions are deliberately **orthogonal**, which is what lets the product be honest:

```text
potential:          HIGH | MEDIUM | LOW | UNKNOWN      ← a claim about the founder
attention:          PRIORITY_REVIEW | REVIEW | ROUTINE ← a claim about our time
data_state:         SUFFICIENT | PARTIAL | NEEDS_INFORMATION ← a claim about our evidence
confidence:         0.00–1.00                          ← how much of the needed evidence we have
```

`PRIORITY_REVIEW + UNKNOWN` is a normal, meaningful output: *look at this person now, and we can't
yet say how good they are.* That combination is exactly what recall-first requires, and a
one-dimensional score cannot express it.

Two guards are worth stating explicitly because they are the whole safety argument:

* **`ROUTINE` is a positive assertion** — "there is sufficient evidence to be comfortable not
  prioritizing this founder" — not merely the absence of a reason to look. A profile we haven't
  finished reading cannot earn it.
* **`LOW` requires sufficient evidence.** Incomplete evidence cannot support a *negative* conclusion,
  because the missing part is exactly where the positive evidence would have been. It *can* leave a
  positive conclusion standing, because what was observed was still observed.

---

## E. Why this AI architecture

> **Deterministic logic handles evidence we can specify reliably. The LLM is reserved for contextual
> interpretation that rigid rubrics may miss.**

The authority hierarchy:

```text
Observed / deterministic evidence
        ↓
Deterministic assessment
        ↓
Optional LLM second set of eyes
        ↓
Grounding / provenance validation
        ↓
Raise-only attention overlay
        ↓
Human decision
```

The governing principle:

> **AI is given only as much authority as we can currently validate.**

### Why the whole founder-ranking problem is NOT one LLM prompt

* **No outcome labels demonstrating Redesign-specific calibration.** There is nothing to calibrate a
  judgment model against, so "the model thinks this founder is a 78" is an unfalsifiable number.
* **Weaker reproducibility.** The deterministic core produces the same answer twice, forever, and
  its config is hashed into `rubric_version`.
* **Harder auditability.** A reviewer can ask "why?" of a rule and get a field list. A prompt gives
  you prose.
* **Model and provider drift.** A silent upstream model change would silently re-rank the pipeline.
* **Harder attribution of improvements.** If everything is one prompt, no one can tell whether a
  better week came from the prompt, the data, or the reviewers.
* **Unnecessary cost and latency** for features — tenure arithmetic, tier lookups, title
  classification — that a rule computes exactly, for free, in microseconds.
* **Harder to separate evidence from judgment.** The product's core value is showing a reviewer the
  *facts* separately from the *inference*. One prompt collapses those into a paragraph.

### What the AI layer actually is (CP10 design — the implemented capability)

> This subsection describes the layer **as built and as tested**, at the `cp10.1` freeze. It is
> architecture, not a deployment recommendation. The authority posture was narrowed after the
> real-provider evaluation — see **§F2**; the two are kept separate deliberately.

* The LLM receives **normalized supplied facts only** — no web search, no enrichment, no outside
  knowledge.
* **Identity hashes are withheld** (email, LinkedIn, phone, github, crunchbase, name,
  `mdm_person_id`).
* The prompt is **frozen, versioned and hashed** — `cp10.1`,
  `50e3a4ef68af10dd161c1282cedc6401e5f79b73430a1a26d188ed1b880b3a76` — recorded *before* the first
  golden-set batch and asserted by test.
* **Strict structured output.** Extra fields are rejected; malformed JSON yields no evidence.
* Every evidence **source path is validated against populated fields in that founder's record**.
* **Bad paths are discarded, never repaired** to a nearby one. Cross-profile citations are rejected
  by name.
* **Unsupported inferences are retained as diagnostics only** — never a signal, never a score, never
  presented as established evidence.
* The AI may **only raise** attention (`raise_only()` is a MAX, tested exhaustively over every
  attention × proposed-floor pair). *Implemented capability; the cp10.2 successor caps it further at
  one level — and after the holdout, the recommendation is not to use it at all (§F2).*
* The AI **cannot set disposition or stage** — the result model cannot even express one.
* The overlay is **ephemeral and non-persistent**: returned by the endpoint, never stored. No AI
  column, no AI field in `Assessment`, no audit event, no `RESCORE` event.
* Provider, model, prompt version, prompt hash and effort **metadata are returned** with every
  result.
* **The system works fully without AI.** With no key, the endpoint reports `unavailable` and changes
  nothing; it never silently substitutes the mock.

Prompt injection is handled structurally rather than by instruction alone: profile strings are DATA,
the system prompt says so by field name, and an instruction embedded in a headline still cannot
ground a claim because the provenance whitelist has no path for it. *Real-provider injection
resistance was exercised in the cp10.1 development experiment; it was deliberately **not** exercised
in the cp10.2 holdout (§I.3c).*

---

## F. AI evaluation result — be intellectually honest

```text
                    Deterministic baseline    Deterministic + no-op AI
Recall                     1.000                      1.000
Leakage                        0                          0
Queue rate                  0.62                       0.62
```

Per-case attention is **identical on all 50 cases**. Accepted cues 0, discarded items 0, unsupported
inferences 0, escalations 0. **Measured recall lift: 0.**

> "The baseline is saturated on our designed golden set, so the no-op adapter correctly produces zero
> lift. That is not evidence that the real LLM adds no value; it means the golden set cannot
> demonstrate incremental contextual lift without real-provider runs and ultimately reviewer-labelled
> data."

> "I deliberately didn't assume the LLM belonged in the system. I built an isolated intervention and
> an ablation framework so the LLM has to earn its place through measurable incremental value."

**What this proves:** enabling the AI subsystem does not itself alter deterministic behavior.
**What it does not prove:** anything about real-provider lift.

> **[True at CP10/CP11.] Real-provider evaluation was not run because no provider API key/SDK
> environment was available. Therefore incremental real-LLM lift is unmeasured.**
>
> **Since then it HAS been run — see §F2.** Two bounded OpenAI experiments were completed
> post-CP11. The line above is preserved as what was true at the time, not as the current position.

### The metrics that would make the LLM earn its place

None of these is claimed today:

* incremental must-surface recall, **measured only where the baseline has headroom** (the current
  golden set has none);
* incremental *useful* founders surfaced, as judged by a reviewer;
* reviewer acceptance rate of AI-contributed evidence;
* unsupported-inference rate — how often the model reaches past its evidence;
* review-queue expansion — extra human load per additional useful surface;
* latency and cost per additional useful surface;
* downstream reviewer/outcome lift, once outcome labels exist.

---

## F2. What happened when I tested the LLM for real?

*The point of this section is evidence-based authority design, not an LLM demo.*

### Hypothesis

> A constrained LLM might identify unusual contextual evidence the deterministic rubric misses.

### cp10.1 — safe, but too noisy

Five real OpenAI calls (`gpt-5-mini`, ≈$0.011). Safety held: grounding held, persistence boundaries
held, the injection case was exercised and resisted, the model could not lower attention.

But the LLM cited real evidence and then rated ordinary facts `MEDIUM` — and cp10.1 fed that word
straight into the deterministic exceptional rule, where `MEDIUM` means "a named detector fired". Two
mundane observations satisfied `2 × MEDIUM → PRIORITY_REVIEW`. One clearly ordinary founder went
**ROUTINE → PRIORITY_REVIEW**. Net new useful surfaces: **0**.

> **Grounded ≠ notable.**

**We froze the failure rather than tuning it away.** cp10.1's recommendation is preserved as
**C — DO NOT ENABLE**, and cp10.2 improving on it does not make it a success.

### cp10.2 — changed the architecture, not the wording

> **The LLM proposes contextual observations; deterministic code decides authority.**

```text
cp10.1                              cp10.2
LLM self-rated strength             LLM contextual observation
        |                                   |
        v                           grounding validation
exceptional aggregation                     |
        |                           relationship / context test
        v                                   |
attention authority                 novelty test
                                            |
                                    deterministic authority policy
```

Added: a relationship requirement (≥2 distinct fact groups); `NONE / LOW / HIGH` novelty with the
`MEDIUM` rung deleted; **no accumulation by count**; a **maximum one-level raise**; a frozen 30-case
holdout with the five development cases excluded in code, hashes recorded in a manifest before the
first paid call.

```text
30 calls
27 parsable responses               (3 malformed — a 12-path contract mismatch, failed closed)
13/13 controls un-escalated         (10/10 of the parsable ones)
4/10 headroom cases with useful contextual observations
0 justified escalations
1 false-positive escalation
$0.061 estimated API cost
```

The one escalation restated a detector that had already fired — the AI overrode a deliberate
deterministic decision while adding no new information.

> **Notable ≠ positive evidence deserving higher priority.**

The useful observations were real but directionally ambiguous: a same-employer Quality → Regulatory
function switch; concurrent advisory roles across software and healthcare; a VP-of-operations →
entry-level-marketing move. Any of those could be a strength, a problem, or a data artefact. That is
exactly why they belong in front of a person.

### The deployment decision

> **Rules prioritize. AI notices. Humans interpret.**
>
> **The model earned permission to suggest context, not permission to change priority.**

Display-only contextual assistance, with deterministic logic keeping prioritization authority and
automated LLM-driven escalation left not enabled until human reviewer labels justify it. Two frozen
gates failed and I am not reinterpreting them after the fact. Final call: **B — PROMISING, NEEDS
HUMAN-LABELLED VALIDATION**.

Honest framing of my own evidence: the utility classifications behind "4/10" are **provisional
AI-assisted analysis, not independent human ground truth**, on 30 synthetic profiles, one provider,
one model snapshot. That is why the recommendation is "get labels", not "ship it".

Full evidence: [`EVAL_REPORT_REAL_PROVIDER.md`](EVAL_REPORT_REAL_PROVIDER.md) ·
[`CP10_1_PRESERVED.md`](evidence/ai/CP10_1_PRESERVED.md) · [`CP10_2_DESIGN.md`](evidence/ai/CP10_2_DESIGN.md) ·
[`cp10_2_experiment_manifest.json`](evidence/ai/cp10_2_experiment_manifest.json) ·
[`cp10_2_holdout_raw.jsonl`](evidence/ai/cp10_2_holdout_raw.jsonl).

---

## G. Demo script

Preconditions (from a clean clone): `make setup && make seed`, then `make api` and `make ui` in
separate terminals, then <http://localhost:5173>. The seeded demo population is 800 **synthetic**
founders — say so once, out loud, at the start.

**The workflow and the business problem come first. The AI architecture follows. Do not open with
the AI.**

| # | Step | What to say / show |
|---|---|---|
| 1 | **Priority Queue** (home) | Open with the actual question: *"Who deserves my attention today?"* KPI strip: 315 Priority Review, 472 Review, 13 Routine. This screen replaces "open the spreadsheet and scroll." |
| 2 | Open a **Priority Review** founder | Click through from the queue, not from a URL. |
| 3 | The four dimensions | Potential, evidence confidence, attention, archetype, data state — four visually different controls, because they are four different claims. |
| 4 | Archetype + why surfaced | e.g. *Clinical Expert*, surfaced by 2 MEDIUM exceptional detectors plus STRONG healthcare depth and leadership. |
| 5 | **Evidence and provenance** | Expand "why this assessment?": the policy trace, then every signal with weight, value, weighted contribution, strength, provenance type and the exact source fields. This is the "why did you conclude this?" answer. |
| 6 | **Missing / contradictory data** | Filter `data_state=NEEDS_INFORMATION` — 84 founders. Show one with contradictions (overlapping roles, totals that don't add up) and note that **all 84 sit at REVIEW or above**: missing data never lowers attention. |
| 7 | **Uncertainty → review, not LOW** | Filter `attention=REVIEW & data_state=PARTIAL` — 230 founders. Open one: weak observable evidence but incomplete data, so potential is `UNKNOWN`, not `LOW`, and it stays in the queue. Then say the line: *`ROUTINE + PARTIAL` and `LOW + PARTIAL` are structurally unreachable — 0 of 800.* |
| 8 | **Make an explicit human decision** | Set disposition = Potential, with actor and reason. Point out there is **no "accept the recommendation" button** — the machine never converts its own recommendation into a decision. |
| 9 | **Move the workflow** | `POTENTIAL → NURTURING → KEEP_WARM (3 months)`. Each move carries a reason and is audited. Keep-warm records a real date (e.g. 2026-11-19). |
| 10 | **Simulate the future date** | `?as_of=2026-11-19` on the queue and dashboard, or `python scripts/simulate_time.py`. The founder becomes **Re-engagement Due**. Note two things: the machine assessment did not change, and the simulation writes **nothing** (the script hashes all four tables before and after to prove it). |
| 11 | **Re-engage and show audit history** | `KEEP_WARM → NURTURING` as a human act. The obsolete keep-warm date is cleared and audited; disposition, owner, notes and the whole assessment survive. Then show the audit trail: who, when, field, from → to, reason. |
| 12 | **Pipeline / dashboard** | Kanban by stage, weekly intake, ageing, stuck (>14 days, excluding KEEP_WARM/CLOSED/DEAL), re-engagement due, review-queue size 787, low-confidence 4.25%. This is the weekly Excel review. |
| 13 | **Change a config weight and rescore** | Config drawer: `education_signal` 10 → 4. Save — note the founder now reads **"Assessment needs recalculation"**, because saving config deliberately does *not* rescore. Then run Recalculate: 800 reassessed, our founder's broad score moves 74.17 → 68.17, `assessment_version` 1 → 2. |
| 14 | **Prove the human state survived** | Same founder, immediately after the rescore: disposition still Potential *with the original reason*, stage still Nurturing, notes and audit intact. The rescore response says `human_state_touched: false`. **The rubric is ours to change; the human record is not the rubric's to touch.** Restore the weight to 10 and rescore back. |
| 15 | **AI layer status — the product needs no LLM** | `GET /config → ai_layer` reports the provider, whether it is available, and the prompt version/hash. **Read whatever it says on the machine in front of you** — availability depends on local configuration, and no key is shown, named or needed. Say plainly: **the product you have been watching for fourteen minutes needs no LLM at all.** The AI layer is optional and provider-isolated; every deterministic number on screen was produced without it. |
| 16 | **What the real-provider experiment actually found** | **No live model call is required** — these are recorded results from the frozen 30-case cp10.2 holdout (`docs/evidence/ai/cp10_2_holdout_raw.jsonl`). Show one or two: **AS04** — the deterministic trajectory signal sees *level* movement; the LLM noticed a *functional* transition, Quality Engineer → Regulatory Affairs Lead inside the same medical-device employer. That is useful context the rubric does not explicitly model. **AS10** — multiple simultaneous `Advisor` roles across employers: a **pattern consistent with** portfolio/advisory work (not a claim of demonstrated bridging capability). Both are **contextual observations, display-only under the recommended posture** — 4 of 10 headroom cases produced something like this, and the model self-rated 34 of 35 findings as LOW, so nothing ordinary moved. |
| 17 | **Authority boundary — the lesson** | Say both lines out loud: **"Rules prioritize. AI notices. Humans interpret."** and **"The model earned permission to suggest context, not permission to change priority."** Reload the founder: 0 stored `AI_INTERPRETED` signals, 0 new audit events, decision and stage untouched. The deterministic assessment is durable; the AI observation is ephemeral and never enters the record; AI never touches disposition or stage. And on the frozen holdout evidence — 0 justified escalations, 1 false positive — **automatic AI attention escalation is NOT recommended.** The code does contain the bounded one-level raise, because that is exactly what the experiment tested; it should stay unused until reviewer-labelled validation supports it. |
| 18 | **End on evaluation + limitations** | §H and §I below. Do not end on the AI. |

Two demo honesty notes:

* `scripts/simulate_time.py` **requires** a founder already in KEEP_WARM and refuses to create one —
  moving a founder is a human act (F-21). So step 9 must happen before step 10.
* At a 2027 `as_of` the dashboard legitimately reports 799 founders "stuck", because the synthetic
  population's `stage_changed_at` values all sit in 2026 (F-20). Name it rather than letting someone
  catch it.

---

## H. Evaluation

**50 hand-authored golden scenarios**, expected outcomes written and **hashed before the assessor
was ever run against them** (`cases.yaml` `6e128c9d…`, `profiles.json` `8de59bea…`, recorded at
2026-08-19T16:24:43Z, verified still unchanged in the final run).

| group | cases | purpose |
|---|---|---|
| must_surface | 15 | founders the system must not miss |
| reasonable_low | 15 | founders it is reasonable not to prioritize |
| ambiguous_spiky | 10 | genuinely hard calls, unusual shapes |
| data_quality_adversarial | 10 | duplicates, contradictions, missing history, CEO-not-founder, elite-school-only |

**Final actual numbers:**

| metric | value |
|---|---|
| **must_surface recall** (primary metric) | **1.000** (15/15) |
| **must_surface leakage into ROUTINE** (hard requirement: 0) | **0** |
| expectation pass rate (all four dimensions + evidence assertions) | **100%** (50/50) |
| review-queue rate | 62.0% (31/50) |
| precision *(informational only — no outcome labels exist)* | 0.484 (15/31) |

Per group, all 50 expectations passed: must_surface 15/15 (12 PRIORITY_REVIEW, 3 REVIEW),
reasonable_low 15/15 (13 ROUTINE, 2 escalated), ambiguous_spiky 10/10, data_quality_adversarial 10/10.

**Recall is not achieved by sending everyone to REVIEW.** 12 of 15 must-surface cases are
PRIORITY_REVIEW, and **6 of 15 surfaced with no exceptional signal at all** — the broad evidence
model carried them.

**Missing-data ablation** (30% of decision-relevant fields nulled, 5 seeded runs):

| metric | baseline | 5-run mean | Δ |
|---|---|---|---|
| must_surface recall | 1.000 | 1.000 | **+0.000** |
| mean confidence | 0.907 | 0.492 | **−0.415** |
| review-queue rate | 0.620 | 0.984 | **+0.364** |
| PRIORITY_REVIEW/REVIEW → ROUTINE downgrades | — | **0** | required 0 |
| transitions into LOW caused by data removal | — | **0** | required 0 |

That is the property that matters: **recall holds while confidence falls and the queue grows.**
Removing evidence makes the system less certain and more cautious, never more dismissive.

**Deterministic vs +AI:** see §F — recall 1.000 → 1.000, leakage 0 → 0, queue 0.62 → 0.62,
measured lift 0, every per-case attention identical.

**The no-overfitting rule**, enforced throughout: weights, thresholds (65 / 0.6 / 30 / 40), detector
parameters, tier lists and golden expectations were **never** tuned to make a case pass. Every
failure was classified first as either **(a)** an implementation violation of intended policy → fix
the code, or **(b)** a wrong test/assumption → report it and leave the case failing until a human
approves the change. `EVAL_DECISIONS.md` records all of them, including the two plan amendments a
human approved (Amendments 1–4) and the one measuring-instrument bug I found and fixed in
`scripts/eval.py` (CP6-1) rather than in the product.

> **Golden-set performance measures consistency with our stated assumptions and safety policy under
> designed sparse/contradictory scenarios. It is not an estimate of real-world accuracy at
> identifying great founders. Real validation requires reviewer-labelled historical candidates
> and/or prospective reviewer feedback.**

---

## I. Limitations

This is its own slide. It does not go in the speaker notes.

1. **No real founder outcome labels exist.** Nothing here has been validated against founders who
   actually succeeded or failed.
2. **No claim of predictive founder-success accuracy.** Recall 1.000 means 15/15 designed scenarios
   obeyed the intended policy. It does not mean 100% of real great founders will be found.
3. **The LLM earned a display-only role, and nothing more.** Real-provider evaluation was run
   post-CP11 (35 calls, OpenAI, one model snapshot `gpt-5-mini-2025-08-07`). Automated attention
   escalation **failed its frozen gates** — 0 justified escalations, 1 false positive — so it is not
   recommended. No claim is made of improved recall, improved ranking or production readiness. The
   code still contains the bounded one-level raise that was tested; "not enabled" is a deployment
   posture, not a statement about the implementation.
3b. **The real-provider evidence is thin, synthetic and self-judged.** 30 golden profiles, one
   provider, one snapshot; **3/30 responses were malformed** (13–14 `source_fields` against a 12-item
   contract — failed closed, but an integration-contract reliability issue to fix before production);
   utility classifications are **provisional AI-assisted analysis, not independent human ground
   truth**; and useful contextual observations may be positive, negative or **ambiguous** —
   usefulness is not directionality. Reviewer capacity remains unknown.
3c. **Prompt-injection testing, stated precisely.** Real-provider injection resistance was exercised
   in the cp10.1 development experiment. It was **not** exercised in the cp10.2 holdout — the
   injection case was deliberately excluded from holdout membership — so that holdout counter is
   *not applicable*, not a pass.
4. **F-23 — semantic entailment limitation.** Provenance validation proves a cited source path
   exists and holds a value, and fails closed when a quoted literal is absent from the cited values.
   It cannot prove that an arbitrary unquoted paraphrase is entailed by them.
5. **F-22 — provider output is not bit-reproducible.** `temperature`, `top_p` and `top_k` are
   rejected by current Claude models, so there is no sampling knob to pin. The MockAdapter is the
   deterministic gate; real-provider results would be exploratory.
6. **Tier lists and scoring weights are assumptions requiring business calibration.** They are
   Redesign-plausible, not Redesign's real lists. Config, not code — editable in the UI.
7. **No enrichment.** No LinkedIn, Crunchbase or GitHub lookups; confidence is bounded by whatever
   the source record contains.
8. **`(-1→0)` only.** No idea/company `(0→1)` assessment.
9. **Local, single-tenant, no auth, no RBAC.** The "Acting as" field is the audited actor, on trust.
   SQLite is an MVP tradeoff, not a production concurrency architecture.
10. **Integrations and production ops are not built** — no email/calendar/Slack/CRM, no monitoring,
    no multi-user story. Full historical assessment-version browsing is V2, and AI-check results are
    ephemeral by design with no history table.
11. **The recall-first policy costs reviewer load, deliberately.** 787 of 800 seeded founders (98%)
    sit at REVIEW or above; the golden-set queue rate is 62% at baseline and 98.4% under ablation.
    That is the intended trade, and reviewer capacity is the open variable that should calibrate it.
12. **F-24 — one additive status field.** `GET /config` exposes a read-only `ai_layer` block
    (provider availability, prompt version/hash) so the UI can label the optional action honestly.
    It is status only: it does not enter the scoring rubric or the rubric hash.

---

## J. Roadmap

Priority order:

1. **Capture reviewer + business outcome labels.** Everything else is blocked on this.
2. **Separate founder-quality outcomes from process/timing outcomes.** "We didn't engage" is not
   "they weren't good" — conflating them teaches the wrong thing.
3. **Calibrate the rubric using real feedback** — thresholds and weights first, since they are the
   cheapest levers with the largest effect.
4. **AI layer, in four phases** (post-holdout, replacing "run real-provider ablations" — that is
   done):
   * **Phase 1 — now.** Deterministic prioritization + **display-only** AI contextual observations +
     human interpretation.
   * **Phase 2 — collect reviewer labels.** For each observation: useful · obvious/redundant ·
     incorrect · ambiguous · positive · negative · decision-changing.
   * **Phase 3 — evaluate authority.** Reviewer acceptance, incremental review value, false-positive
     escalation risk, and whether particular observation categories consistently predict useful
     reviews. Only then reconsider automatic escalation.
   * **Phase 4 — learned ranking**, and only once meaningful outcome labels exist. Do not jump from
     this holdout to ML ranking. The next step is **not** prompt tuning.
5. **Add data enrichment** (LinkedIn/Crunchbase/GitHub via the existing hashes) to raise confidence
   rather than to raise scores.
6. **Add `(0→1)` idea/company assessment** as a separate scorer sharing the pipeline.
7. **Introduce learned ranking only once labels justify it.**
8. **Add workflow integrations** — Slack digest for resurfacing, calendar, CRM export.
9. **Productionize** — Postgres, auth/roles, monitoring, data-quality monitors, drift controls.

The intended evolution:

```text
Cold start
Rules + constrained AI + humans
        ↓
Feedback
Reviewer labels + outcomes
        ↓
Calibration
Threshold/rubric/AI lift measurement
        ↓
Learned ranking
Only when labels justify it
        ↓
AI copilot
Research, contextual synthesis, memos
```

---

## K. "If you told me X, I'd change Y"

The point of this table is that the assumptions in §C are **testable and reversible**, not disguised
as facts.

| If I learned... | I would change... |
|---|---|
| Review capacity is only ~40 founders/week | Recalibrate attention thresholds and the queue policy rather than silently ranking people out — the queue would get an explicit capacity budget, not a quieter model |
| Education is weakly correlated with actual success | Reduce or remove education weighting (currently 10 of 100) |
| Healthcare experience is less important than assumed | Reweight the domain component (currently 20 of 100) and possibly split exposure from seniority |
| Referral source matters materially | Add source as an explicitly governed, visible signal — never as a hidden prior |
| Older experience should decay | Add recency weighting to tenure and progression |
| Real reviewer outcomes disagree with the rubric | Calibrate or rebuild the rubric using labels; the rubric is config and hashed, so the change is auditable |
| `(0→1)` is equally important | Build a separate idea/company scorer rather than polluting person scoring |
| Real-provider AI adds no measurable reviewer value | Remove or disable the LLM layer — it is optional by construction, so this costs nothing |
| The LLM increases queue size but not useful discoveries | Tighten the AI escalation policy (require STRONG cues only) or remove it |
| The LLM discovers valuable contextual evidence | Expand it carefully, retaining provenance validation, raise-only authority and the human decision boundary |

Two structural notes that make the above cheap rather than theoretical: weights, thresholds and tier
lists are **config, not code** (editable in the UI, hashed into `rubric_version`), and the AI layer
is **optional and non-persistent**, so removing it is a config change rather than a migration.

---

## L. Appendix — likely challenges

### "Why not use an LLM for the whole ranking?"

Auditability, calibration, labels, cost, drift, attribution, authority. There are no outcome labels
to calibrate a judgment model against, so its scores would be unfalsifiable. A rule gives a reviewer
a field list when they ask "why?"; a prompt gives them prose. A silent upstream model change would
silently re-rank the pipeline. If everything is one prompt, no one can attribute an improvement to
the prompt, the data, or the reviewers. And it is the wrong tool for tenure arithmetic and tier
lookups, which rules compute exactly and for free. Most importantly: I can't validate a judgment
model yet, and authority should track validation.

### "Why use an LLM at all?"

Because contextual, cross-field, *unusual* evidence is genuinely hard to encode exhaustively in
rules — the profile whose significance lives in the relationship between three fields rather than in
any one of them. That is a real gap in a rubric. But it remains a **hypothesis**, explicitly subject
to measured incremental lift, which is why the layer is isolated, optional and instrumented rather
than woven through the scoring.

### "Your deterministic recall is already 1.0. What does AI add?"

On the golden set, **no lift has been proven** — the baseline is saturated, so the measurement has no
headroom and cannot show lift even if lift exists. Since then I ran it for real (§F2): on 10 golden
cases that *did* have attention headroom, the LLM produced genuinely incremental contextual
observations on 4 — a same-employer Quality → Regulatory function switch, concurrent cross-industry
advisory roles, a senior-to-entry domain move — none of which the deterministic rubric models. But it
produced **0 justified escalations and 1 false positive**, so what it earned is the right to *show*
context, not to change priority. Proving more requires reviewer-labelled cases where the
deterministic baseline demonstrably misses. I'd rather report zero honestly than manufacture a lift
number.

### "Why is the LLM raise-only?"

Directly from the asymmetric business cost: a false negative (a missed exceptional founder) costs
more than an extra human review. A layer that can only add attention has a bounded worst case —
wasted reviewer time, which is visible and measurable. A layer that could lower attention has an
unbounded one — a silently dismissed founder, which is invisible. We have no calibration evidence
entitling the model to the second kind of authority. After the cp10.2 holdout the recommendation is
narrower still: the model has not earned the *raising* half either, so contextual findings should be
display-only until reviewer labels justify otherwise.

### "What does 100% recall mean?"

It means **15 of 15 designed must-surface scenarios obeyed the intended policy**. It is a statement
about our policy's internal consistency on scenarios we wrote ourselves. It does **not** mean 100%
of real great founders will be found, and I'd push back on anyone in the room who repeats it that
way.

### "Why rules instead of ML?"

No meaningful labelled outcome data exists yet. Rules are an auditable cold-start baseline that a
reviewer can argue with field by field, and they make the assumptions explicit enough to be
falsified. Capture labels first; learn later. Shipping an unvalidated model here would be
substituting sophistication for calibration.

### "How would this become production AI?"

Labels → calibration → authority evaluation → learned ranking where justified → feedback, monitoring
and drift controls. The order matters: every step after the first is meaningless without it. The
real-provider ablation is now done (§F2) and it moved the AI layer *down* to display-only rather than
up — which is the point of running it. Production hardening also has one concrete item from that run:
align the provider's structured-output guidance with the application's field-cardinality limits
(3/30 responses were rejected for citing 13–14 source paths against a 12-path contract; they failed
closed, but that rate is too high to ship).

### "How do you handle hallucinations?"

Five layers, plus an admission. Strict supplied-facts scope with identity minimization; mandatory
provenance paths; invalid citations **discarded, never repaired**; unsupported inferences retained as
diagnostics only, never as evidence; a hard authority ceiling with a human decision boundary (and
after the holdout, a recommendation not to use even the raising half — §F2). And the
admission: **F-23** — citation validity is not full semantic-entailment proof. The validator can
show a quoted literal is absent from the values cited, and fails closed on that; it cannot prove an
unquoted paraphrase is true. Everything it cannot prove is left visible to the human reading the
claim, which is the correct response to a validator with a known ceiling.

---

## M. Optional technical deep-dive — deterministic safety-harness demonstration

> **Not the recommended deployment posture.** This is the offline, key-free harness that proves the
> AI layer's containment properties. It uses the **MockAdapter** — a deterministic stub, not a model
> — and it predates the real-provider evaluation. Keep it out of the main demo flow: after the
> cp10.2 holdout showed escalation did not earn deployment authority, demonstrating a *mock* priority
> raise as though it were desired behaviour would misrepresent the conclusion. Show it only if asked
> how the safety machinery is tested.

`python scripts/ai_examples.py` shows both halves of the harness:

* **Example A — the escalation path, exercised.** A cue whose every cited path exists, raising
  REVIEW → PRIORITY_REVIEW. What this demonstrates is that the ratchet is *wired and testable*, not
  that raising is recommended. Under the current posture this capability stays unused.
* **Example B — the discard path, still the more useful half.** A claimed exit citing
  `experience[0].exit_details`, a field that does not exist on that founder: **discarded, not
  repaired**, with its two unsupported inferences kept visible as diagnostics only. This is the
  property that matters most and it is unaffected by the deployment recommendation — an ungrounded
  citation never becomes evidence, and the system never guesses which path the model "meant".

The MockAdapter is also the deterministic gate for the whole evaluation: fixed model id, fixed
timestamp, no sampling, finds nothing by default, and everything it produces is labelled
`provider: mock` all the way to the UI badge — canned output is never presented as a model result.

The real-provider evidence, and the posture that follows from it, is in **§F2** and
[`EVAL_REPORT_REAL_PROVIDER.md`](EVAL_REPORT_REAL_PROVIDER.md).

