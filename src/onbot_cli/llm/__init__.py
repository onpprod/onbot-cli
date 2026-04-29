"""Fronteira de clientes LLM OpenAI-compatible."""

from onbot_cli.llm.client import (
    LLMCancelledError,
    LLMClient,
    LLMConfigurationError,
    LLMError,
    LLMRequest,
    LLMResponse,
    LLMResponseError,
    LLMStreamChunk,
    LLMTransportError,
)
from onbot_cli.llm.openai_compatible import (
    OpenAICompatibleClient,
    OpenAICompatibleConfig,
)

__all__ = [
    "LLMCancelledError",
    "LLMClient",
    "LLMConfigurationError",
    "LLMError",
    "LLMRequest",
    "LLMResponse",
    "LLMResponseError",
    "LLMStreamChunk",
    "LLMTransportError",
    "OpenAICompatibleClient",
    "OpenAICompatibleConfig",
]
