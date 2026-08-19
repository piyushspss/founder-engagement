"""cp10.2 — the contextual check, end to end.

    stored raw + canonical  ->  minimized facts + allowed paths   (cp10.1, reused)
                            ->  adapter (cp10.2 prompt + schema)
                            ->  strict schema validation
                            ->  provenance whitelist (fail closed)
                            ->  DETERMINISTIC contextual policy
                            ->  ephemeral overlay

Identical in shape to `service.py::run_ai_check`, and identical in every safety
property: the deterministic assessment is READ and echoed back, there is no
session here so nothing can be persisted, every failure mode lands exactly where
NO CALL would have landed, and the raise-only invariant is asserted rather than
assumed.

One difference, and it is the whole experiment: the escalation decision is made
by `contextual_policy`, from a validated finding plus the deterministic attention
value — never by the model's own rating reaching a threshold rule that was
calibrated for detectors.
"""

from __future__ import annotations

from typing import Any

from app.llm.adapter import (AdapterError, AdapterMalformed, AdapterUnavailable,
                             LLMAdapter)
from app.llm.contextual_policy import (escalation_decision,
                                       validate_contextual_finding)
from app.llm.contextual_prompt import (PROMPT_VERSION, RESPONSE_SCHEMA,
                                       SYSTEM_PROMPT, build_user_content)
from app.llm.contextual_types import ContextualCheckResult
from app.llm.types import DiscardReason, DiscardedItem
from app.llm.validate import allowed_source_paths
from app.policy.dimensions import ATTENTION_ORDER, Attention


def _unavailable(founder_id: str, provider: str, deterministic: str,
                 status: str, detail: str) -> ContextualCheckResult:
    """Fail closed: the deterministic attention is echoed back unchanged."""
    return ContextualCheckResult(
        founder_id=founder_id, available=False, provider=provider,
        prompt_version=PROMPT_VERSION, status=status, detail=detail,
        deterministic_attention=deterministic, attention_with_ai=deterministic,
        attention_changed=False, escalated=False,
        attention_change_reason="no accepted contextual findings")


def run_contextual_check(founder_id: str, raw: dict[str, Any], canonical,
                         assessment_json: dict, adapter: LLMAdapter, cfg=None, *,
                         foreign_paths: dict[str, str] | None = None,
                         ) -> ContextualCheckResult:
    """Run one optional cp10.2 contextual check and RETURN an ephemeral overlay.

    `cfg` is accepted and deliberately UNUSED: the cp10.2 policy must not depend
    on the deterministic rubric's thresholds. That coupling — reusing
    `exceptional.medium_count` for AI cues — is exactly what let cp10.1's
    self-rated MEDIUMs inherit the authority of fired detectors."""
    deterministic = str(assessment_json.get("attention"))

    if not adapter.available():
        return _unavailable(founder_id, adapter.provider, deterministic, "unavailable",
                            getattr(adapter, "last_error", None)
                            or "no AI provider is configured")

    allowed = allowed_source_paths(raw)
    user_content = build_user_content(canonical, raw, list(allowed))

    try:
        finding, metadata = adapter.analyze(SYSTEM_PROMPT, user_content,
                                            RESPONSE_SCHEMA)
    except AdapterUnavailable as exc:
        return _unavailable(founder_id, adapter.provider, deterministic,
                            "unavailable", str(exc))
    except AdapterMalformed as exc:
        result = _unavailable(founder_id, adapter.provider, deterministic,
                              "malformed", str(exc))
        return result.model_copy(update={"available": True, "discarded": [DiscardedItem(
            claim="(provider output)", source_fields=[],
            reason=DiscardReason.MALFORMED_OUTPUT, detail=str(exc))]})
    except AdapterError as exc:
        return _unavailable(founder_id, adapter.provider, deterministic, "error",
                            str(exc)).model_copy(update={"available": True})

    accepted, discarded = validate_contextual_finding(
        finding, allowed, metadata, foreign_paths=foreign_paths)
    with_ai, escalated, rule = escalation_decision(accepted, Attention(deterministic))

    # Both invariants asserted rather than assumed. A violation is a bug we want
    # loudly, not a silently mis-ranked queue.
    before = ATTENTION_ORDER[Attention(deterministic)]
    after = ATTENTION_ORDER[with_ai]
    assert after >= before, "raise-only violated: contextual overlay lowered attention"
    assert after - before <= 1, (
        "one-step ceiling violated: a single AI check moved attention more than "
        "one level")

    return ContextualCheckResult(
        founder_id=founder_id, available=True, provider=adapter.provider,
        prompt_version=PROMPT_VERSION, status="ok",
        deterministic_attention=deterministic, attention_with_ai=with_ai.value,
        attention_changed=with_ai.value != deterministic,
        attention_change_reason=rule, escalated=escalated, escalation_rule=rule,
        cues=accepted, discarded=discarded,
        unsupported_inferences=list(finding.unsupported_inferences),
        metadata=metadata)
