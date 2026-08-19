"""OpenAIAdapter — a second real provider behind the SAME CP10 contract.

Added post-CP11. Nothing about the semantic contract changed to accommodate it,
and that is the point of the file: the adapter boundary drawn at CP10 was
supposed to be provider-independent, and a second real provider is the only way
to demonstrate that it actually is.

    MockAdapter · AnthropicAdapter · OpenAIAdapter
                        |
                same RawFinding + AdapterMetadata
                        |
        same grounding · same safety policy · same raise-only
        overlay · same persistence boundary (none)

What is NOT provider-specific, and is therefore not implemented here: schema
validation, the provenance whitelist, unsupported-inference handling,
exceptional aggregation and the raise-only ratchet. All of that runs in
`validate.py` / `overlay.py` / `service.py` AFTER this adapter returns, exactly
as it does for the other two providers. This file is responsible only for
"make the call, hand back a validated RawFinding or raise".

The frozen prompt carries over UNCHANGED: `prompt_version` stays `cp10.1` and
`prompt_sha256` stays
`50e3a4ef68af10dd161c1282cedc6401e5f79b73430a1a26d188ed1b880b3a76`. The frozen
`RESPONSE_SCHEMA` already satisfies OpenAI strict structured-output rules
(`additionalProperties: false` and every property required, at every object
level), so no schema edit was needed to make OpenAI accept it — verified by
test rather than assumed.

Post-cp10.1 addition: `ContextualOpenAIAdapter` at the bottom of this file is the
cp10.2 variant. It is a SUBCLASS, not an edit — the cp10.1 defaults
(`RawFinding`, `cp10.1`, `50e3a4ef…`) are unchanged, and both variants share this
file's transport, timeout, retry, token-ceiling and `tools=[]` guarantees so a
control cannot be weakened for one and not the other.

Determinism note, recorded and NOT worked around: no sampling parameter is sent.
We deliberately make no claim that OpenAI output is bit-for-bit reproducible,
and we do NOT assume the Anthropic-specific finding F-22 (that current Claude
models reject `temperature`/`top_p`/`top_k`) describes OpenAI's API — that was
observed against Anthropic and has not been observed here. The MockAdapter
remains the deterministic gate for the evaluation.

The SDK is imported LAZILY inside `_sdk()`, so the deterministic app, the whole
test suite and the evaluator all run with the `openai` package absent.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any

from app.llm.adapter import (AdapterError, AdapterMalformed, AdapterUnavailable,
                             LLMAdapter)
from app.llm.contextual_prompt import PROMPT_VERSION as CP102_PROMPT_VERSION
from app.llm.contextual_prompt import prompt_sha256 as cp102_prompt_sha256
from app.llm.contextual_types import RawContextualFinding
from app.llm.prompt import PROMPT_VERSION, prompt_sha256
from app.llm.types import AdapterMetadata, RawFinding

#: Default model, overridable with `OPENAI_MODEL`.
#:
#: Chosen for this task rather than assumed: the job is to read ONE short
#: normalized profile and either ground a claim in a supplied path or decline,
#: which needs reliable structured output and careful instruction-following far
#: more than it needs frontier reasoning depth. The mini tier gives materially
#: lower latency and cost per profile, which matters because the eventual
#: population is ~800 founders rather than 20.
#:
#: If the bounded experiment suggests the model is UNDER-reading contextual
#: evidence, re-running with `OPENAI_MODEL=gpt-5` is a legitimate, pre-declared
#: variation: changing the model is not prompt tuning, and the prompt, schema,
#: thresholds and golden cases stay frozen either way.
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-mini")

#: Name attached to the structured-output format. A transport-level label only —
#: it is NOT part of the hashed prompt contract.
SCHEMA_NAME = "founder_evidence_finding"

#: Seconds before we give up. A timeout must land exactly where "no call at all"
#: lands: deterministic attention, unchanged.
TIMEOUT_S = float(os.environ.get("OPENAI_TIMEOUT", "60"))

#: SDK-level automatic retries. DEFAULT 0 — deliberately disabled.
#:
#: Two reasons, and the second is the operative one for a personally-funded
#: evaluation: a person is waiting on a human-initiated action, so a silent
#: retry loop is worse than an honest failure; and every retry is a BILLED
#: attempt that a caller-side call budget cannot see. With retries off,
#: one `analyze()` == one provider attempt == one countable unit of spend.
MAX_RETRIES = int(os.environ.get("OPENAI_MAX_RETRIES", "0"))

#: Ceiling on billed output tokens per request, including reasoning tokens.
#:
#: Sized for the frozen CP10 schema with room to spare: a valid finding is a
#: small JSON object (a boolean, two enums, and short claim strings), so this
#: bounds worst-case spend without being able to truncate a legitimate answer.
#: A response that hits the ceiling comes back `incomplete` and is reported as
#: an error rather than being retried.
MAX_OUTPUT_TOKENS = int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "2500"))

#: Reasoning effort for the gpt-5 family. Low by default: the task is reading
#: one short profile against an explicit path whitelist, not solving a puzzle,
#: and reasoning tokens are billed as output. Set `OPENAI_REASONING_EFFORT=off`
#: to omit the parameter entirely for a non-reasoning model.
REASONING_EFFORT = os.environ.get("OPENAI_REASONING_EFFORT", "low")


class OpenAIAdapter(LLMAdapter):
    """Real OpenAI provider. Provider-specific SDK details stop at this class.

    Everything it returns is the shared internal contract — a `RawFinding` plus
    an `AdapterMetadata` — so no caller anywhere in the application needs to
    know which provider produced it.
    """

    provider = "openai"

    #: Which finding model and which frozen prompt identity this adapter speaks.
    #: Class attributes rather than call arguments so a variant is a NAMED class
    #: with its own hash, not a per-call flag someone can pass by accident. The
    #: defaults are cp10.1 and are unchanged; `ContextualOpenAIAdapter` below
    #: overrides them for cp10.2. Nothing else in this file differs between the
    #: two, which is the point: same transport, same guards, same failure modes.
    finding_model = RawFinding
    prompt_version = PROMPT_VERSION

    @staticmethod
    def prompt_hash() -> str:
        return prompt_sha256()

    def __init__(self, model: str = DEFAULT_MODEL, *, api_key: str | None = None,
                 timeout: float = TIMEOUT_S, max_retries: int = MAX_RETRIES,
                 max_output_tokens: int = MAX_OUTPUT_TOKENS,
                 reasoning_effort: str = REASONING_EFFORT):
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        #: Reason the adapter is unavailable, for `/config → ai_layer`. Names the
        #: missing ENV VAR only — never a key, a prefix, a suffix or a length.
        self.last_error: str | None = None

    # ------------------------------------------------------------------
    def _sdk(self):
        """Import the SDK LAZILY.

        Keeping this out of module scope is what preserves the property that the
        deterministic product needs no LLM SDK at all: with `openai` absent the
        adapter reports unavailable and the app is otherwise unaffected."""
        try:
            import openai                                        # noqa: PLC0415
        except ImportError as exc:
            raise AdapterUnavailable(
                "the `openai` package is not installed "
                "(pip install -r backend/requirements-openai.txt)") from exc
        return openai

    def available(self) -> bool:
        """True only when a key AND the SDK are both present.

        Fails closed and records why. It never falls back to the mock: canned
        output presented as a model result would be a lie about provenance."""
        if not self._api_key:
            self.last_error = "OPENAI_API_KEY is not set"
            return False
        try:
            self._sdk()
        except AdapterUnavailable as exc:
            self.last_error = str(exc)
            return False
        self.last_error = None
        return True

    # ------------------------------------------------------------------
    def _client(self):
        """Construct the SDK client. The key is passed directly and is never
        logged, echoed, or stored anywhere it could reach a response body."""
        openai = self._sdk()
        return openai.OpenAI(api_key=self._api_key, timeout=self.timeout,
                             max_retries=self.max_retries)

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Pull the JSON payload out of a Responses API result.

        Prefers the SDK's `output_text` convenience and falls back to walking
        `output[].content[]`, so a shape change in one does not silently yield
        an empty string that would be misread as "the model found nothing"."""
        text = getattr(response, "output_text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()

        chunks: list[str] = []
        for item in getattr(response, "output", None) or []:
            for block in getattr(item, "content", None) or []:
                value = getattr(block, "text", None)
                if isinstance(value, str):
                    chunks.append(value)
        return "".join(chunks).strip()

    def analyze(self, system_prompt: str, user_content: str,
                schema: dict[str, Any]) -> tuple[RawFinding, AdapterMetadata]:
        """Run one evidence check. Returns a schema-validated finding or raises.

        Uses OpenAI structured output in STRICT mode, but provider-side schema
        enforcement is treated as a convenience and never as a guarantee: the
        response is re-validated against `RawFinding` here (which forbids extra
        fields), and the provenance whitelist, unsupported-inference handling
        and raise-only overlay all still run afterwards in the shared pipeline.
        A response is never trusted merely because the SDK parsed it.

        Every failure mode is normalised so a bad call lands exactly where NO
        call would have landed — deterministic attention, unchanged:

        * missing key/SDK          -> AdapterUnavailable
        * transport, timeout, 4xx/5xx, refusal, truncation -> AdapterError
        * unparseable or non-conforming body -> AdapterMalformed

        No sampling parameter is sent, and no bit-for-bit reproducibility is
        claimed for this provider.
        """
        if not self._api_key:
            raise AdapterUnavailable("OPENAI_API_KEY is not set")
        client = self._client()

        settings = {
            "structured_output": "json_schema (strict)",
            "timeout_s": self.timeout,
            "max_retries": self.max_retries,
            "max_output_tokens": self.max_output_tokens,
            "reasoning_effort": self.reasoning_effort,
            "tools": "none — no web search, file search, code interpreter, "
                     "images or embeddings",
            "sampling_parameters": "not set — no determinism claim is made for "
                                   "this provider",
            "determinism": "not guaranteed; real-provider output is not treated "
                           "as a reproducible evaluation fixture",
        }

        # Only the frozen prompt, the minimized founder facts and the frozen
        # schema go out. `tools=[]` is explicit rather than implicit: no web
        # search, no file search, no code interpreter, no image or embedding
        # call, and therefore no billed side-channel beyond this one request.
        request: dict[str, Any] = {
            "model": self.model,
            "instructions": system_prompt,
            "input": user_content,
            "max_output_tokens": self.max_output_tokens,
            "tools": [],
            "text": {"format": {"type": "json_schema", "name": SCHEMA_NAME,
                                "schema": schema, "strict": True}},
        }
        if self.reasoning_effort and self.reasoning_effort.lower() != "off":
            request["reasoning"] = {"effort": self.reasoning_effort}

        started = time.perf_counter()
        try:
            response = client.responses.create(**request)
        except Exception as exc:            # transport, timeout, 4xx, 5xx, refusal
            raise AdapterError(f"{type(exc).__name__}: {exc}") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        usage = getattr(response, "usage", None)
        details = getattr(usage, "output_tokens_details", None)
        usage_dict = {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
            # Reasoning tokens are BILLED AS OUTPUT and are already included in
            # `output_tokens`. Surfaced separately so a cost report can show
            # where the output spend actually went.
            "reasoning_tokens": getattr(details, "reasoning_tokens", None),
        }
        metadata = AdapterMetadata(
            provider=self.provider, model=getattr(response, "model", self.model),
            prompt_version=self.prompt_version, prompt_sha256=self.prompt_hash(),
            generated_at=datetime.now(timezone.utc).isoformat(),
            settings=settings, usage=usage_dict, latency_ms=latency_ms)

        # A refusal or a length cut-off is a real outcome, not a crash. Report it
        # and change nothing — the deterministic assessment stands on its own.
        status = getattr(response, "status", None)
        if status == "incomplete":
            detail = getattr(response, "incomplete_details", None)
            raise AdapterError(
                f"provider returned an incomplete response "
                f"({getattr(detail, 'reason', 'unknown reason')})")

        text = self._extract_text(response)
        if not text:
            raise AdapterMalformed("provider returned no text content")

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AdapterMalformed(f"provider output was not valid JSON: {exc}") from exc

        try:
            finding = self.finding_model.model_validate(payload)
        except Exception as exc:                       # pydantic ValidationError
            raise AdapterMalformed(
                f"provider output failed schema validation: {exc}") from exc
        return finding, metadata


class ContextualOpenAIAdapter(OpenAIAdapter):
    """The cp10.2 variant. Identical transport, budget behaviour, failure
    normalisation and `tools=[]` guarantee — it differs only in which frozen
    prompt identity it stamps into the metadata and which schema it validates
    against. Subclassing rather than parameterising keeps the cp10.1 adapter
    byte-identical in behaviour: its defaults are untouched and its tests still
    exercise the same code path."""

    finding_model = RawContextualFinding
    prompt_version = CP102_PROMPT_VERSION

    @staticmethod
    def prompt_hash() -> str:
        return cp102_prompt_sha256()
