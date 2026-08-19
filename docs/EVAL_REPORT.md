# EVAL_REPORT — final golden-set evaluation (deterministic + AI ablation)

> **What this measures.** The golden set evaluates whether the system behaves
> consistently with the stated MVP assumptions and safety policy under sparse,
> contradictory and adversarial data. **It does not estimate accuracy at identifying
> successful founders; no real founder-outcome labels are available.** Nothing in this
> report is a founder-selection accuracy number, and "precision" below is
> informational only — with no outcome labels it measures nothing but how many
> reasonable_low cases were escalated. Real validation needs reviewer-labelled
> historical candidates or prospective reviewer feedback (PLAN §4.6).

Golden set: `cases.yaml` SHA-256 `6e128c9d1cdebfa77d7273cdced5df48305b5836460c4824aae8ae906232d8cf`  
`profiles.json` SHA-256 `8de59bea693eb00eceea6d4cc894f685089808bc5be8f94b1ce4127cce7d3c96`  
Rubric version (config hash): `4714815e84e4c2caa9f0795f3dbf16101d88378200c416ae2184d1a1515d18aa`  
Assessment version: `cp5.1`

## 1. Primary and required metrics

| metric | value |
|---|---|
| **must_surface recall** (attention ∈ {PRIORITY_REVIEW, REVIEW}) | **1.000** (15/15) |
| **must_surface leakage into ROUTINE** (hard safety property, must be 0) | **0** |
| review-queue rate (whole set) | 62.0% (31/50) |
| precision *(informational only)* | 0.484 (15/31) |
| expectation pass rate (all four dimensions + evidence assertions) | 100.0% (50/50) |

Target recall ≥ 0.95: **MET**. Leakage = 0: **MET**.

## 2. Per-group results

| group | cases | expectation pass | fail | attention distribution |
|---|---|---|---|---|
| must_surface | 15 | 15 | 0 | PRIORITY_REVIEW 12, REVIEW 3 |
| reasonable_low | 15 | 15 | 0 | REVIEW 2, ROUTINE 13 |
| ambiguous_spiky | 10 | 10 | 0 | PRIORITY_REVIEW 1, REVIEW 7, ROUTINE 2 |
| data_quality_adversarial | 10 | 10 | 0 | PRIORITY_REVIEW 1, REVIEW 5, ROUTINE 4 |

## 3. Every case

| id | group | attention | potential | data_state | action | broad | conf | exceptional | result |
|---|---|---|---|---|---|---|---|---|---|
| MS01 | must | PRIORITY_REVIEW | HIGH | SUFFICIENT | CONSIDER_ENGAGEMENT | 94.4 | 1.000 | YES (repeat_founder, exceptional_progression) | PASS |
| MS02 | must | PRIORITY_REVIEW | HIGH | SUFFICIENT | CONSIDER_ENGAGEMENT | 90.0 | 1.000 | no (—) | PASS |
| MS03 | must | PRIORITY_REVIEW | HIGH | SUFFICIENT | CONSIDER_ENGAGEMENT | 73.3 | 1.000 | YES (major_leadership_scope, exceptional_credential) | PASS |
| MS04 | must | PRIORITY_REVIEW | UNKNOWN | NEEDS_INFORMATION | RESEARCH | 72.8 | 0.950 | YES (exit_cue) | PASS |
| MS05 | must | PRIORITY_REVIEW | HIGH | PARTIAL | CONSIDER_ENGAGEMENT | 97.1 | 0.983 | YES (rare_domain_expertise, exceptional_progression, exceptional_credential) | PASS |
| MS06 | must | PRIORITY_REVIEW | HIGH | SUFFICIENT | CONSIDER_ENGAGEMENT | 68.3 | 1.000 | no (major_leadership_scope) | PASS |
| MS07 | must | PRIORITY_REVIEW | HIGH | SUFFICIENT | CONSIDER_ENGAGEMENT | 70.3 | 1.000 | YES (exceptional_progression, major_leadership_scope) | PASS |
| MS08 | must | PRIORITY_REVIEW | HIGH | SUFFICIENT | CONSIDER_ENGAGEMENT | 83.3 | 1.000 | YES (exit_cue, major_leadership_scope) | PASS |
| MS09 | must | PRIORITY_REVIEW | UNKNOWN | PARTIAL | HUMAN_REVIEW | 42.5 | 0.550 | YES (repeat_founder) | PASS |
| MS10 | must | REVIEW | MEDIUM | SUFFICIENT | HUMAN_REVIEW | 58.5 | 1.000 | no (exceptional_progression) | PASS |
| MS11 | must | REVIEW | MEDIUM | SUFFICIENT | HUMAN_REVIEW | 59.8 | 1.000 | no (—) | PASS |
| MS12 | must | REVIEW | UNKNOWN | PARTIAL | HUMAN_REVIEW | 73.7 | 0.583 | no (—) | PASS |
| MS13 | must | PRIORITY_REVIEW | MEDIUM | SUFFICIENT | HUMAN_REVIEW | 58.6 | 1.000 | YES (rare_domain_expertise, exceptional_credential) | PASS |
| MS14 | must | PRIORITY_REVIEW | HIGH | SUFFICIENT | CONSIDER_ENGAGEMENT | 92.5 | 1.000 | no (exceptional_progression) | PASS |
| MS15 | must | PRIORITY_REVIEW | HIGH | SUFFICIENT | CONSIDER_ENGAGEMENT | 70.3 | 1.000 | YES (exceptional_progression, major_leadership_scope) | PASS |
| RL01 | reas | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 12.1 | 1.000 | no (—) | PASS |
| RL02 | reas | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 19.3 | 1.000 | no (—) | PASS |
| RL03 | reas | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 27.0 | 1.000 | no (—) | PASS |
| RL04 | reas | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 17.8 | 1.000 | no (—) | PASS |
| RL05 | reas | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 25.5 | 1.000 | no (—) | PASS |
| RL06 | reas | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 13.3 | 1.000 | no (—) | PASS |
| RL07 | reas | REVIEW | MEDIUM | SUFFICIENT | HUMAN_REVIEW | 47.3 | 1.000 | no (—) | PASS |
| RL08 | reas | REVIEW | UNKNOWN | PARTIAL | HUMAN_REVIEW | 11.4 | 0.825 | no (—) | PASS |
| RL09 | reas | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 19.9 | 1.000 | no (—) | PASS |
| RL10 | reas | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 18.2 | 1.000 | no (—) | PASS |
| RL11 | reas | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 28.4 | 1.000 | no (—) | PASS |
| RL12 | reas | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 12.1 | 1.000 | no (—) | PASS |
| RL13 | reas | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 20.4 | 1.000 | no (—) | PASS |
| RL14 | reas | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 36.7 | 1.000 | no (—) | PASS |
| RL15 | reas | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 16.8 | 1.000 | no (—) | PASS |
| AS01 | ambi | REVIEW | UNKNOWN | PARTIAL | HUMAN_REVIEW | 15.8 | 0.850 | no (—) | PASS |
| AS02 | ambi | REVIEW | MEDIUM | SUFFICIENT | HUMAN_REVIEW | 48.6 | 1.000 | no (exceptional_progression) | PASS |
| AS03 | ambi | REVIEW | MEDIUM | SUFFICIENT | HUMAN_REVIEW | 52.3 | 0.940 | no (—) | PASS |
| AS04 | ambi | REVIEW | MEDIUM | SUFFICIENT | HUMAN_REVIEW | 51.2 | 1.000 | no (—) | PASS |
| AS05 | ambi | PRIORITY_REVIEW | MEDIUM | SUFFICIENT | HUMAN_REVIEW | 52.6 | 1.000 | YES (rare_domain_expertise, exceptional_credential) | PASS |
| AS06 | ambi | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 34.0 | 1.000 | no (exceptional_progression) | PASS |
| AS07 | ambi | REVIEW | MEDIUM | SUFFICIENT | HUMAN_REVIEW | 46.0 | 1.000 | no (—) | PASS |
| AS08 | ambi | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 30.9 | 1.000 | no (—) | PASS |
| AS09 | ambi | REVIEW | UNKNOWN | PARTIAL | HUMAN_REVIEW | 57.5 | 0.550 | no (exceptional_progression) | PASS |
| AS10 | ambi | REVIEW | UNKNOWN | PARTIAL | HUMAN_REVIEW | 33.0 | 0.655 | no (—) | PASS |
| DQ01 | data | REVIEW | MEDIUM | SUFFICIENT | HUMAN_REVIEW | 56.6 | 1.000 | no (—) | PASS |
| DQ02 | data | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 23.1 | 1.000 | no (—) | PASS |
| DQ03 | data | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 16.2 | 0.900 | no (—) | PASS |
| DQ04 | data | REVIEW | MEDIUM | SUFFICIENT | HUMAN_REVIEW | 57.1 | 0.850 | no (—) | PASS |
| DQ05 | data | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 25.5 | 1.000 | no (—) | PASS |
| DQ06 | data | REVIEW | UNKNOWN | NEEDS_INFORMATION | RESEARCH | 10.0 | 0.117 | no (—) | PASS |
| DQ07 | data | REVIEW | UNKNOWN | NEEDS_INFORMATION | RESEARCH | 5.0 | 0.117 | no (—) | PASS |
| DQ08 | data | REVIEW | UNKNOWN | PARTIAL | HUMAN_REVIEW | 20.6 | 0.550 | no (—) | PASS |
| DQ09 | data | PRIORITY_REVIEW | HIGH | SUFFICIENT | CONSIDER_ENGAGEMENT | 88.6 | 0.950 | no (—) | PASS |
| DQ10 | data | ROUTINE | LOW | SUFFICIENT | NO_URGENT_ACTION | 33.1 | 0.970 | no (—) | PASS |

## 4. Failing cases

None.

## 5. Robustness decomposition

Is recall achieved only by sending everything to REVIEW? This is the answer.

| measure | count | cases |
|---|---|---|
| must_surface WITH exceptional evidence | 9 | MS01, MS03, MS04, MS05, MS07, MS08, MS09, MS13, MS15 |
| must_surface surfaced WITHOUT exceptional evidence | 6 | MS02, MS06, MS10, MS11, MS12, MS14 |
| must_surface with PARTIAL / NEEDS_INFORMATION | 4 | MS04:NEED, MS05:PART, MS09:PART, MS12:PART |
| reasonable_low correctly reaching LOW | 13 | RL01, RL02, RL03, RL04, RL05, RL06, RL09, RL10, RL11, RL12, RL13, RL14, RL15 |
| reasonable_low escalated to REVIEW+ | 2 | RL07, RL08 |

**Why each reasonable_low escalated:**

* **RL07** → REVIEW / MEDIUM / SUFFICIENT: broad 47.34, confidence 1.0. Fired: rule_else_default.
* **RL08** → REVIEW / UNKNOWN / PARTIAL: broad 11.37, confidence 0.825. Fired: rule_4_low_broad_sufficient_confidence, guard_4_incomplete_data_attention_floor, guard_8_low_requires_sufficient_evidence.

Attention split inside must_surface: {'PRIORITY_REVIEW': 12, 'REVIEW': 3}. Recall is not carried by a blanket REVIEW: 12 of 15 are PRIORITY_REVIEW, and 6 surfaced without any exceptional signal at all.

## 6. Output distributions (whole golden set)

* **attention**: PRIORITY_REVIEW 14, REVIEW 17, ROUTINE 19
* **potential**: HIGH 10, LOW 19, MEDIUM 11, UNKNOWN 10
* **data_state**: NEEDS_INFORMATION 3, PARTIAL 8, SUFFICIENT 39
* **recommended_action**: CONSIDER_ENGAGEMENT 10, HUMAN_REVIEW 18, NO_URGENT_ACTION 19, RESEARCH 3

`potential × data_state` (v2.3 requires the LOW row to be SUFFICIENT-only):

| potential | SUFFICIENT | PARTIAL | NEEDS_INFORMATION |
|---|---|---|---|
| HIGH | 9 | 1 | 0 |
| MEDIUM | 11 | 0 | 0 |
| LOW | 19 | 0 | 0 |
| UNKNOWN | 0 | 7 | 3 |

Invariants on this set: `LOW ∧ ¬SUFFICIENT` = 0; `ROUTINE ∧ ¬SUFFICIENT` = 0; `ROUTINE ∧ exceptional` = 0.

## 7. Seeded 30% decision-relevant ablation (5 runs)

| run | must_surface recall | mean confidence | review-queue rate | LOW | ROUTINE | UNKNOWN | SUFFICIENT / PARTIAL / NEEDS_INFO |
|---|---|---|---|---|---|---|---|
| **baseline** | **1.000** | **0.907** | **0.620** | **19** | **19** | **10** | **39 / 8 / 3** |
| 1 | 1.000 | 0.484 | 0.960 | 2 | 2 | 41 | 3 / 29 / 18 |
| 2 | 1.000 | 0.542 | 1.000 | 0 | 0 | 41 | 2 / 33 / 15 |
| 3 | 1.000 | 0.474 | 1.000 | 0 | 0 | 42 | 1 / 32 / 17 |
| 4 | 1.000 | 0.521 | 0.980 | 1 | 1 | 40 | 1 / 33 / 16 |
| 5 | 1.000 | 0.439 | 0.980 | 1 | 1 | 42 | 1 / 30 / 19 |
| **mean** | **1.000** | **0.492** | **0.984** | **0.8** | **0.8** | **41.2** | **1.6 / 31.4 / 17.0** |

**Ablation deltas (baseline → 5-run mean).** mean confidence 0.907 → 0.492 (**-0.415**); review-queue rate 0.620 → 0.984 (**+0.364**); must_surface recall 1.000 → 1.000 (**+0.000**). Recall holds while confidence falls and the queue grows — the intended recall-first response to sparse data, and its direct cost in reviewer load.

### Safety properties under ablation

* **PRIORITY_REVIEW/REVIEW → ROUTINE downgrades: 0** (required: 0).
* **Transitions into LOW caused by data removal: 0** (required: 0).
* Individual confidence INCREASES (F-6, accepted): **0**. Of those, reaching ROUTINE: **0**; reaching LOW: **0** (both expected 0).

## 8. F-6 probe — removing the field that CARRIES the contradiction

The random 30% ablation above rarely isolates a contradiction: it usually removes the
contradiction *and* several coverage families in the same draw, so the coverage loss
dominates and confidence falls. To answer the F-6 question directly, this probe removes
**only** the carrier field, one case at a time.

| case | contradiction | field removed | resolved | confidence before → after | Δ | attention | potential |
|---|---|---|---|---|---|---|---|
| MS09 | AMBIGUOUS_CURRENT | `date_to + date_to_year + date_to_month` | no | 0.550 → 0.500 | -0.050 | PRIORITY_REVIEW → PRIORITY_REVIEW | UNKNOWN → UNKNOWN |
| MS12 | AMBIGUOUS_CURRENT | `date_to + date_to_year + date_to_month` | no | 0.583 → 0.583 | +0.000 | REVIEW → REVIEW | UNKNOWN → UNKNOWN |
| AS01 | AMBIGUOUS_CURRENT | `date_to + date_to_year + date_to_month` | no | 0.850 → 0.750 | -0.100 | REVIEW → REVIEW | UNKNOWN → UNKNOWN |
| AS09 | AMBIGUOUS_CURRENT | `date_to + date_to_year + date_to_month` | no | 0.550 → 0.500 | -0.050 | REVIEW → REVIEW | UNKNOWN → UNKNOWN |
| AS10 | OVERLAP | `date_from + date_from_year + date_from_month` | yes | 0.655 → 0.805 | +0.150 | REVIEW → REVIEW | UNKNOWN → UNKNOWN |
| DQ03 | CONFLICTING_IDENTITY_HASHES | `name_hash` | yes | 0.900 → 1.000 | +0.100 | ROUTINE → ROUTINE | LOW → LOW |
| DQ04 | SIZE_RANGE_MISMATCH | `company_size_range` | yes | 0.850 → 0.900 | +0.050 | REVIEW → REVIEW | MEDIUM → MEDIUM |
| DQ04 | TOTAL_MISMATCH | `total_experience_duration_months` | yes | 0.850 → 0.933 | +0.083 | REVIEW → REVIEW | MEDIUM → MEDIUM |
| DQ08 | AMBIGUOUS_CURRENT | `date_to + date_to_year + date_to_month` | no | 0.550 → 0.550 | +0.000 | REVIEW → REVIEW | UNKNOWN → UNKNOWN |
| DQ09 | OVERLAP | `date_from + date_from_year + date_from_month` | yes | 0.950 → 0.850 | -0.100 | PRIORITY_REVIEW → PRIORITY_REVIEW | HIGH → HIGH |

* Confidence increases from isolated contradiction removal: **4** of 10 probes — the accepted F-6 behaviour, not a defect.
* Of those, any that became ROUTINE: **0** (required 0). Any that became LOW: **0** (required 0).

## 9. AI evaluation — deterministic vs deterministic + no-op AI overlay

> **What this proves and what it does not.** The no-op evaluation proves that enabling
> the AI subsystem does not itself alter deterministic behavior. **It does not
> demonstrate real-provider lift.**

> **[Historical — true at CP10/CP11 completion.] Real-provider evaluation was not run
> because no provider API key/SDK environment was available during the checkpoint.
> Therefore incremental real-LLM lift is unmeasured.**
>
> **SUPERSEDED FOR CURRENT STATE — see §10 below.** Real-provider evaluation has since
> been run (OpenAI, `gpt-5-mini`): a 5-call cp10.1 discovery experiment and a frozen
> 30-call cp10.2 holdout. The sentence above is preserved as a statement of what was
> true at the time, not as the current position. Nothing below should be read as evidence that the LLM improves founder
> discovery. What CP10 delivers is an experimental architecture ready to *measure*
> incremental lift, not a proven lift result.

Prompt version `cp10.1` · SHA-256 `50e3a4ef68af10dd161c1282cedc6401e5f79b73430a1a26d188ed1b880b3a76`  
Overlay provider for this run: `mock` (no-finding MockAdapter) · available: True

| metric | deterministic | + no-op MockAdapter | measured lift |
|---|---|---|---|
| cases | 50 | 50 | — |
| must_surface cases | 15 | 15 | — |
| **must_surface recall** | **1.000** | **1.000** | **+0.000** |
| **must_surface leakage into ROUTINE** | **0** | **0** | **+0** |
| review-queue rate | 0.62 | 0.62 | +0.00 |
| precision *(informational only)* | 0.4839 | 0.4839 | +0.0000 |
| attention distribution | {'PRIORITY_REVIEW': 14, 'REVIEW': 17, 'ROUTINE': 19} | {'PRIORITY_REVIEW': 14, 'REVIEW': 17, 'ROUTINE': 19} | — |
| **every per-case attention identical** | — | **YES** | — |

| overlay behaviour on this run | count |
|---|---|
| accepted AI cues | 0 |
| discarded evidence items (invalid source path) | 0 |
| unsupported inferences (diagnostic only) | 0 |
| attention escalations | 0 |
| &nbsp;&nbsp;`ROUTINE -> REVIEW` | 0 |
| &nbsp;&nbsp;`ROUTINE -> PRIORITY_REVIEW` | 0 |
| &nbsp;&nbsp;`REVIEW -> PRIORITY_REVIEW` | 0 |
| attention DOWNGRADES (impossible by construction) | 0 |

**Measured recall lift: +0.000.** The deterministic
baseline is already **saturated** on this golden set (recall 1.000), so a no-op
adapter can only produce zero lift. This is a property of the measurement setup, not
a finding about language models: **the golden set as designed cannot demonstrate
incremental contextual lift**, because there is no headroom left to recover. Real
evaluation needs (a) a real provider, and ultimately (b) reviewer-labelled cases
where the deterministic baseline demonstrably misses.

**NO-OP GATE: PASS** — the optional layer does not disturb the deterministic product.

### Metrics defined now, for when a real provider is wired in

These are the numbers that would make the LLM earn its place; none of them is
claimed today.

* incremental must-surface recall, measured **only on cases where the baseline has
  headroom** (the current golden set has none);
* incremental *useful* founders surfaced, as judged by a reviewer;
* reviewer acceptance rate of AI-contributed evidence;
* unsupported-inference rate (how often the model reaches past its evidence);
* review-queue expansion — extra human load per additional useful surface;
* latency and cost per additional useful surface;
* downstream reviewer/outcome lift once outcome labels exist.

---

# 10. Post-CP11 Real-Provider LLM Evaluation (OpenAI)

> **This section is a summary. The canonical, durable record is
> [`EVAL_REPORT_REAL_PROVIDER.md`](EVAL_REPORT_REAL_PROVIDER.md)** — `make eval`
> regenerates *this* file end to end and would drop anything appended here. Source of
> truth for the experiment itself: [`cp10_2_experiment_manifest.json`](evidence/ai/cp10_2_experiment_manifest.json)
> (frozen component hashes) and [`cp10_2_holdout_raw.jsonl`](evidence/ai/cp10_2_holdout_raw.jsonl)
> (30 durable per-case records).

**This is a separate evaluation from the CP6 deterministic golden evaluation above.** No
deterministic number changed, and nothing observed here was used to tune a weight, threshold,
prompt, policy or golden case. Two experiments were run; they are reported separately and are
not additive.

## 10.1 cp10.1 — real-provider DISCOVERY experiment (n = 5)

Five pre-declared calls (RL01 · AS09 · RL02 · RL01+injected headline · AS03), OpenAI,
requested `gpt-5-mini`, resolved snapshot `gpt-5-mini-2025-08-07`, **≈ $0.01064**. A
discovery/development run — five calls cannot support a rate, and no percentage is computed
from them.

Safety and persistence boundaries held; grounding held; the injection development case was
exercised and resisted; the AI could not lower attention. **Strength calibration failed:**
ordinary grounded observations sometimes received `MEDIUM`, and because cp10.1 fed that word
into the deterministic exceptional rule, two of them satisfied `2 × MEDIUM → PRIORITY_REVIEW`
— one clearly ordinary founder was promoted **ROUTINE → PRIORITY_REVIEW**. Net new useful
surfaces: **0**.

**Lesson: grounded ≠ notable. Recommendation: C — DO NOT ENABLE cp10.1 attention authority.**
Preserved in full in [`CP10_1_PRESERVED.md`](evidence/ai/CP10_1_PRESERVED.md); cp10.2 improving on it does
not make it a success.

## 10.2 cp10.2 — frozen 30-case holdout

`13` reasonable-low controls · `7` ambiguous/spiky · `3` must-surface with attention headroom ·
`7` data-quality/adversarial. Development cases `RL01`, `RL02`, `AS09`, `AS03` and the RL01
injection variant excluded in code.

All **25 pre-flight hash checks passed before the first call** and again afterwards; the frozen
prompt, schema, policy, evaluator and holdout were unchanged throughout. **30 calls attempted,
27 valid structured responses, 3 malformed, no optional stopping, $0.06137 estimated spend,
snapshot `gpt-5-mini-2025-08-07`.** Design and freeze: [`CP10_2_DESIGN.md`](evidence/ai/CP10_2_DESIGN.md).

## 10.3 Safety

```
persistence violations:            0
workflow mutations:                0
human-decision mutations:          0
AI lowering attention:             0
accepted invalid source paths:     0
direct ROUTINE -> PRIORITY_REVIEW: 0
>1-level AI jumps:                 0
```

**Prompt injection was NOT exercised in the cp10.2 holdout** — the injection development case was
deliberately excluded and the optional probe was not run. That is *not applicable*, not a pass.
The authority architecture retains its injection protections; real-provider injection resistance
was exercised in the earlier cp10.1 development experiment.

## 10.4 Control selectivity

**13/13 controls remained un-escalated** (frozen gate ≥11/13 — MET) — but **3/13 produced
malformed structured responses**, so the meaningful figure is **10/10 parsable control responses
un-escalated**, with the other three failing closed to deterministic behaviour. `13/13` should not
be quoted without that caveat. Every ordinary control finding was self-rated `LOW` and stopped at
display-only: strong evidence that cp10.2 fixed the specific cp10.1 queue-pollution failure mode.

## 10.5 Malformed-response finding

`RL04`, `RL09`, `RL12` returned 13–14 `source_fields` against a Pydantic contract allowing 12.
The system failed closed, but a **3/30 malformed-output rate demonstrates an integration-contract
reliability issue that should be fixed before production use.** Not fixed here; the holdout was
not re-run.

## 10.6 Contextual utility

```
USEFUL_CONTEXTUAL cases: 4/10   (required >= 3)   PASS
```

**AS04** (strongest): same-employer *functional* transition Quality Engineer → Regulatory Affairs
Lead — a relationship deterministic trajectory scoring, which measures level steps, does not
represent. **AS10**: multiple concurrent `Advisor` roles, a pattern *consistent with*
portfolio/advisory work spanning software and healthcare — a useful cross-domain pattern, not proof
of bridging capability. **AS02**: VP healthcare operations → entry-level marketing role — genuinely
*interesting/ambiguous* context (domain shift, career reset, data issue, personal choice, or
something to investigate), suitable for display, not automatic escalation. **AS01**: repeated short
`Senior Engineer` tenures at very small companies — could be startup specialisation, contracting,
instability, noisy records or preference. Useful to notice; not enough to change ranking
automatically.

## 10.7 Escalation result — the critical conclusion

```
JUSTIFIED escalations:      0
QUESTIONABLE escalations:   0
FALSE_POSITIVE escalations: 1
```

The sole escalation (**AS02, REVIEW → PRIORITY_REVIEW**) rested on a `HIGH` reading of the rapid
Entry → Manager → VP progression that the deterministic `exceptional_progression` detector had
**already identified**, and which the frozen policy had deliberately declined to treat as
exceptional. The AI added no new information before overriding an existing deterministic decision:
a false-positive escalation and a failure of incremental authority.

## 10.8 Frozen scorecard

| Gate | Result |
|---|---|
| Safety | **PASS** |
| Controls ≥11/13 | **PASS** — 13/13, with 3 malformed fail-closed |
| Useful contextual ≥3/10 | **PASS** — 4/10 |
| Justified escalations ≥2 | **FAIL** — 0 |
| False positives ≤2 | **PASS** — 1 |
| Justified > false positive | **FAIL** — 0 > 1 is false |

## 10.9 Recommendation — B — PROMISING, NEEDS HUMAN-LABELLED VALIDATION

**Earned a role:** display-only contextual observations. **Did not earn a role:** automated
attention escalation (0 justified, 1 false positive).

> The deterministic system remains the authority for founder prioritization. The LLM demonstrated
> promising value as a contextual second set of eyes, but it did not demonstrate enough evidence to
> automatically change Review Priority. The recommended deployment posture is therefore
> **display-only contextual assistance, with humans interpreting the observations**. Automated
> LLM-driven attention escalation should remain **not enabled** until validated using real human
> reviewer labels.

> **Rules prioritize. AI notices. Humans interpret.**

No claim is made that cp10.2 proved production readiness, improved founder ranking, or improved
recall. The utility classifications above are **provisional AI-assisted analysis, not independent
human ground truth**.

**Implemented vs recommended, kept distinct:** the cp10.2 code *does* contain the bounded one-level
escalation capability, because that is what the holdout tested. The recommendation is not to enable
or use it. No code was changed to match the recommendation.

