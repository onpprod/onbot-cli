"""Contratos e modelos para clientes LLM."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from onbot_cli.errors import ApplicationError


class LLMError(ApplicationError):
    """Erro normalizado da camada LLM."""

    code = "llm_error"


class LLMConfigurationError(LLMError):
    """Configuracao incompleta ou invalida para chamar o provedor."""

    code = "llm_configuration_error"


class LLMTransportError(LLMError):
    """Falha de rede, HTTP ou serializacao ao chamar o provedor."""

    code = "llm_transport_error"


class LLMResponseError(LLMError):
    """Resposta inesperada ou erro retornado pelo provedor."""

    code = "llm_response_error"


class LLMCancelledError(LLMError):
    """Chamada ao provedor cancelada pelo usuario ou controlador."""

    code = "llm_cancelled"


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """Payload independente de provedor usado pelo AgentController."""

    messages: Sequence[Mapping[str, Any]]
    model: str | None = None
    temperature: float | None = None
    generation_params: Mapping[str, Any] = field(default_factory=dict)
    stream: bool = True


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Resposta completa de uma chamada sem streaming."""

    content: str
    model: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class LLMStreamChunk:
    """Chunk incremental de texto normalizado."""

    content: str = ""
    model: str | None = None
    finish_reason: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @property
    def done(self) -> bool:
        return self.finish_reason is not None


class LLMClient(Protocol):
    """Interface unica para provedores OpenAI-compatible."""

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Executa uma chamada e retorna o texto completo."""

    def stream(self, request: LLMRequest) -> Iterable[LLMStreamChunk]:
        """Executa uma chamada em streaming e produz chunks incrementais."""
