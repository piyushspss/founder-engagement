"""AnthropicAdapter — the real provider, enabled only when it can actually run.

The SDK is imported lazily inside `analyze()`, so the deterministic app, the
test suite and the evaluator all run with the package absent. With no key and no
SDK the adapter reports `available() is False` and the endpoint fails closed;
it never falls back to the mock, because presenting canned output as a model
result would be a lie about provenance.

Determinism note (recorded, not worked around): `temperature`, `top_p` and
`top_k` are **rejected** by current Claude models — there is no sampling knob to
pin. The lowest-variability settings actually available are a low effort level
and a strict output schema, and both are recorded in the result metadata. We do
not claim bit-for-bit reproducibility for real-provider runs.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from app.llm.adapter import (AdapterError, AdapterMalformed, AdapterUnavailable,
                             LLMAdapter)
from app.llm.prompt import PROMPT_VERSION, prompt_sha256
from app.llm.types import AdapterMetadata, RawFinding

#: Current model id per the claude-api reference. Overridable for a deliberate
#: experiment; never silently downgraded.
DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")

#: Lowest practical variability the API offers. Sampling parameters are not
#: among them — passing temperature/top_p/top_k to a current model is a 400.
EFFORT = os.environ.get("ANTHROPIC_EFFORT", "low")
MAX_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "4000"))


class AnthropicAdapter(LLMAdapter):
    """Real Anthropic provider behind the shared `LLMAdapter` contract.

    Provider-specific SDK details stop here: it returns the same `RawFinding` +
    `AdapterMetadata` pair as every other adapter, so grounding, safety policy,
    raise-only overlay and the persistence boundary are identical whichever
    provider is configured."""

    provider = "anthropic"

    def __init__(self, model: str = DEFAULT_MODEL, *, api_key: str | None = None,
                 effort: str = EFFORT, max_tokens: int = MAX_TOKENS):
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.last_error: str | None = None

    # ------------------------------------------------------------------
    def _sdk(self):
        """Import the SDK LAZILY. Keeping this out of module scope is what lets
        the deterministic app, the tests and the evaluator run with the
        `anthropic` package absent."""
        try:
            import anthropic                                    # noqa: PLC0415
        except ImportError as exc:
            raise AdapterUnavailable(
                "the `anthropic` package is not installed "
                "(pip install -r backend/requirements-llm.txt)") from exc
        return anthropic

    def available(self) -> bool:
        """True only when a key AND the SDK are both present.

        Records the reason in `last_error` for the UI/`/config` to display. The
        reason names the missing ENV VAR, never a key or any part of one."""
        if not self._api_key:
            self.last_error = "ANTHROPIC_API_KEY is not set"
            return False
        try:
            self._sdk()
        except AdapterUnavailable as exc:
            self.last_error = str(exc)
            return False
        return True

    # ------------------------------------------------------------------
    def analyze(self, system_prompt: str, user_content: str,
                schema: dict[str, Any]) -> tuple[RawFinding, AdapterMetadata]:
        """One real call. Returns a schema-validated finding or raises.

        Provider-side structured output does NOT replace application
        validation: the response is re-validated here, and the provenance
        whitelist still runs afterwards in `validate_finding`. Every failure —
        transport, 4xx/5xx, refusal, unparseable body — becomes an
        `AdapterError`/`AdapterMalformed`, so a bad call lands exactly where no
        call would have landed."""
        if not self._api_key:
            raise AdapterUnavailable("ANTHROPIC_API_KEY is not set")
        anthropic = self._sdk()

        client = anthropic.Anthropic(api_key=self._api_key)
        settings = {
            "effort": self.effort,
            "max_tokens": self.max_tokens,
            "structured_output": "json_schema",
            "sampling_parameters": ("not set — temperature/top_p/top_k are rejected "
                                    "by current Claude models"),
            "determinism": "not guaranteed; lowest practical variability only",
        }

        started = time.perf_counter()
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                output_config={"effort": self.effort,
                               "format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": user_content}],
            )
        except Exception as exc:                       # transport, 4xx, 5xx, timeout
            raise AdapterError(f"{type(exc).__name__}: {exc}") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        usage = getattr(response, "usage", None)
        usage_dict = {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None),
            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens",
                                                   None),
        }
        metadata = AdapterMetadata(
            provider=self.provider, model=getattr(response, "model", self.model),
            prompt_version=PROMPT_VERSION, prompt_sha256=prompt_sha256(),
            generated_at=datetime.now(timezone.utc).isoformat(),
            settings=settings, usage=usage_dict, latency_ms=latency_ms)

        # A safety refusal is a real outcome, not a crash: report it and change
        # nothing. The deterministic assessment stands on its own.
        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            raise AdapterError(
                f"provider declined the request (refusal"
                f"{', ' + str(getattr(details, 'category', '')) if details else ''})")

        text = "".join(block.text for block in response.content
                       if getattr(block, "type", None) == "text").strip()
        if not text:
            raise AdapterMalformed("provider returned no text content")

        import json                                             # noqa: PLC0415
        try:
            finding = RawFinding.model_validate(json.loads(text))
        except Exception as exc:
            raise AdapterMalformed(
                f"provider output failed schema validation: {exc}") from exc
        return finding, metadata


def default_adapter() -> LLMAdapter:
    """Back-compat re-export. Provider selection moved to `app.llm.provider`
    when OpenAI was added; this name is kept so existing imports keep working."""
    from app.llm.provider import default_adapter as _default   # noqa: PLC0415
    return _default()
