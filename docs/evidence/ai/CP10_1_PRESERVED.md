# CP10.1 — PRESERVED RESULT (frozen, historical, not superseded)

**Status: CLOSED. Recommendation: C — DO NOT ENABLE.**

This file exists so that the cp10.1 experiment stays intact and reproducible after
cp10.2 was authorized. Nothing in cp10.2 amends, reinterprets or replaces anything
recorded here. cp10.1 did not succeed, and no later document is permitted to imply
that it did.

---

## 1. What was frozen, and still is

| item | value |
|---|---|
| `PROMPT_VERSION` | `cp10.1` |
| `prompt_sha256()` | `50e3a4ef68af10dd161c1282cedc6401e5f79b73430a1a26d188ed1b880b3a76` |
| system-prompt text | `backend/app/llm/prompt.py` — **unmodified**, 2888 chars, SHA-256 of the system string alone `8f72be6e81fda81e9a4e99bf83f29b511251400b3778606b044e02c125eadf1f` |
| response schema | `RESPONSE_SCHEMA` in the same file — unmodified |
| aggregation rule | `backend/app/llm/overlay.py` — unmodified (1 STRONG **or** `exceptional.medium_count` (2) MEDIUM → PRIORITY_REVIEW floor) |
| service | `backend/app/llm/service.py::run_ai_check` — unmodified |
| evaluation instrument | `scripts/openai_eval.py` — unmodified |
| model | `gpt-5-mini`, reasoning effort `low`, `tools=[]`, `max_retries=0`, `max_output_tokens=2500` |

Re-verified at the start of the cp10.2 work: `prompt_sha256() == 50e3a4ef…` → **True**.

cp10.2 is implemented in **new modules**. Not one byte of the cp10.1 prompt, schema,
policy, service or eval script was edited to accommodate it. `cp10.1` therefore remains
runnable exactly as it was, for comparison.

## 2. The five-call real-provider run (DEVELOPMENT / DISCOVERY SET)

Pre-declared before any output was seen, in `scripts/openai_eval.py::INITIAL_PLAN`:

| # | call | case | purpose |
|---|---|---|---|
| 1 | A | RL01 | connectivity / auth / structured output parses |
| 2 | B | AS09 | contextual-positive candidate (deterministic headroom) |
| 3 | C | RL02 | negative control (nothing to find) |
| 4 | D | RL01 + injected headline | adversarial / prompt injection |
| 5 | E1 | AS03 | ambiguous/spiky contextual case |

These five cases are **development cases**. They are excluded from the cp10.2 primary
holdout and may never be used to claim cp10.2 works.

### Outcome, as adjudicated by the operator

* The **safety architecture held**. Grounding, the source-path whitelist, identity
  minimisation, the raise-only ratchet, the ephemeral overlay and the injection
  boundary all behaved as designed.
* The **calibration did not**. There is a scale mismatch between
  1. *deterministic* strength, where `MEDIUM` means "a specific, meaningful detector
     fired", and
  2. *LLM self-rated* strength, where `gpt-5-mini` assigns `MEDIUM` to facts that are
     merely true and grounded.
* Because cp10.1 fed the model's self-rated strength straight into the deterministic
  exceptional aggregation rule, **two grounded-but-mundane observations satisfied
  `2 × MEDIUM → PRIORITY_REVIEW`**. Ordinary evidence polluted reviewer priority.

**Recommendation: C — DO NOT ENABLE.** Unchanged, and not revisited by cp10.2.

> **Transcript note (honest gap).** The per-call stdout of the five paid calls was not
> written to a file by `scripts/openai_eval.py` — it printed to the terminal of the
> session that ran it and is not in this repository. Everything above that is a *repo
> fact* (prompt, hash, plan, case selection, model settings) is verified; the outcome
> summary is the operator's adjudication of that run, recorded as such. If the raw
> terminal output is still available, paste it under §2.1 below; it is the only part of
> the cp10.1 record that is not independently reconstructible, and re-running the five
> calls to recover it would cost money and would *not* recover the original outputs
> anyway (no determinism claim is made for this provider).

### 2.1 Verbatim five-call transcript

*(not captured — see the transcript note above)*

## 3. What cp10.2 is, relative to this

cp10.2 is a **follow-up experiment motivated by the strength-scale mismatch observed
here**. It is not a fix applied to cp10.1, not a re-run of cp10.1, and not evidence
about cp10.1. Both experiments are reported separately and cp10.1's conclusion stands.
