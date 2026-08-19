"""MockAdapter — deterministic, and honest about being a mock.

Default mode returns NOTHING. That is the mode the evaluation runs in, and it
is the point: a no-op overlay must leave the deterministic product exactly as it
was, and the only way to prove that is to run the whole golden set through the
layer and get identical output.

Canned findings exist for demos and adversarial tests. They are configured
explicitly by the caller — never inferred, never sampled — and every result
carries `provider = "mock"`, so a mock finding cannot be mistaken for a real
model's output at any layer of the stack.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from app.llm.adapter import AdapterMalformed, LLMAdapter
from app.llm.prompt import PROMPT_VERSION, prompt_sha256
from app.llm.types import AdapterMetadata, RawFinding

MOCK_MODEL = "mock-deterministic-v1"

#: A fixed timestamp: a deterministic adapter must be deterministic in its
#: metadata too, or the eval's own output stops being reproducible.
MOCK_GENERATED_AT = "1970-01-01T00:00:00+00:00"


class MockAdapter(LLMAdapter):
    """provider == "mock", always.

    `finding` may be a `RawFinding`, a raw dict (to exercise the validator with
    a malformed payload), a callable taking the user content, or None for the
    no-finding mode."""

    provider = "mock"

    def __init__(self, finding: RawFinding | dict[str, Any] | Callable[[str], Any] | None = None,
                 *, fail: Exception | None = None, real_clock: bool = False):
        self._finding = finding
        self._fail = fail
        self._real_clock = real_clock
        self.calls: list[str] = []

    def available(self) -> bool:
        """Always True — the mock is reachable by construction. It is opt-in and
        never a fallback for a real provider that failed."""
        return True

    def analyze(self, system_prompt: str, user_content: str,
                schema: dict[str, Any]) -> tuple[RawFinding, AdapterMetadata]:
        """Return the configured finding (or nothing) with `provider="mock"`.

        A configured raw dict is still validated, so the mock can exercise the
        malformed-output path exactly as a real provider would. Records every
        call in `self.calls` so tests can assert what was actually sent —
        notably that no identity hash appears in the payload."""
        self.calls.append(user_content)
        if self._fail is not None:
            raise self._fail

        payload = self._finding(user_content) if callable(self._finding) else self._finding
        if payload is None:
            payload = {"exceptional_signal": False, "strength": "WEAK",
                       "category": "unusual_progression", "evidence": [],
                       "unsupported_inferences": []}

        try:
            finding = (payload if isinstance(payload, RawFinding)
                       else RawFinding.model_validate(payload))
        except Exception as exc:                       # pydantic ValidationError
            raise AdapterMalformed(f"mock payload failed schema validation: {exc}") from exc

        generated_at = (datetime.now(timezone.utc).isoformat() if self._real_clock
                        else MOCK_GENERATED_AT)
        return finding, AdapterMetadata(
            provider=self.provider, model=MOCK_MODEL, prompt_version=PROMPT_VERSION,
            prompt_sha256=prompt_sha256(), generated_at=generated_at,
            settings={"deterministic": True, "note": "MOCK OUTPUT — not a model result"},
            usage={}, latency_ms=0)


def no_finding_adapter() -> MockAdapter:
    """The evaluation adapter: reachable, deterministic, finds nothing."""
    return MockAdapter(None)
