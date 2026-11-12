"""
Multi-provider LLM adapter and citation-grounded RAG explainer for ASCI Platform.
Provides tool-isolated Stage A event extraction and verified executive briefings
over immutable PipelineState with deterministic offline fallbacks.
"""

from asci.llm.client import (
    LLMCompletionResult,
    LLMConfig,
    MultiProviderLLMClient,
    load_local_dotenv,
)
from asci.llm.explainer import PlanBriefingGenerator, verify_briefing_citations
from asci.llm.stage_a_llm import LLMExtractorBackend

__all__ = [
    "LLMCompletionResult",
    "LLMConfig",
    "LLMExtractorBackend",
    "MultiProviderLLMClient",
    "PlanBriefingGenerator",
    "load_local_dotenv",
    "verify_briefing_citations",
]

