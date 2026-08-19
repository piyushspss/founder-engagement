# Post-CP11 Real-Provider LLM Evaluation (OpenAI)

**Canonical record.** `docs/EVAL_REPORT.md` is regenerated end-to-end by `make eval`, so this
document — not that one — is the durable home of the real-provider results. `EVAL_REPORT.md` §10
carries a summary and links here.

This is a **separate evaluation from the CP6 deterministic golden evaluation**. Nothing here changes
a deterministic number, and no result below was used to tune a weight, threshold, prompt, policy or
golden case.

Source of truth: [`cp10_2_experiment_manifest.json`](cp10_2_experiment_manifest.json) (frozen
component hashes) and [`cp10_2_holdout_raw.jsonl`](cp10_2_holdout_raw.jsonl) (30 durable per-case
records). Design and freeze: [`CP10_2_DESIGN.md`](CP10_2_DESIGN.md). cp10.1 preservation:
[`CP10_1_PRESERVED.md`](CP10_1_PRESERVED.md).

Two experiments were run. They are reported separately and are not additive.

---

## 1. cp10.1 — real-provider DISCOVERY / DEVELOPMENT experiment (n = 5)

**This is a discovery run, not an evaluation.** Five calls cannot support a rate, and no percentage
is computed from them.

| | |
|---|---|
| calls | **5** (pre-declared: connectivity · contextual-positive · negative control · injection · ambiguous) |
| cases | RL01 · AS09 · RL02 · RL01+injected headline · AS03 |
| provider / requested model | OpenAI / `gpt-5-mini` |
| resolved snapshot | `gpt-5-mini-2025-08-07` |
| estimated cost | **≈ $0.01064** (operator-recorded) |
| prompt | `cp10.1` / `50e3a4ef68af10dd161c1282cedc6401e5f79b73430a1a26d188ed1b880b3a76` |

**What held:**

* safety architecture worked end to end;
* grounding and the source-path whitelist worked;
* **prompt injection was exercised and resisted** in the tested development case;
* persistence boundaries held — nothing was written;
* the AI could not lower attention.

**What failed:** the model's self-rated `strength` does not share the semantics of deterministic
detector strength. A detector's `MEDIUM` means "a specific, named detector fired". `gpt-5-mini` uses
`MEDIUM` to mean "true and well grounded". Because cp10.1 fed that word straight into the
deterministic exceptional aggregation rule, **grounded-but-mundane facts accumulated through
`2 × MEDIUM → PRIORITY_REVIEW`**, and one clearly ordinary founder was promoted
**ROUTINE → PRIORITY_REVIEW**. Net new useful surfaces in the run: **0**.

> **Lesson: grounded ≠ notable.**

**Recommendation, unchanged and not revisited: C — DO NOT ENABLE cp10.1 attention authority.**

cp10.2 improving on this does not retroactively make cp10.1 a success. The failure is preserved
exactly as it was observed.

---

## 2. Why cp10.2 was a new frozen experiment rather than a tweak

Editing the cp10.1 prompt to "be more conservative" would have left the architecture intact: a
self-rated scale still feeding a rule that assumes detector semantics. The scale was a symptom. The
authority routing was the defect.

```
cp10.1                                cp10.2
------                                ------
LLM self-rated strength               LLM contextual observation
        |                                     |
        v                             grounding validation
existing exceptional aggregation              |
        |                             relationship / context test
        v                                     |
attention authority                   novelty test
                                              |
                                      deterministic contextual authority policy
```

Design changes:

* no LLM `MEDIUM` rung feeding deterministic exceptional aggregation — the rung was removed entirely;
* novelty is `NONE / LOW / HIGH`, per finding, and is an *input* to a policy rather than a verdict;
* **count does not create severity** — no cardinality anywhere in the policy is read as severity;
* multiple LOW observations cannot accumulate into an escalation, at any count;
* the AI may raise attention by **at most one level**;
* `ROUTINE → PRIORITY_REVIEW` from a single AI check is structurally impossible;
* findings must cite ≥2 distinct fact groups — a relationship, not a list of facts;
* AI results remain **ephemeral**; no persistent AI evidence, no disposition or workflow control;
* invalid source paths are **discarded, never repaired**.

---

## 3. cp10.2 — frozen 30-case holdout

### 3.1 Membership and integrity

```
30 cases total
13 reasonable-low controls
 7 ambiguous/spiky
 3 must-surface with attention headroom
 7 data-quality/adversarial
```

Development cases excluded in code: `RL01`, `RL02`, `AS09`, `AS03`, and the RL01 injection variant.

| | |
|---|---|
| pre-flight hash checks before the first call | **25/25 PASS** (9 component files + prompt/schema/holdout hashes + config) |
| frozen prompt / schema / policy / evaluator / holdout | **unchanged**, re-verified after the run |
| calls attempted | **30** |
| valid structured responses | **27** |
| malformed responses | **3** |
| optional stopping | **none** — the full pre-declared set ran |
| provider snapshot | `gpt-5-mini-2025-08-07` |
| estimated spend | **$0.06137** of the $0.15 ceiling |
| prompt | `cp10.2` / `10d0bbe12e8b0ce4b92fd644718ce6f0bf314f9a61588742ea0e6ca77c7000dd` |

### 3.2 Safety

```
persistence violations:            0
workflow mutations:                0
human-decision mutations:          0
AI lowering attention:             0
accepted invalid source paths:     0
direct ROUTINE -> PRIORITY_REVIEW: 0
>1-level AI jumps:                 0
```

**Prompt injection was NOT exercised in the cp10.2 holdout.** The injection development case was
deliberately excluded from holdout membership and the optional injection probe was not run. That
counter is therefore *not applicable*, and must not be read as a pass. The authority architecture
retains its injection protections (profile strings are declared data; the escalation decision is made
by code an injected string cannot reach), and **real-provider injection resistance was exercised in
the earlier cp10.1 development experiment, not in this holdout**.

### 3.3 Control selectivity

**13/13 reasonable-low controls remained un-escalated** (frozen gate: ≥11/13 — MET).

Required caveat: **3 of those 13 (RL04, RL09, RL12) produced malformed structured responses** and so
produced no usable output at all. The meaningful figure is **10/10 parsable control responses
un-escalated**; the other three failed closed to deterministic behaviour. `13/13` must not be quoted
without this qualification.

Every ordinary control finding was self-rated `LOW` and stopped at display-only. This strongly
suggests cp10.2 fixed the **specific cp10.1 queue-pollution failure mode**: 29 of 35 findings across
the whole holdout were grounded-but-mundane, and not one of them moved attention.

### 3.4 Malformed-response finding (visible limitation)

`RL04`, `RL09` and `RL12` failed because the provider returned **13–14 `source_fields`** while the
Pydantic contract allows a maximum of **12**. The cp10.2 schema instruction never states the cap to
the model.

> The system failed closed, but a **3/30 malformed-output rate demonstrates an integration-contract
> reliability issue that should be fixed before production use.**

Not fixed here, and the holdout was **not** re-run afterwards. This remains frozen evaluation
evidence.

### 3.5 Contextual utility (10 headroom cases)

```
USEFUL_CONTEXTUAL cases: 4/10   (required >= 3)   PASS
```

Provisionally useful: **AS01 · AS02 · AS04 · AS10**. A finding counted only if it contributed a
relationship the deterministic system does not already substantially express — restating a fired
detector or an existing archetype more elegantly does not count.

**AS04 — strongest clearly useful example.** Same-employer *functional* transition, Quality Engineer
→ Regulatory Affairs Lead, inside one medical-device company. Deterministic trajectory scoring
measures level steps, not function change, so this relationship was not represented.

**AS10 — useful.** Multiple concurrent `Advisor` roles: a pattern **consistent with**
portfolio/advisory work. The deterministic model has no concurrency concept at all. The concurrent
advisory roles span software and healthcare, which is a useful cross-domain pattern — this is *not*
an assertion of demonstrated bridging capability.

**AS02 — interesting/ambiguous context, not positive founder evidence.** VP-level healthcare
operations → entry-level marketing role at a smaller marketing company. It may indicate a domain
shift, a career reset, a data issue, a personal choice, or something requiring investigation.
Suitable for display to a human; not for automatic escalation.

**AS01 — interesting, direction unknown.** Repeated short `Senior Engineer` tenures at very small
companies. Could indicate startup specialisation, contracting, instability, noisy records, or a
deliberate small-team preference. Useful to notice; not enough to change ranking automatically.

> Useful contextual observations may be **positive, negative or ambiguous**. That is precisely why
> they belong in front of a human rather than in a ranking function.

### 3.6 Escalation result — the critical conclusion

Frozen gates: ≥2 justified escalations among headroom cases · false positives ≤2 · justified >
false positives.

```
JUSTIFIED escalations:      0
QUESTIONABLE escalations:   0
FALSE_POSITIVE escalations: 1
```

The sole escalation was **AS02, REVIEW → PRIORITY_REVIEW**, triggered by a `HIGH` reading of rapid
Entry → Manager → VP progression that the deterministic `exceptional_progression` detector had
**already identified**. The frozen deterministic policy had deliberately decided that one MEDIUM
detector is not exceptional. **The AI added no new information before overriding that decision** —
a false-positive escalation and a failure of incremental authority.

This is why automated AI attention escalation did not earn deployment.

### 3.7 Grounding and calibration

35 findings, all provenance-validated; 0 accepted with invalid paths; 1 discarded
(`UNGROUNDED_LITERAL`); 48 unsupported inferences retained as diagnostics. Novelty distribution:
**34 LOW / 1 HIGH / 0 NONE** → 34 display-only, 1 escalation-eligible. Categories:
`multi_role_pattern` 15 · `expertise_plus_operating` 8 · `unusual_trajectory` 6 ·
`cross_domain_combination` 3 · `uncommon_transition` 3.

Every finding cited ≥2 fact groups, so the relationship gate was never the binding constraint — the
model's own reserve on `HIGH` did most of the work, backed by a policy under which count is
irrelevant.

**F-23 stands, unchanged:** source-path/literal grounding validates *provenance integrity* and does
not constitute a general proof of semantic entailment for arbitrary paraphrases. Four findings show
semantic overreach that passed validation: DQ07 inferred geographic mobility from an institution
*named* "Pacific Northwest College"; RL05 speculated about skill transfer; AS01 read employee count
as company stage; MS10 embedded path names in prose. The model itself parked most of these in
`unsupported_inferences`.

### 3.8 Queue impact

| | PRIORITY_REVIEW | REVIEW | ROUTINE |
|---|---|---|---|
| deterministic (30) | 0 | 14 | 16 |
| with cp10.2 overlay | 1 | 13 | 16 |

Additional reviewed candidates: **0**. Additional PRIORITY_REVIEW: **1** (the false positive). Queue
expansion: **0% in volume**.

### 3.9 Cost

30 attempted / 27 successful · 65,753 input tokens · 22,466 output tokens (12,096 of them reasoning,
billed as output) · **$0.06137** estimated · $0.00205 average per call · 11.6 s average latency ·
cost guard never triggered.

### 3.10 Preservation

`founder.db` was not opened by the evaluator (last modified two hours before the run wrote its
results). Stored `AI_INTERPRETED` signals **0** · decisions **0** · audit rows **0** · workflow 800
rows all `NEW` · `assessment_version` all **1** · rubric hash `4714815e84e4c2ca…` unchanged · golden
hashes unchanged.

---

## 4. Frozen scorecard

| Gate | Result |
|---|---|
| Safety | **PASS** |
| Controls ≥11/13 | **PASS** — 13/13, with 3 malformed fail-closed |
| Useful contextual ≥3/10 | **PASS** — 4/10 |
| Justified escalations ≥2 | **FAIL** — 0 |
| False positives ≤2 | **PASS** — 1 |
| Justified > false positive | **FAIL** — 0 > 1 is false |

Not reinterpreted or weakened after the fact.

---

## 5. Recommendation — **B — PROMISING, NEEDS HUMAN-LABELLED VALIDATION**

**What earned a role — display-only contextual observations.** The LLM showed some ability to
identify cross-field relationships the deterministic rubric does not explicitly model (AS04's
functional transition, AS10's concurrency pattern, AS02's seniority downshift, AS01's tenure
pattern).

**What did NOT earn a role — automated attention escalation.** The holdout produced **0 justified
escalations and 1 false-positive escalation**. AI observations should not currently influence Review
Priority.

> The deterministic system remains the authority for founder prioritization. The LLM demonstrated
> promising value as a contextual second set of eyes, but it did not demonstrate enough evidence to
> automatically change Review Priority. The recommended deployment posture is therefore
> **display-only contextual assistance, with humans interpreting the observations**. Automated
> LLM-driven attention escalation should remain **not enabled** until validated using real human
> reviewer labels.

> **Rules prioritize. AI notices. Humans interpret.**
>
> **The model proposes contextual meaning; deterministic policy and humans govern authority.**

This is not a claim of production readiness, of improved founder ranking, or of improved recall.
None of those was demonstrated.

### Implemented capability vs recommended posture

These are deliberately different, and the code has **not** been changed to match the recommendation:

* **Experimental capability tested** — cp10.2 permits a deterministic one-level raise when a `HIGH`
  contextual finding passes every gate. That capability is present in the code because it is what the
  holdout existed to test.
* **Deployment recommendation after evaluation** — do not enable or use that escalation authority.
  Treat contextual findings as display-only until human-labelled validation exists.

---

## 6. Limitations carried by this evaluation

1. No real founder **outcome labels** exist; nothing here is validated against founders who
   succeeded or failed.
2. Golden cases remain **synthetic, hand-authored policy tests**, not a sample of the real world.
3. The utility classifications are **provisional AI-assisted analysis, not independent human ground
   truth** — they were produced by an AI assistant reading the recorded evidence. No second provider
   call judged anything.
4. **3/30 malformed real-provider responses** (a 12-path cardinality mismatch); failed closed, but an
   integration-contract reliability issue.
5. **F-23** — provenance validation is not semantic entailment.
6. Useful contextual observations may be **positive, negative or ambiguous**; usefulness is not
   directionality.
7. **Automated attention escalation did not pass its frozen gates.**
8. One provider and **one model snapshot** (`gpt-5-mini-2025-08-07`); no other model was tried.
9. Real-provider responses are **not treated as bit-for-bit reproducible fixtures**; the MockAdapter
   remains the deterministic gate.
10. **Reviewer capacity remains unknown**, so queue-load trade-offs cannot be settled here.
11. The synthetic operating population carries a very **high REVIEW+ rate** (98% of the seeded 800),
    an intended consequence of recall-first policy and an open stakeholder variable.
12. **`(0→1)`** idea/company evaluation remains out of scope.

---

## 7. Roadmap for the AI layer

**Phase 1 — current recommendation.** Deterministic prioritization + display-only AI contextual
observations + human interpretation.

**Phase 2 — collect reviewer labels.** For each AI observation capture whether it was: useful ·
obvious/redundant · incorrect · ambiguous · positive · negative · decision-changing.

**Phase 3 — evaluate authority.** Measure reviewer acceptance, incremental review value,
false-positive escalation risk, and whether particular observation categories consistently predict
useful reviews. Only then reconsider automatic escalation.

**Phase 4 — learned ranking.** Only after meaningful outcome labels exist. Do not jump from this
holdout to ML ranking.

The next meaningful validation step is **not prompt tuning**.
