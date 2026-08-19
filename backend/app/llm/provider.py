"""Which adapter the application uses. One small function, deliberately.

    LLM_PROVIDER=mock       -> MockAdapter
    LLM_PROVIDER=openai     -> OpenAIAdapter
    LLM_PROVIDER=anthropic  -> AnthropicAdapter
    (unset)                 -> inferred from whichever key is present
    (anything else)         -> FAILS CLOSED (UNKNOWN_LLM_PROVIDER)

This is NOT a plugin framework and must not become one. Provider selection is a
deployment detail: it does not enter the scoring rubric, `rubric_version`,
`assessment_version` or rescore semantics, and switching providers cannot change
a single deterministic number.

Three properties hold whatever is configured:

* **No silent mock.** With no key and no SDK the selected real adapter reports
  `available() is False` and the endpoint fails closed. It never substitutes the
  MockAdapter, because canned output presented as a model result is a lie about
  provenance. The mock is opt-in only, and everything it produces carries
  `provider = "mock"` all the way to the UI badge.
* **No silent substitution.** An explicit but unrecognised `LLM_PROVIDER` — a
  typo such as `opneai` — selects NOTHING. It returns an unavailable adapter
  reporting `UNKNOWN_LLM_PROVIDER`. Quietly falling back to another provider
  would mean a misconfigured deployment silently spending money at, and sending
  founder data to, a vendor the operator did not name. Failing closed is also
  the cheaper mistake: an unavailable adapter costs nothing.
* **No SDK required.** Constructing any adapter imports no SDK; the import is
  lazy and happens inside a real call. The deterministic product runs with
  neither `openai` nor `anthropic` installed and with no key set.

Failing closed here must not take the deterministic product down: a typo in an
env var is a configuration error, not an outage. So `make_adapter` returns an
`UnknownProviderAdapter` (unavailable, honest, inert) rather than raising, and
`/config → ai_layer` reports the misconfiguration. Only an actual attempt to
USE it raises `UnknownProviderError`.
"""

from __future__ import annotations

import os
from typing import Any

from app.llm.adapter import AdapterUnavailable, LLMAdapter
from app.llm.types import AdapterMetadata, RawFinding

#: Canonical provider names accepted by `LLM_PROVIDER`.
PROVIDERS = ("mock", "openai", "anthropic")

#: Machine-readable code for a misconfigured provider name.
UNKNOWN_PROVIDER_CODE = "UNKNOWN_LLM_PROVIDER"


class UnknownProviderError(AdapterUnavailable):
    """`LLM_PROVIDER` names a provider that does not exist.

    A subclass of `AdapterUnavailable`, so every existing fail-closed path in
    `service.py` already handles it correctly: the AI check reports
    `status: "unavailable"` and the deterministic assessment is untouched."""

    code = UNKNOWN_PROVIDER_CODE


class UnknownProviderAdapter(LLMAdapter):
    """The fail-closed adapter for a misconfigured provider name.

    Deliberately inert. It reports `provider = "unknown"` — never the name of a
    real provider, so no dashboard, log line or screenshot can suggest that a
    vendor was contacted when the configuration was simply wrong."""

    provider = "unknown"

    def __init__(self, requested: str):
        self.requested = requested
        self.last_error = (
            f"{UNKNOWN_PROVIDER_CODE}: LLM_PROVIDER={requested!r} is not a known "
            f"provider (expected one of {', '.join(PROVIDERS)}). No provider was "
            f"selected and no request will be made.")

    def available(self) -> bool:
        """Always False. There is nothing to be available."""
        return False

    def analyze(self, system_prompt: str, user_content: str,
                schema: dict[str, Any]) -> tuple[RawFinding, AdapterMetadata]:
        """Always raises. Nothing is sent anywhere."""
        raise UnknownProviderError(self.last_error)


def configured_provider() -> str:
    """The provider name in effect, without constructing anything.

    Explicit `LLM_PROVIDER` wins and is returned VERBATIM even when invalid —
    reporting the typo back is what makes the misconfiguration diagnosable.
    With nothing set we infer from whichever key is present, preferring OpenAI
    only because it is the provider this deployment currently holds a key for;
    with no key at all we still name a real provider, so `/config` reports an
    honest "unavailable" rather than implying a mock is standing in."""
    requested = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if requested:
        return requested                 # valid or not — never silently swapped
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "anthropic"


def make_adapter(name: str | None = None) -> LLMAdapter:
    """Build the adapter for `name` (default: `configured_provider()`).

    An unrecognised name returns `UnknownProviderAdapter` — unavailable and
    inert — never another provider. Imports are function-local so that selecting
    one provider never imports the other's module, and so no SDK is touched at
    construction time."""
    name = (name or configured_provider()).strip().lower()

    if name == "mock":
        # Opt-in only, for demos and screenshots — never a fallback.
        # `FOUNDER_AI_MOCK_FINDING` may point at a JSON file holding a canned
        # finding; with no file the mock finds nothing.
        import json                                              # noqa: PLC0415
        from pathlib import Path                                 # noqa: PLC0415

        from app.llm.mock import MockAdapter                     # noqa: PLC0415
        path = os.environ.get("FOUNDER_AI_MOCK_FINDING")
        if path:
            return MockAdapter(json.loads(Path(path).read_text()))
        return MockAdapter(None)

    if name == "openai":
        from app.llm.openai_adapter import OpenAIAdapter         # noqa: PLC0415
        return OpenAIAdapter()

    if name == "anthropic":
        from app.llm.anthropic_adapter import AnthropicAdapter   # noqa: PLC0415
        return AnthropicAdapter()

    return UnknownProviderAdapter(name)


def default_adapter() -> LLMAdapter:
    """The adapter the API and scripts use.

    `FOUNDER_AI_ADAPTER=mock` is honoured for backward compatibility with the
    CP10 demo scripts and screenshots; `LLM_PROVIDER=mock` is the current
    spelling and both mean exactly the same thing."""
    if os.environ.get("FOUNDER_AI_ADAPTER", "").strip().lower() == "mock":
        return make_adapter("mock")
    return make_adapter()
