"""Contratos iniciais para pontos de hook do ciclo agentico."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class HookEvent(StrEnum):
    """Eventos suportados como interface desde a etapa de tools."""

    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    FILE_CHANGED = "file_changed"


@dataclass(frozen=True, slots=True)
class HookResult:
    """Resultado normalizado de um hook ou dispatcher de hooks."""

    allowed: bool = True
    status: str = "skipped"
    output: Any | None = None
    reason: str | None = None


class HookDispatcher(Protocol):
    """Interface minima que o Hook Manager real implementara depois."""

    def dispatch(
        self,
        event: HookEvent | str,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> HookResult:
        """Executa hooks configurados para um evento."""


@dataclass(frozen=True, slots=True)
class NoopHookDispatcher:
    """Dispatcher padrao: preserva o contrato sem executar codigo do usuario."""

    metadata: dict[str, Any] = field(default_factory=dict)

    def dispatch(
        self,
        event: HookEvent | str,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> HookResult:
        return HookResult(
            allowed=True,
            status="skipped",
            output={
                "event": str(event),
                "session_id": session_id,
                "metadata": self.metadata,
            },
        )
