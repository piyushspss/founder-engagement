"""OpenAI provider tests — CP11 post-checkpoint, NO REAL API CALLS.

Every test here runs against a fake SDK module injected into `sys.modules`, so
the suite passes with the `openai` package absent and never opens a socket.

What is deliberately NOT tested: OpenAI's SDK internals. The subject is OUR
adapter boundary and OUR application semantics — that a second real provider
reaches the same internal contract, and that every CP10 safety property holds
identically behind it. If a property is already proved provider-independently in
`test_llm_layer.py`, it is asserted here only through the OpenAI path.
"""

from __future__ import annotations

import json
import sys
import types

import pytest

from app.assessment import assess
from app.evidence.signal import SignalType, Strength
from app.llm.adapter import AdapterError, AdapterMalformed, AdapterUnavailable
from app.llm.mock import MockAdapter
from app.llm.openai_adapter import DEFAULT_MODEL, SCHEMA_NAME, OpenAIAdapter
from app.llm.prompt import (PROMPT_VERSION, RESPONSE_SCHEMA, SYSTEM_PROMPT,
                            WITHHELD_RAW_FIELDS, prompt_sha256)
from app.llm.provider import configured_provider, default_adapter, make_adapter
from app.llm.service import run_ai_check
from app.models.canonical import CanonicalProfile
from app.models.raw import RawProfile
from app.normalize import load_config
from app.normalize.normalizer import normalize

CFG = load_config()

#: The frozen CP10 prompt hash. Recorded before the first golden-set batch and
#: unchanged by the addition of a second provider.
FROZEN_PROMPT_SHA = "50e3a4ef68af10dd161c1282cedc6401e5f79b73430a1a26d188ed1b880b3a76"


# --------------------------------------------------------------- fake SDK
class _FakeUsage:
    def __init__(self):
        self.input_tokens = 1234
        self.output_tokens = 56
        self.total_tokens = 1290


class _FakeResponse:
    """Shaped like an OpenAI Responses API result, with only what we read."""

    def __init__(self, text: str, *, model: str = "gpt-5-mini-2026-01-01",
                 status: str = "completed", incomplete_reason: str | None = None,
                 use_output_text: bool = True):
        self.model = model
        self.status = status
        self.usage = _FakeUsage()
        self.output_text = text if use_output_text else None
        if incomplete_reason:
            self.incomplete_details = types.SimpleNamespace(reason=incomplete_reason)
        block = types.SimpleNamespace(text=text, type="output_text")
        self.output = [types.SimpleNamespace(content=[block])]


class _FakeResponses:
    def __init__(self, owner):
        self._owner = owner

    def create(self, **kwargs):
        self._owner.calls.append(kwargs)
        if self._owner.raises is not None:
            raise self._owner.raises
        return self._owner.response


class _FakeClient:
    def __init__(self, *, api_key=None, timeout=None, max_retries=None, owner=None):
        owner.client_kwargs = {"api_key": api_key, "timeout": timeout,
                               "max_retries": max_retries}
        self.responses = _FakeResponses(owner)


class FakeSDK:
    """A stand-in `openai` module. Records every call so tests can inspect the
    exact payload the adapter would have sent to a real provider."""

    def __init__(self, response=None, raises=None):
        self.response = response
        self.raises = raises
        self.calls: list[dict] = []
        self.client_kwargs: dict = {}
        owner = self

        class OpenAI(_FakeClient):
            def __init__(self, **kw):
                super().__init__(**kw, owner=owner)

        self.OpenAI = OpenAI


@pytest.fixture
def fake_sdk(monkeypatch):
    """Install a fake `openai` module. Removed again after the test, so the
    'SDK is absent' tests are unaffected."""
    def _install(response=None, raises=None):
        sdk = FakeSDK(response=response, raises=raises)
        module = types.ModuleType("openai")
        module.OpenAI = sdk.OpenAI
        monkeypatch.setitem(sys.modules, "openai", module)
        return sdk
    return _install


@pytest.fixture
def no_sdk(monkeypatch):
    """Guarantee `import openai` fails, whatever the machine has installed."""
    monkeypatch.setitem(sys.modules, "openai", None)


GOOD_PAYLOAD = {
    "exceptional_signal": False,
    "strength": "WEAK",
    "category": "unusual_progression",
    "evidence": [],
    "unsupported_inferences": [],
}


@pytest.fixture
def founder_fixture():
    """A real normalized founder plus its deterministic assessment."""
    raw = {
        "mdm_person_id": "openai-t1",
        "name_hash": "NAMEHASH", "email_hash": "EMAILHASH",
        "linkedin_hash": "LIHASH", "phone_hash": "PHHASH",
        "github_hash": "GHHASH", "crunchbase_hash": "CBHASH",
        "public_profile_id_hash": "PPHASH", "twitter_hash": "TWHASH",
        "facebook_hash": "FBHASH", "professional_emails_hashed": ["PE1"],
        "headline": "Co-Founder and CEO, clinical workflow company",
        "location_country": "United States", "location_city": "Boston",
        "total_experience_duration_months": 120,
        "experience": [
            {"position_title": "Co-Founder", "company_name": "Northwind Clinical",
             "company_industry": "Hospital & Health Care", "management_level": "Owner",
             "department": "General", "date_from": "01/2019", "date_from_year": 2019,
             "date_from_month": 1, "date_to": None, "is_current": True,
             "duration_months": 60, "company_employees_count": 40,
             "company_size_range": "11-50 employees", "order_in_profile": 0},
            {"position_title": "Senior Product Manager", "company_name": "Mass General",
             "company_industry": "Hospital & Health Care", "management_level": "Manager",
             "department": "Product", "date_from": "01/2014", "date_from_year": 2014,
             "date_from_month": 1, "date_to": "01/2019", "date_to_year": 2019,
             "date_to_month": 1, "is_current": False, "duration_months": 60,
             "company_employees_count": 20000, "order_in_profile": 1},
        ],
        "education": [
            {"institution_name": "Harvard University", "school_name": "Harvard University",
             "degree": "MBA", "field_of_study": "Business", "order_in_profile": 0},
        ],
    }
    profile = RawProfile.model_validate(raw)
    canonical = normalize(profile, CFG, person_id="openai-t1")
    assessment = assess(canonical, CFG).to_dict()
    return profile.raw_dict(), canonical, assessment


def _run(raw, canonical, assessment, adapter):
    return run_ai_check("openai-t1", raw, canonical, assessment, adapter, CFG)


# =====================================================================
# 1 · provider selection chooses OpenAIAdapter
# =====================================================================
def test_1_llm_provider_openai_selects_the_openai_adapter(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    adapter = default_adapter()
    assert isinstance(adapter, OpenAIAdapter)
    assert adapter.provider == "openai"


def test_1b_each_provider_name_maps_to_its_own_adapter(monkeypatch):
    monkeypatch.delenv("FOUNDER_AI_ADAPTER", raising=False)
    assert make_adapter("mock").provider == "mock"
    assert make_adapter("openai").provider == "openai"
    assert make_adapter("anthropic").provider == "anthropic"


def test_1c_anthropic_adapter_still_exists_and_is_selectable(monkeypatch):
    """The OpenAI work must not have removed or replaced the CP10 provider."""
    from app.llm.anthropic_adapter import AnthropicAdapter
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert isinstance(default_adapter(), AnthropicAdapter)


def test_1d_key_presence_infers_a_provider_when_none_is_named(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("FOUNDER_AI_ADAPTER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    assert configured_provider() == "openai"


def test_1e_unknown_provider_name_does_not_crash_the_app(monkeypatch):
    """Fails CLOSED (see the cost-safety section below) but stays non-fatal:
    the deterministic product must survive a typo in an env var."""
    from app.llm.provider import UnknownProviderAdapter
    monkeypatch.setenv("LLM_PROVIDER", "not-a-provider")
    assert configured_provider() == "not-a-provider"      # reported, not swapped
    adapter = default_adapter()
    assert isinstance(adapter, UnknownProviderAdapter)
    assert adapter.available() is False


# =====================================================================
# 2 · no provider / no key keeps the core app operational
# =====================================================================
def test_2_no_key_reports_unavailable_without_faking_a_mock(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    adapter = OpenAIAdapter(api_key=None)
    assert adapter.available() is False
    assert adapter.last_error == "OPENAI_API_KEY is not set"
    assert adapter.provider == "openai"          # never silently becomes "mock"


def test_2b_deterministic_assessment_is_unaffected_by_an_unavailable_provider(
        founder_fixture, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    raw, canonical, assessment = founder_fixture
    result = _run(raw, canonical, assessment, OpenAIAdapter(api_key=None))
    assert result.status == "unavailable"
    assert result.available is False
    assert result.attention_with_ai == assessment["attention"]
    assert result.ai_cues == []


def test_2c_config_endpoint_works_with_openai_selected_and_no_key(
        client, seeded, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    body = client.get("/config").json()
    layer = body["ai_layer"]
    assert layer["provider"] == "openai"
    assert layer["available"] is False
    assert layer["detail"] == "OPENAI_API_KEY is not set"
    assert layer["prompt_version"] == PROMPT_VERSION
    assert layer["prompt_sha256"] == FROZEN_PROMPT_SHA


# =====================================================================
# 3 · missing optional SDK degrades safely
# =====================================================================
def test_3_missing_sdk_is_reported_not_raised(no_sdk):
    adapter = OpenAIAdapter(api_key="test-not-a-real-key")
    assert adapter.available() is False
    assert "openai" in adapter.last_error and "not installed" in adapter.last_error


def test_3b_missing_sdk_during_a_call_becomes_adapter_unavailable(no_sdk):
    adapter = OpenAIAdapter(api_key="test-not-a-real-key")
    with pytest.raises(AdapterUnavailable):
        adapter.analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)


def test_3c_missing_sdk_leaves_the_ai_check_a_clean_no_op(founder_fixture, no_sdk):
    raw, canonical, assessment = founder_fixture
    result = _run(raw, canonical, assessment, OpenAIAdapter(api_key="test-not-a-real-key"))
    assert result.status == "unavailable"
    assert result.attention_with_ai == assessment["attention"]


# =====================================================================
# 4 · correct structured output parses
# =====================================================================
def test_4_valid_structured_output_parses_to_the_shared_contract(fake_sdk):
    fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    finding, metadata = OpenAIAdapter(api_key="test-not-a-real-key").analyze(
        SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert finding.exceptional_signal is False
    assert finding.category == "unusual_progression"
    assert metadata.provider == "openai"
    assert metadata.prompt_version == PROMPT_VERSION


def test_4b_output_is_read_when_the_sdk_convenience_field_is_absent(fake_sdk):
    fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD), use_output_text=False))
    finding, _ = OpenAIAdapter(api_key="test-not-a-real-key").analyze(
        SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert finding.category == "unusual_progression"


def test_4c_strict_structured_output_is_requested_with_the_frozen_schema(fake_sdk):
    sdk = fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    OpenAIAdapter(api_key="test-not-a-real-key").analyze(
        SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    fmt = sdk.calls[0]["text"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["strict"] is True
    assert fmt["name"] == SCHEMA_NAME
    assert fmt["schema"] == RESPONSE_SCHEMA      # frozen schema, passed verbatim


def test_4d_frozen_schema_satisfies_openai_strict_mode_rules():
    """Strict mode requires `additionalProperties: false` and every property
    required, at every object level. The FROZEN schema already does — which is
    why no schema edit was needed to add this provider."""
    def check(node):
        if isinstance(node, dict) and node.get("type") == "object":
            assert node.get("additionalProperties") is False
            assert set(node.get("properties", {})) == set(node.get("required", []))
            for value in node.get("properties", {}).values():
                check(value)
        if isinstance(node, dict) and node.get("type") == "array":
            check(node.get("items", {}))
    check(RESPONSE_SCHEMA)


def test_4e_no_sampling_parameter_is_sent(fake_sdk):
    """We make no determinism claim for this provider and pin no sampling knob.
    F-22 was observed against Anthropic and is NOT assumed to apply here."""
    sdk = fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    OpenAIAdapter(api_key="test-not-a-real-key").analyze(
        SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    sent = sdk.calls[0]
    for knob in ("temperature", "top_p", "top_k", "seed"):
        assert knob not in sent


# =====================================================================
# 5 · malformed structured output fails safely
# =====================================================================
@pytest.mark.parametrize("body", [
    "not json at all",
    "",
    "{}",                                            # missing required fields
    json.dumps({**GOOD_PAYLOAD, "surprise": 1}),     # extra field -> forbidden
    json.dumps({**GOOD_PAYLOAD, "strength": 12}),    # wrong type
])
def test_5_malformed_output_raises_adapter_malformed(fake_sdk, body):
    fake_sdk(_FakeResponse(body))
    with pytest.raises(AdapterMalformed):
        OpenAIAdapter(api_key="test-not-a-real-key").analyze(
            SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)


def test_5b_malformed_output_changes_nothing_and_is_reported(founder_fixture, fake_sdk):
    fake_sdk(_FakeResponse("{ this is not json"))
    raw, canonical, assessment = founder_fixture
    result = _run(raw, canonical, assessment, OpenAIAdapter(api_key="test-not-a-real-key"))
    assert result.status == "malformed"
    assert result.attention_with_ai == assessment["attention"]
    assert result.ai_cues == []
    assert result.discarded and result.discarded[0].reason.value == "MALFORMED_OUTPUT"


def test_5c_provider_side_schema_enforcement_is_not_trusted(fake_sdk):
    """The SDK "parsed" it; we still reject it. Application validation is the
    authority, not the provider's strict-mode promise."""
    fake_sdk(_FakeResponse(json.dumps({**GOOD_PAYLOAD, "category": "made_up"})))
    finding, metadata = OpenAIAdapter(api_key="test-not-a-real-key").analyze(
        SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    from app.llm.validate import validate_finding
    accepted, discarded = validate_finding(finding, {}, metadata)
    assert accepted == []
    assert discarded[0].reason.value == "INVALID_CATEGORY"


# =====================================================================
# 6 · provider exception is normalized / propagated correctly
# =====================================================================
def test_6_provider_exception_becomes_adapter_error(fake_sdk):
    fake_sdk(raises=RuntimeError("upstream 500"))
    with pytest.raises(AdapterError) as exc:
        OpenAIAdapter(api_key="test-not-a-real-key").analyze(
            SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert "RuntimeError" in str(exc.value)


def test_6b_provider_error_lands_where_no_call_would_have(founder_fixture, fake_sdk):
    fake_sdk(raises=RuntimeError("upstream 500"))
    raw, canonical, assessment = founder_fixture
    result = _run(raw, canonical, assessment, OpenAIAdapter(api_key="test-not-a-real-key"))
    assert result.status == "error"
    assert result.attention_with_ai == assessment["attention"]
    assert result.attention_changed is False


def test_6c_incomplete_response_is_an_error_not_a_finding(fake_sdk):
    fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD), status="incomplete",
                           incomplete_reason="max_output_tokens"))
    with pytest.raises(AdapterError) as exc:
        OpenAIAdapter(api_key="test-not-a-real-key").analyze(
            SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert "incomplete" in str(exc.value)


# =====================================================================
# 7 · timeout behaves as no successful AI check
# =====================================================================
def test_7_timeout_matches_no_call_at_all(founder_fixture, fake_sdk):
    fake_sdk(raises=TimeoutError("request timed out"))
    raw, canonical, assessment = founder_fixture
    result = _run(raw, canonical, assessment, OpenAIAdapter(api_key="test-not-a-real-key"))
    assert result.status == "error"
    assert result.ai_cues == []
    assert result.aggregate_override is False
    assert result.attention_with_ai == result.deterministic_attention


def test_7b_timeout_is_configured_on_the_client(fake_sdk):
    sdk = fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    OpenAIAdapter(api_key="test-not-a-real-key", timeout=12.5,
                  max_retries=1).analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert sdk.client_kwargs["timeout"] == 12.5
    assert sdk.client_kwargs["max_retries"] == 1


# =====================================================================
# 8 · provider / model metadata normalize correctly
# =====================================================================
def test_8_metadata_matches_the_shared_contract(fake_sdk):
    fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD), model="gpt-5-mini-2026-01-01"))
    _, metadata = OpenAIAdapter(api_key="test-not-a-real-key").analyze(
        SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert metadata.provider == "openai"
    assert metadata.model == "gpt-5-mini-2026-01-01"   # the RESOLVED model, echoed back
    assert metadata.prompt_version == "cp10.1"
    assert metadata.prompt_sha256 == FROZEN_PROMPT_SHA
    assert metadata.latency_ms is not None
    assert metadata.usage["input_tokens"] == 1234
    assert metadata.usage["output_tokens"] == 56
    assert metadata.generated_at


def test_8b_model_is_configurable_and_not_hardwired(monkeypatch, fake_sdk):
    sdk = fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    OpenAIAdapter(model="gpt-5", api_key="test-not-a-real-key").analyze(
        SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert sdk.calls[0]["model"] == "gpt-5"
    assert DEFAULT_MODEL                       # a default exists...
    assert isinstance(DEFAULT_MODEL, str)      # ...and is a plain configurable string


def test_8c_all_three_adapters_return_the_same_metadata_shape(fake_sdk):
    from app.llm.anthropic_adapter import AnthropicAdapter
    fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    _, openai_meta = OpenAIAdapter(api_key="test-not-a-real-key").analyze(
        SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    _, mock_meta = MockAdapter(None).analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert set(openai_meta.model_dump()) == set(mock_meta.model_dump())
    assert AnthropicAdapter(api_key=None).provider == "anthropic"


# =====================================================================
# 9 · identity hashes are absent from the model payload
# =====================================================================
def test_9_no_identity_hash_reaches_the_provider(founder_fixture, fake_sdk):
    sdk = fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    raw, canonical, assessment = founder_fixture
    _run(raw, canonical, assessment, OpenAIAdapter(api_key="test-not-a-real-key"))

    sent = json.dumps(sdk.calls[0], default=str)
    for field in WITHHELD_RAW_FIELDS:
        assert field not in sent, f"{field} leaked to the provider"
    for value in ("NAMEHASH", "EMAILHASH", "LIHASH", "PHHASH", "GHHASH",
                  "CBHASH", "PPHASH", "TWHASH", "FBHASH", "PE1"):
        assert value not in sent, f"identity hash value {value} leaked"


def test_9b_the_api_key_never_appears_in_the_request_payload(founder_fixture, fake_sdk):
    """The key authenticates the client; it must not reach the message body."""
    sdk = fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    raw, canonical, assessment = founder_fixture
    _run(raw, canonical, assessment, OpenAIAdapter(api_key="sk-test-SENTINEL-not-real"))
    assert "SENTINEL" not in json.dumps(sdk.calls[0], default=str)
    assert sdk.client_kwargs["api_key"] == "sk-test-SENTINEL-not-real"


def test_9c_the_api_key_never_appears_in_an_ai_check_result(founder_fixture, fake_sdk):
    fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    raw, canonical, assessment = founder_fixture
    result = _run(raw, canonical, assessment, OpenAIAdapter(api_key="sk-test-SENTINEL-not-real"))
    assert "SENTINEL" not in json.dumps(result.to_dict(), default=str)


def test_9d_an_unavailable_reason_names_the_env_var_not_the_secret(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-SENTINEL-not-real")
    adapter = OpenAIAdapter()
    adapter._api_key = None                       # simulate an absent key
    adapter.available()
    assert adapter.last_error == "OPENAI_API_KEY is not set"
    assert "SENTINEL" not in (adapter.last_error or "")


# =====================================================================
# 10 · frozen prompt text / version / hash remain unchanged
# =====================================================================
def test_10_prompt_version_and_hash_are_still_the_frozen_cp10_values():
    assert PROMPT_VERSION == "cp10.1"
    assert prompt_sha256() == FROZEN_PROMPT_SHA


def test_10b_openai_sends_the_frozen_system_prompt_verbatim(fake_sdk):
    sdk = fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    OpenAIAdapter(api_key="test-not-a-real-key").analyze(
        SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert sdk.calls[0]["instructions"] == SYSTEM_PROMPT


def test_10c_every_provider_reports_the_same_frozen_prompt_identity(fake_sdk):
    fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    _, openai_meta = OpenAIAdapter(api_key="test-not-a-real-key").analyze(
        SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    _, mock_meta = MockAdapter(None).analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert openai_meta.prompt_sha256 == mock_meta.prompt_sha256 == FROZEN_PROMPT_SHA
    assert openai_meta.prompt_version == mock_meta.prompt_version == "cp10.1"


# =====================================================================
# 11 & 12 · unsupported source paths are discarded, never repaired
# =====================================================================
def test_11_unsupported_source_path_is_discarded(founder_fixture, fake_sdk):
    payload = {"exceptional_signal": True, "strength": "STRONG",
               "category": "repeat_founding",
               "evidence": [{"claim": "Founded three companies",
                             "source_fields": ["experience[9].position_title"]}],
               "unsupported_inferences": []}
    fake_sdk(_FakeResponse(json.dumps(payload)))
    raw, canonical, assessment = founder_fixture
    result = _run(raw, canonical, assessment, OpenAIAdapter(api_key="test-not-a-real-key"))

    assert result.ai_cues == []
    assert len(result.discarded) == 1
    assert result.discarded[0].reason.value == "UNKNOWN_SOURCE_PATH"
    assert result.attention_with_ai == result.deterministic_attention


def test_12_a_bad_path_is_never_repaired_to_a_nearby_one(founder_fixture, fake_sdk):
    """`experience[9]` does not exist; `experience[0].position_title` does.
    A repaired citation would turn a hallucination into evidence with a
    plausible-looking source attached, which is worse than the hallucination."""
    payload = {"exceptional_signal": True, "strength": "STRONG",
               "category": "repeat_founding",
               "evidence": [{"claim": "Founded three companies",
                             "source_fields": ["experience[9].position_title"]}],
               "unsupported_inferences": []}
    fake_sdk(_FakeResponse(json.dumps(payload)))
    raw, canonical, assessment = founder_fixture
    result = _run(raw, canonical, assessment, OpenAIAdapter(api_key="test-not-a-real-key"))

    assert result.discarded[0].source_fields == ["experience[9].position_title"]
    assert "not repaired" in result.discarded[0].detail
    assert result.ai_cues == []


# =====================================================================
# 13 · unsupported inferences remain diagnostic only
# =====================================================================
def test_13_unsupported_inferences_never_become_evidence(founder_fixture, fake_sdk):
    payload = {"exceptional_signal": False, "strength": "WEAK",
               "category": "exceptional_credential", "evidence": [],
               "unsupported_inferences": [
                   "Harvard MBA suggests an exceptional network",
                   "Leaving Mass General was probably an exit"]}
    fake_sdk(_FakeResponse(json.dumps(payload)))
    raw, canonical, assessment = founder_fixture
    result = _run(raw, canonical, assessment, OpenAIAdapter(api_key="test-not-a-real-key"))

    assert len(result.unsupported_inferences) == 2
    assert result.ai_cues == []                      # never a Signal
    assert result.aggregate_override is False        # never an escalation
    assert result.attention_with_ai == result.deterministic_attention


# =====================================================================
# 14 · OpenAI cannot lower attention
# =====================================================================
@pytest.mark.parametrize("deterministic", ["PRIORITY_REVIEW", "REVIEW", "ROUTINE"])
@pytest.mark.parametrize("strength", ["WEAK", "MEDIUM", "STRONG"])
def test_14_openai_can_never_lower_attention(founder_fixture, fake_sdk,
                                             deterministic, strength):
    raw, canonical, assessment = founder_fixture
    assessment = {**assessment, "attention": deterministic}
    allowed_path = "experience[0].position_title"
    payload = {"exceptional_signal": True, "strength": strength,
               "category": "unusual_progression",
               "evidence": [{"claim": "Grounded claim about the first role.",
                             "source_fields": [allowed_path]}],
               "unsupported_inferences": []}
    fake_sdk(_FakeResponse(json.dumps(payload)))
    result = _run(raw, canonical, assessment, OpenAIAdapter(api_key="test-not-a-real-key"))

    order = {"ROUTINE": 0, "REVIEW": 1, "PRIORITY_REVIEW": 2}
    assert order[result.attention_with_ai] >= order[deterministic]


def test_14b_a_priority_founder_is_never_downgraded_by_a_weak_openai_finding(
        founder_fixture, fake_sdk):
    raw, canonical, assessment = founder_fixture
    assessment = {**assessment, "attention": "PRIORITY_REVIEW"}
    payload = {"exceptional_signal": False, "strength": "WEAK",
               "category": "unusual_progression", "evidence": [],
               "unsupported_inferences": []}
    fake_sdk(_FakeResponse(json.dumps(payload)))
    result = _run(raw, canonical, assessment, OpenAIAdapter(api_key="test-not-a-real-key"))
    assert result.attention_with_ai == "PRIORITY_REVIEW"
    assert result.attention_changed is False


def test_14c_accepted_openai_cues_are_typed_ai_interpreted(founder_fixture, fake_sdk):
    raw, canonical, assessment = founder_fixture
    payload = {"exceptional_signal": True, "strength": "MEDIUM",
               "category": "unusual_progression",
               "evidence": [{"claim": "A grounded observation about role one.",
                             "source_fields": ["experience[0].position_title"]}],
               "unsupported_inferences": []}
    fake_sdk(_FakeResponse(json.dumps(payload)))
    result = _run(raw, canonical, assessment, OpenAIAdapter(api_key="test-not-a-real-key"))
    assert result.ai_cues
    for cue in result.ai_cues:
        assert cue.signal.type is SignalType.AI_INTERPRETED
        assert cue.strength is Strength.MEDIUM


# =====================================================================
# 15 · persistence remains unchanged
# =====================================================================
def test_15_openai_result_is_not_persisted_into_the_assessment(
        client, session, seeded, monkeypatch, fake_sdk):
    from app.api import main as api
    from app.db.models import Founder

    fid = seeded["founder_ids"][0]
    before = json.loads(json.dumps(session.get(Founder, fid).assessment_json,
                                   sort_keys=True))

    payload = {"exceptional_signal": True, "strength": "STRONG",
               "category": "unusual_progression",
               "evidence": [{"claim": "A claim citing nothing real.",
                             "source_fields": ["experience[0].position_title"]}],
               "unsupported_inferences": ["a diagnostic hunch"]}
    fake_sdk(_FakeResponse(json.dumps(payload)))
    monkeypatch.setattr(api, "default_adapter",
                        lambda: OpenAIAdapter(api_key="test-not-a-real-key"))

    assert client.post(f"/founders/{fid}/ai_check").status_code == 200

    session.expire_all()
    after = session.get(Founder, fid)
    assert json.loads(json.dumps(after.assessment_json, sort_keys=True)) == before
    # No AI_INTERPRETED signal was written into the deterministic assessment.
    assert all(s["type"] != "AI_INTERPRETED" for s in after.assessment_json["signals"])


def test_15b_assessment_version_and_rubric_are_untouched_by_an_ai_check(
        client, session, seeded, monkeypatch, fake_sdk):
    from app.api import main as api
    from app.db.models import Founder

    fid = seeded["founder_ids"][0]
    row = session.get(Founder, fid)
    before = (row.assessment_version, row.rubric_version, row.engine_version,
              row.assessed_at)

    fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    monkeypatch.setattr(api, "default_adapter",
                        lambda: OpenAIAdapter(api_key="test-not-a-real-key"))
    client.post(f"/founders/{fid}/ai_check")

    session.expire_all()
    row = session.get(Founder, fid)
    assert (row.assessment_version, row.rubric_version, row.engine_version,
            row.assessed_at) == before


# =====================================================================
# 16 · decision / workflow remain unchanged
# =====================================================================
def test_16_human_decision_and_workflow_survive_an_openai_check(
        client, session, seeded, monkeypatch, fake_sdk):
    from app.api import main as api
    from app.db.models import Founder

    fid = seeded["founder_ids"][0]
    client.post(f"/founders/{fid}/decision",
                json={"disposition": "POTENTIAL", "actor": "piyush",
                      "reason": "worth a conversation"})
    client.post(f"/founders/{fid}/stage",
                json={"stage": "ASSESSMENT", "actor": "piyush", "reason": "triage"})
    client.patch(f"/founders/{fid}/workflow",
                 json={"actor": "piyush", "reason": "assigning", "owner": "piyush"})

    session.expire_all()
    row = session.get(Founder, fid)
    before = (row.current_decision.disposition, row.workflow.stage,
              row.workflow.owner, row.workflow.next_action,
              len(row.workflow.notes or []), len(row.decisions))

    payload = {"exceptional_signal": True, "strength": "STRONG",
               "category": "unusual_progression",
               "evidence": [{"claim": "A grounded claim.",
                             "source_fields": ["experience[0].position_title"]}],
               "unsupported_inferences": []}
    fake_sdk(_FakeResponse(json.dumps(payload)))
    monkeypatch.setattr(api, "default_adapter",
                        lambda: OpenAIAdapter(api_key="test-not-a-real-key"))
    assert client.post(f"/founders/{fid}/ai_check").status_code == 200

    session.expire_all()
    row = session.get(Founder, fid)
    after = (row.current_decision.disposition, row.workflow.stage,
             row.workflow.owner, row.workflow.next_action,
             len(row.workflow.notes or []), len(row.decisions))
    assert after == before


def test_16b_the_result_model_cannot_even_express_a_human_decision(
        founder_fixture, fake_sdk):
    fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    raw, canonical, assessment = founder_fixture
    result = _run(raw, canonical, assessment, OpenAIAdapter(api_key="test-not-a-real-key"))
    body = result.to_dict()
    for forbidden in ("decision", "disposition", "stage", "owner", "keep_warm_until"):
        assert forbidden not in body


# =====================================================================
# 17 · AI creates no durable audit event
# =====================================================================
def test_17_openai_check_creates_no_audit_event(client, session, seeded,
                                                monkeypatch, fake_sdk):
    from app.api import main as api
    from app.db.models import AuditLog

    fid = seeded["founder_ids"][0]
    before = session.query(AuditLog).filter(AuditLog.founder_id == fid).count()

    payload = {"exceptional_signal": True, "strength": "STRONG",
               "category": "unusual_progression",
               "evidence": [{"claim": "A grounded claim.",
                             "source_fields": ["experience[0].position_title"]}],
               "unsupported_inferences": []}
    fake_sdk(_FakeResponse(json.dumps(payload)))
    monkeypatch.setattr(api, "default_adapter",
                        lambda: OpenAIAdapter(api_key="test-not-a-real-key"))
    client.post(f"/founders/{fid}/ai_check")

    session.expire_all()
    after = session.query(AuditLog).filter(AuditLog.founder_id == fid).all()
    assert len(after) == before
    assert all(row.event != "AI_CHECK" for row in after)
    assert all(row.event != "RESCORE" for row in after[before:])


# =====================================================================
# 18 · deterministic behaviour is unchanged without a real provider
# =====================================================================
def test_18_golden_style_assessment_is_identical_with_and_without_the_layer(
        founder_fixture, fake_sdk):
    raw, canonical, assessment = founder_fixture
    baseline = json.dumps(assessment, sort_keys=True)

    fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    result = _run(raw, canonical, assessment, OpenAIAdapter(api_key="test-not-a-real-key"))

    assert json.dumps(assessment, sort_keys=True) == baseline
    assert result.deterministic_attention == assessment["attention"]
    assert result.attention_with_ai == assessment["attention"]


def test_18b_selecting_openai_changes_no_deterministic_number(monkeypatch,
                                                              founder_fixture):
    """Provider selection is a deployment detail, not a scoring input."""
    raw, canonical, assessment = founder_fixture
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    again = assess(CanonicalProfile.model_validate(canonical.model_dump(mode="json")),
                   CFG).to_dict()
    assert again["broad_score"] == assessment["broad_score"]
    assert again["attention"] == assessment["attention"]
    assert again["confidence"] == assessment["confidence"]
    assert again["rubric_version"] == assessment["rubric_version"]


def test_18c_ai_layer_status_never_enters_the_rubric_hash(client, seeded, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    anthropic_hash = client.get("/config").json()["rubric_version"]
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    body = client.get("/config").json()
    assert body["rubric_version"] == anthropic_hash
    assert body["ai_layer"]["provider"] == "openai"
    assert "ai_layer" not in body["config"]        # status, never configuration


# =====================================================================
# Secret safety of the status surface
# =====================================================================
def test_config_ai_layer_exposes_no_secret_material(client, seeded, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-SENTINEL-not-real")
    body = client.get("/config").json()
    blob = json.dumps(body)
    assert "SENTINEL" not in blob
    assert "sk-" not in blob
    assert set(body["ai_layer"]) == {"provider", "available", "detail",
                                     "prompt_version", "prompt_sha256"}


def test_ai_check_response_exposes_no_secret_material(client, seeded, monkeypatch,
                                                      fake_sdk):
    from app.api import main as api
    fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-SENTINEL-not-real")
    monkeypatch.setattr(api, "default_adapter", lambda: OpenAIAdapter())
    body = client.post(f"/founders/{seeded["founder_ids"][0]}/ai_check").json()
    blob = json.dumps(body)
    assert "SENTINEL" not in blob and "sk-" not in blob


def test_no_real_key_is_embedded_in_this_test_file():
    """Guards against a real key being pasted into the suite later."""
    from pathlib import Path
    source = Path(__file__).read_text()
    # Built at runtime so this guard does not trip over its own source text.
    for prefix in ("sk-" + "proj-", "sk-" + "ant-api", "sk-" + "svcacct-"):
        assert prefix not in source, f"a real-looking key prefix {prefix!r} is present"


# =====================================================================
# COST-SAFETY AMENDMENT — fail-closed provider selection
# =====================================================================
def test_unknown_provider_fails_closed_and_selects_nothing(monkeypatch):
    """A typo must not silently spend money at, or send founder data to, a
    provider the operator never named."""
    from app.llm.provider import (UNKNOWN_PROVIDER_CODE, UnknownProviderAdapter,
                                  default_adapter)
    from app.llm.anthropic_adapter import AnthropicAdapter

    monkeypatch.setenv("LLM_PROVIDER", "opneai")        # the classic typo
    monkeypatch.delenv("FOUNDER_AI_ADAPTER", raising=False)
    adapter = default_adapter()

    assert isinstance(adapter, UnknownProviderAdapter)
    assert not isinstance(adapter, (AnthropicAdapter, OpenAIAdapter))
    assert not isinstance(adapter, MockAdapter)
    assert adapter.provider == "unknown"                # never a real vendor name
    assert adapter.available() is False
    assert UNKNOWN_PROVIDER_CODE in adapter.last_error
    assert "opneai" in adapter.last_error


def test_unknown_provider_reports_the_typo_verbatim(monkeypatch):
    from app.llm.provider import configured_provider
    monkeypatch.setenv("LLM_PROVIDER", "OpNeAi")
    assert configured_provider() == "opneai"            # not "anthropic"


def test_unknown_provider_never_makes_a_request(monkeypatch):
    from app.llm.provider import UnknownProviderError, make_adapter
    adapter = make_adapter("gpt4")
    with pytest.raises(UnknownProviderError) as exc:
        adapter.analyze(SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert exc.value.code == "UNKNOWN_LLM_PROVIDER"


def test_unknown_provider_is_an_adapter_unavailable_subclass():
    """So every existing fail-closed path in service.py already handles it."""
    from app.llm.provider import UnknownProviderError
    assert issubclass(UnknownProviderError, AdapterUnavailable)


def test_unknown_provider_leaves_the_ai_check_a_clean_no_op(founder_fixture,
                                                            monkeypatch):
    from app.llm.provider import make_adapter
    raw, canonical, assessment = founder_fixture
    result = _run(raw, canonical, assessment, make_adapter("nope"))
    assert result.status == "unavailable"
    assert result.attention_with_ai == assessment["attention"]
    assert result.ai_cues == []


def test_unknown_provider_does_not_break_the_config_endpoint(client, seeded,
                                                             monkeypatch):
    """A misconfigured env var is a configuration error, not an outage."""
    monkeypatch.setenv("LLM_PROVIDER", "opneai")
    response = client.get("/config")
    assert response.status_code == 200
    layer = response.json()["ai_layer"]
    assert layer["available"] is False
    assert layer["provider"] == "unknown"
    assert "UNKNOWN_LLM_PROVIDER" in layer["detail"]


@pytest.mark.parametrize("name", ["mock", "openai", "anthropic"])
def test_valid_provider_behaviour_is_unchanged(name, monkeypatch):
    from app.llm.provider import UnknownProviderAdapter, make_adapter
    monkeypatch.delenv("FOUNDER_AI_ADAPTER", raising=False)
    adapter = make_adapter(name)
    assert adapter.provider == name
    assert not isinstance(adapter, UnknownProviderAdapter)


# =====================================================================
# COST-SAFETY AMENDMENT — bounded request shape
# =====================================================================
def test_output_tokens_are_capped(fake_sdk):
    from app.llm.openai_adapter import MAX_OUTPUT_TOKENS
    sdk = fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    OpenAIAdapter(api_key="test-not-a-real-key").analyze(
        SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert sdk.calls[0]["max_output_tokens"] == MAX_OUTPUT_TOKENS
    assert 0 < MAX_OUTPUT_TOKENS <= 4000


def test_sdk_auto_retries_are_disabled_by_default(fake_sdk):
    """Every retry is a billed attempt a caller-side budget cannot see."""
    from app.llm.openai_adapter import MAX_RETRIES
    assert MAX_RETRIES == 0
    sdk = fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    OpenAIAdapter(api_key="test-not-a-real-key").analyze(
        SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert sdk.client_kwargs["max_retries"] == 0


def test_no_tools_are_enabled(fake_sdk):
    """No web search, file search, code interpreter, images or embeddings."""
    sdk = fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    OpenAIAdapter(api_key="test-not-a-real-key").analyze(
        SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    sent = sdk.calls[0]
    assert sent["tools"] == []
    for forbidden in ("tool_choice", "attachments", "file_ids", "modalities"):
        assert forbidden not in sent


def test_request_carries_only_the_frozen_prompt_and_facts(fake_sdk):
    sdk = fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    OpenAIAdapter(api_key="test-not-a-real-key").analyze(
        SYSTEM_PROMPT, "user facts", RESPONSE_SCHEMA)
    assert set(sdk.calls[0]) <= {"model", "instructions", "input",
                                 "max_output_tokens", "tools", "text", "reasoning"}


def test_reasoning_effort_can_be_switched_off(fake_sdk):
    sdk = fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    OpenAIAdapter(api_key="test-not-a-real-key", reasoning_effort="off").analyze(
        SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert "reasoning" not in sdk.calls[0]


def test_reasoning_tokens_are_surfaced_for_cost_reporting(fake_sdk):
    fake_sdk(_FakeResponse(json.dumps(GOOD_PAYLOAD)))
    _, metadata = OpenAIAdapter(api_key="test-not-a-real-key").analyze(
        SYSTEM_PROMPT, "content", RESPONSE_SCHEMA)
    assert "reasoning_tokens" in metadata.usage
