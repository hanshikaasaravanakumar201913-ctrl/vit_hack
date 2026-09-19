"""ATLAS Stage 1 — AI Conversational Intelligence Layer.

Provides multi-turn conversational interface, intent detection,
provider abstraction (OpenAI-compatible + Deterministic Clinical Fallback),
evidence-grounded explanation synthesis, and study graph orchestration.
"""

from stage1.ai.provider import AIProvider, get_ai_provider
from stage1.ai.context import ConversationContext, ConversationStore
from stage1.ai.orchestrator import AtlasConversationalOrchestrator

__all__ = [
    "AIProvider",
    "get_ai_provider",
    "ConversationContext",
    "ConversationStore",
    "AtlasConversationalOrchestrator",
]
