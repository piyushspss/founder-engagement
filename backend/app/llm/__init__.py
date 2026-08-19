"""Optional, raise-only LLM evidence layer (PLAN A11c, RUNBOOK CP10).

The deterministic assessment is the source of truth. Nothing in this package
can modify it, and nothing here can lower a priority.
"""

from app.llm.adapter import (AdapterError, AdapterMalformed, AdapterUnavailable,
                             LLMAdapter)
from app.llm.mock import MockAdapter, no_finding_adapter
from app.llm.provider import (PROVIDERS, configured_provider, default_adapter,
                              make_adapter)
from app.llm.service import run_ai_check
from app.llm.types import AICheckResult, AICue, DiscardedItem, RawFinding

__all__ = ["LLMAdapter", "AdapterError", "AdapterUnavailable", "AdapterMalformed",
           "MockAdapter", "no_finding_adapter", "run_ai_check", "AICheckResult",
           "AICue", "DiscardedItem", "RawFinding", "PROVIDERS",
           "configured_provider", "default_adapter", "make_adapter"]
