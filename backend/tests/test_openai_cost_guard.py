"""Cost-guard tests for the bounded real-provider evaluation. NO REAL CALLS.

The key funding the evaluation is personal, so the call and cost ceilings must
hold in CODE. These tests drive `scripts/openai_eval.BudgetedAdapter` with a
fake adapter and assert that it refuses to spend, rather than trusting that an
operator will notice in time.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from app.llm.adapter import AdapterError                         # noqa: E402
from app.llm.prompt import RESPONSE_SCHEMA, SYSTEM_PROMPT        # noqa: E402
from app.llm.types import AdapterMetadata, RawFinding            # noqa: E402

import openai_eval                                               # noqa: E402
from openai_eval import (DEFAULT_MAX_CALLS, DEFAULT_MAX_COST_USD,  # noqa: E402
                         INITIAL_PLAN, BudgetedAdapter, BudgetExceeded)

FINDING = RawFinding(exceptional_signal=False, strength="WEAK",
                     category="unusual_progression", evidence=[],
                     unsupported_inferences=[])


def _metadata(model="gpt-5-mini", tin=1000, tout=200):
    return AdapterMetadata(
        provider="openai", model=model, prompt_version="cp10.1",
        prompt_sha256="x" * 64, generated_at="2026-08-20T00:00:00+00:00",
        settings={}, usage={"input_tokens": tin, "output_tokens": tout,
                            "reasoning_tokens": 120}, latency_ms=900)


class FakeAdapter:
    """Counts real attempts so a test can prove the budget stopped them."""

    provider = "openai"

    def __init__(self, *, raises=None, tin=1000, tout=200, model="gpt-5-mini"):
        self.attempts = 0
        self.raises = raises
        self.tin, self.tout, self.model = tin, tout, model

    def available(self):
        return True

    def analyze(self, system_prompt, user_content, schema):
        self.attempts += 1
        if self.raises is not None:
            raise self.raises
        return FINDING, _metadata(self.model, self.tin, self.tout)


def _budget(inner, calls=5, cost=0.10):
    return BudgetedAdapter(inner, max_calls=calls, max_cost_usd=cost)


# ----------------------------------------------------------- call ceiling
def test_call_budget_stops_at_the_limit():
    inner = FakeAdapter()
    budget = _budget(inner, calls=3)
    for _ in range(3):
        budget.analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    with pytest.raises(BudgetExceeded):
        budget.analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert inner.attempts == 3, "a 4th provider attempt was made after the limit"


def test_budget_refuses_before_spending_not_after():
    """`check_before_call` must raise without the inner adapter being touched."""
    inner = FakeAdapter()
    budget = _budget(inner, calls=1)
    budget.analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    with pytest.raises(BudgetExceeded):
        budget.check_before_call()
    assert inner.attempts == 1


def test_a_failed_attempt_still_consumes_the_budget():
    """A failed call is still a billed attempt, so it must not be free."""
    inner = FakeAdapter(raises=AdapterError("upstream 500"))
    budget = _budget(inner, calls=2)
    for _ in range(2):
        with pytest.raises(AdapterError):
            budget.analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert budget.calls == 2
    with pytest.raises(BudgetExceeded):
        budget.analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert inner.attempts == 2


def test_retries_cannot_bypass_the_call_budget():
    """Every attempt is counted, so a retry loop exhausts the budget rather
    than slipping past it."""
    inner = FakeAdapter(raises=AdapterError("timeout"))
    budget = _budget(inner, calls=2)
    attempts = 0
    for _ in range(10):                       # a caller that naively retries
        try:
            budget.analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
        except BudgetExceeded:
            break
        except AdapterError:
            attempts += 1
    assert attempts == 2
    assert inner.attempts == 2


# ----------------------------------------------------------- cost ceiling
def test_cost_budget_stops_the_run():
    # 1M input + 1M output at gpt-5-mini pricing is far above $0.10.
    inner = FakeAdapter(tin=1_000_000, tout=1_000_000)
    budget = _budget(inner, calls=99, cost=0.10)
    budget.analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert budget.cost_usd >= 0.10
    with pytest.raises(BudgetExceeded):
        budget.analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert inner.attempts == 1


def test_cost_accumulates_across_calls():
    inner = FakeAdapter(tin=1000, tout=200)
    budget = _budget(inner)
    budget.analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    first = budget.cost_usd
    budget.analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert budget.cost_usd == pytest.approx(2 * first)
    assert first > 0


def test_estimate_uses_the_configured_model_pricing():
    inner = FakeAdapter(tin=1_000_000, tout=0, model="gpt-5-mini")
    budget = _budget(inner, cost=99.0)
    budget.analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert budget.cost_usd == pytest.approx(
        openai_eval.PRICING_USD_PER_1M["gpt-5-mini"]["input"])


def test_unknown_model_uses_the_most_expensive_fallback():
    """An unknown model must OVER-estimate, so the run stops early not late."""
    inner = FakeAdapter(tin=1_000_000, tout=0, model="some-future-model")
    budget = _budget(inner, cost=99.0)
    budget.analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert budget.cost_usd == pytest.approx(openai_eval.FALLBACK_PRICING["input"])
    assert (openai_eval.FALLBACK_PRICING["input"]
            >= max(p["input"] for p in openai_eval.PRICING_USD_PER_1M.values()))
    assert budget.ledger[-1]["fallback_pricing"] is True


def test_operator_supplied_pricing_overrides_the_table():
    inner = FakeAdapter(tin=1_000_000, tout=1_000_000)
    budget = BudgetedAdapter(inner, max_calls=5, max_cost_usd=99.0,
                             price_in=1.0, price_out=2.0)
    budget.analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert budget.cost_usd == pytest.approx(3.0)


def test_ledger_records_tokens_for_the_required_cost_line():
    inner = FakeAdapter()
    budget = _budget(inner)
    budget.analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    row = budget.ledger[-1]
    for field in ("model", "input_tokens", "output_tokens", "reasoning_tokens",
                  "cost_usd", "cumulative_usd"):
        assert field in row


def test_no_api_key_appears_in_the_ledger():
    inner = FakeAdapter()
    budget = _budget(inner)
    budget.analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert "sk-" not in str(budget.ledger)


# ------------------------------------------------------- plan is bounded
def test_the_initial_plan_is_exactly_five_calls():
    assert len(INITIAL_PLAN) == 5
    assert DEFAULT_MAX_CALLS == 5
    assert DEFAULT_MAX_COST_USD == 0.10


def test_the_initial_plan_covers_the_five_required_purposes():
    labels = [row[0] for row in INITIAL_PLAN]
    assert labels == ["A", "B", "C", "D", "E1"]
    assert sum(1 for row in INITIAL_PLAN if row[3]) == 1      # exactly one injection


def test_connectivity_and_initial_partition_the_plan_without_overlap():
    """--connectivity runs call 1; --initial runs calls 2-5. 5 in total, never 6."""
    connectivity = INITIAL_PLAN[:1]
    initial = INITIAL_PLAN[1:]
    assert len(connectivity) == 1
    assert len(initial) == 4
    assert connectivity + initial == INITIAL_PLAN


def test_extended_sample_is_refused_without_explicit_authorization():
    """Behavioural, not a string check: the wider sample must REFUSE to run."""
    import subprocess
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "openai_eval.py"),
         "--extended-sample", "--dry-run"],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 2
    assert "EXTENDED SAMPLE REFUSED" in proc.stdout
    assert "Nothing was run and nothing was spent" in proc.stdout


def test_extended_sample_still_refused_with_only_one_of_the_two_flags():
    import subprocess
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "openai_eval.py"),
         "--extended-sample", "--i-authorize-extended-run", "--dry-run"],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 2, "authorization alone must not raise the call cap"
    assert "EXTENDED SAMPLE REFUSED" in proc.stdout


def test_running_with_no_action_flag_spends_nothing():
    """A bare invocation must do nothing rather than default to running."""
    import subprocess
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "openai_eval.py")],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 2
    assert "Nothing to do" in proc.stdout


def test_dry_run_makes_no_network_request_and_states_the_budgets():
    import subprocess
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "openai_eval.py"), "--dry-run"],
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0
    assert "MAX PAID CALLS        : 5" in proc.stdout
    assert "MAX ESTIMATED SPEND   : $0.10" in proc.stdout
    assert "no network" in proc.stdout or "no network request was made" in proc.stdout
    assert "gpt-5-mini" in proc.stdout


def test_default_model_is_the_cheap_tier():
    from app.llm.openai_adapter import DEFAULT_MODEL
    assert DEFAULT_MODEL == "gpt-5-mini"


def test_harness_has_no_model_escalation_path():
    """No code path re-runs a disappointing answer against a stronger model."""
    source = (ROOT / "scripts" / "openai_eval.py").read_text()
    body = source.split("def main(")[-1]
    for banned in ("OPENAI_MODEL =", "model=\"gpt-5\"", "retry", "escalate"):
        assert banned not in body, f"model-escalation/retry path found: {banned}"
