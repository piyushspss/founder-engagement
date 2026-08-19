"""ContextualMockAdapter — the deterministic cp10.2 gate.

Same contract and same honesty rules as `mock.MockAdapter`: `provider="mock"`
always, a fixed timestamp so the evaluation's own output is reproducible, canned
findings configured explicitly by the caller and never inferred, and a raw dict
still validated so the malformed path can be exercised exactly as a real
provider would exercise it. It is opt-in and is never a fallback for a real
provider that failed.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from app.llm.adapter import AdapterMalformed, LLMAdapter
from app.llm.contextual_prompt import PROMPT_VERSION, prompt_sha256
from app.llm.contextual_types import RawContextualFinding
from app.llm.mock import MOCK_GENERATED_AT, MOCK_MODEL
from app.llm.types import AdapterMetadata


class ContextualMockAdapter(LLMAdapter):
    """provider == "mock", always."""

    provider = "mock"

    def __init__(self, finding: RawContextualFinding | dict[str, Any]
                 | Callable[[str], Any] | None = None, *,
                 fail: Exception | None = None, real_clock: bool = False):
        self._finding = finding
        self._fail = fail
        self._real_clock = real_clock
        self.calls: list[str] = []

    def available(self) -> bool:
        return True

    def analyze(self, system_prompt: str, user_content: str,
                schema: dict[str, Any]) -> tuple[RawContextualFinding, AdapterMetadata]:
        self.calls.append(user_content)
        if self._fail is not None:
            raise self._fail

        payload = self._finding(user_content) if callable(self._finding) else self._finding
        if payload is None:
            payload = {"contextual_signal": False, "findings": [],
                       "unsupported_inferences": []}

        try:
            finding = (payload if isinstance(payload, RawContextualFinding)
                       else RawContextualFinding.model_validate(payload))
        except Exception as exc:                       # pydantic ValidationError
            raise AdapterMalformed(
                f"mock payload failed schema validation: {exc}") from exc

        generated_at = (datetime.now(timezone.utc).isoformat() if self._real_clock
                        else MOCK_GENERATED_AT)
        return finding, AdapterMetadata(
            provider=self.provider, model=MOCK_MODEL, prompt_version=PROMPT_VERSION,
            prompt_sha256=prompt_sha256(), generated_at=generated_at,
            settings={"deterministic": True,
                      "note": "MOCK OUTPUT — not a model result"},
            usage={}, latency_ms=0)


def no_finding_adapter() -> ContextualMockAdapter:
    """Reachable, deterministic, finds nothing."""
    return ContextualMockAdapter(None)
