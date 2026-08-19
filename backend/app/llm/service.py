"""The AI check, end to end.

    stored raw + canonical  ->  minimized facts + allowed paths
                            ->  adapter
                            ->  strict schema validation
                            ->  provenance whitelist (fail closed)
                            ->  raise-only aggregation
                            ->  overlay result

The deterministic assessment is READ here and never written. This module has no
access to a session, no access to `decisions` or `workflow`, and returns a value
rather than persisting one — the AI layer is an overlay by construction, not by
discipline.
"""

from __future__ import annotations

from typing import Any

from app.llm.adapter import (AdapterError, AdapterMalformed, AdapterUnavailable,
                             LLMAdapter)
from app.llm.overlay import aggregate, raise_only
from app.llm.prompt import (RESPONSE_SCHEMA, SYSTEM_PROMPT, build_user_content)
from app.llm.types import (AICheckResult, DiscardReason, DiscardedItem)
from app.llm.validate import allowed_source_paths, validate_finding
from app.policy.dimensions import Attention


def _unavailable(founder_id: str, provider: str, deterministic: str,
                 status: str, detail: str) -> AICheckResult:
    """Fail closed: the deterministic attention is echoed back unchanged."""
    return AICheckResult(
        founder_id=founder_id, available=False, provider=provider, status=status,
        detail=detail, deterministic_attention=deterministic,
        attention_with_ai=deterministic, attention_changed=False,
        attention_change_reason="no accepted AI evidence")


def run_ai_check(founder_id: str, raw: dict[str, Any], canonical, assessment_json: dict,
                 adapter: LLMAdapter, cfg, *,
                 foreign_paths: dict[str, str] | None = None) -> AICheckResult:
    """Run one optional AI evidence check and RETURN an ephemeral overlay.

    The LLM is a second set of eyes for CONTEXTUAL evidence, not a replacement
    for the deterministic baseline. Everything about this function is shaped so
    that it cannot become one:

    * the deterministic assessment is READ and echoed back unchanged;
    * accepted cues are typed `AI_INTERPRETED` and never merged into
      `broad_score`, `confidence`, `potential` or the stored `Assessment`;
    * attention is RAISE-ONLY — asserted, not assumed, before returning;
    * there is no session here, so no decision, stage, owner, note or audit row
      can be written; the result is a value the caller may show and discard;
    * every failure mode (no provider, malformed output, provider error) lands
      exactly where NO CALL would have landed: deterministic attention, echoed
      back, with the reason reported rather than hidden.

    Provider-agnostic: mock, Anthropic and OpenAI adapters all reach here
    through the same `LLMAdapter` contract, so the grounding, safety and
    persistence rules are identical whichever one is configured. Real-provider
    output is not treated as bit-for-bit deterministic."""
    deterministic = str(assessment_json.get("attention"))

    if not adapter.available():
        return _unavailable(founder_id, adapter.provider, deterministic, "unavailable",
                            getattr(adapter, "last_error", None)
                            or "no AI provider is configured")

    allowed = allowed_source_paths(raw)
    user_content = build_user_content(canonical, raw, list(allowed))

    try:
        finding, metadata = adapter.analyze(SYSTEM_PROMPT, user_content, RESPONSE_SCHEMA)
    except AdapterUnavailable as exc:
        return _unavailable(founder_id, adapter.provider, deterministic, "unavailable",
                            str(exc))
    except AdapterMalformed as exc:
        result = _unavailable(founder_id, adapter.provider, deterministic, "malformed",
                              str(exc))
        return result.model_copy(update={"available": True, "discarded": [DiscardedItem(
            claim="(provider output)", source_fields=[],
            reason=DiscardReason.MALFORMED_OUTPUT, detail=str(exc))]})
    except AdapterError as exc:
        # A provider failure must land exactly where no call would have landed.
        return _unavailable(founder_id, adapter.provider, deterministic, "error",
                            str(exc)).model_copy(update={"available": True})

    accepted, discarded = validate_finding(finding, allowed, metadata,
                                           foreign_paths=foreign_paths)
    override, floor, rule = aggregate(accepted, cfg)
    with_ai = raise_only(Attention(deterministic), floor)

    # The invariant, asserted rather than assumed. A violation is a bug we want
    # loudly, not a silently lowered priority.
    from app.policy.dimensions import ATTENTION_ORDER
    assert ATTENTION_ORDER[with_ai] >= ATTENTION_ORDER[Attention(deterministic)], (
        "raise-only violated: AI overlay attempted to lower attention")

    changed = with_ai.value != deterministic
    return AICheckResult(
        founder_id=founder_id, available=True, provider=adapter.provider, status="ok",
        deterministic_attention=deterministic, attention_with_ai=with_ai.value,
        attention_changed=changed,
        attention_change_reason=(f"{deterministic} -> {with_ai.value}: {rule}" if changed
                                 else rule),
        ai_cues=accepted, discarded=discarded,
        unsupported_inferences=list(finding.unsupported_inferences),
        aggregate_override=override, aggregate_rule=rule, metadata=metadata)
