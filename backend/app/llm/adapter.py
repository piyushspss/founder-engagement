"""The adapter interface. Nothing outside this package imports an SDK.

`analyze()` returns a validated `RawFinding` or raises. It never returns a
partially-trusted object: an adapter that cannot produce a schema-conforming
finding raises `AdapterMalformed`, and the service turns that into a reported
discard with the deterministic assessment untouched.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.llm.types import AdapterMetadata, RawFinding


class AdapterError(RuntimeError):
    """The provider was reachable but the call failed (timeout, 5xx, refusal)."""


class AdapterUnavailable(AdapterError):
    """No provider is configured. The app continues; the AI check reports this
    honestly rather than silently substituting a mock."""


class AdapterMalformed(AdapterError):
    """The provider replied, but not with a valid finding."""


@runtime_checkable
class LLMAdapter(Protocol):
    """Implemented by MockAdapter and AnthropicAdapter."""

    provider: str

    def available(self) -> bool:
        """True when this adapter can actually make a call right now."""
        ...

    def analyze(self, system_prompt: str, user_content: str,
                schema: dict[str, Any]) -> tuple[RawFinding, AdapterMetadata]:
        """Run one evidence check. Raises AdapterError on any failure."""
        ...
