"""Contratos compartilhados por tools internas e locais."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from onbot_cli.hooks.models import HookDispatcher, HookEvent, NoopHookDispatcher
from onbot_cli.models import Workspace
from onbot_cli.security.paths import GuardedPath, PathGuard, PathOperation
from onbot_cli.security.permissions import (
    PermissionAction,
    PermissionEvaluation,
    PermissionManager,
    PermissionRequest,
)
from onbot_cli.storage.logs import AuditLogger
from onbot_cli.storage.models import ToolCallRecord
from onbot_cli.storage.sessions import SessionStore
from onbot_cli.workspace import WorkspaceLayout


class ToolRisk(StrEnum):
    """Niveis de risco exibidos no catalogo de tools."""

    SAFE = "SAFE"
    CAUTION = "CAUTION"
    DANGEROUS = "DANGEROUS"
    BLOCKED = "BLOCKED"


class ToolOrigin(StrEnum):
    """Origem de uma tool registrada."""

    INTERNAL = "internal"
    LOCAL = "local"


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Resultado padronizado de uma invocacao de tool."""

    success: bool = True
    output: Any | None = None
    error: str | None = None
    status: str = "ok"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(
        cls,
        output: Any | None = None,
        *,
        status: str = "ok",
        metadata: Mapping[str, Any] | None = None,
    ) -> "ToolResult":
        return cls(
            success=True,
            output=output,
            status=status,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def fail(
        cls,
        error: str,
        *,
        status: str = "error",
        output: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "ToolResult":
        return cls(
            success=False,
            output=output,
            error=error,
            status=status,
            metadata=dict(metadata or {}),
        )


class Tool(Protocol):
    """Contrato minimo de uma tool executavel pelo agente."""

    name: str
    description: str
    input_schema: Mapping[str, Any]
    risk_level: ToolRisk | str
    origin: ToolOrigin | str

    def execute(
        self,
        context: "ToolContext",
        input_data: Mapping[str, Any],
    ) -> ToolResult:
        """Executa a tool com input validado pelo registry."""


@dataclass(slots=True)
class ToolContext:
    """Dependencias seguras oferecidas para tools internas."""

    workspace: Workspace
    layout: WorkspaceLayout
    config: Mapping[str, Any]
    path_guard: PathGuard
    permission_manager: PermissionManager
    audit_logger: AuditLogger | None = None
    session_store: SessionStore | None = None
    session_id: str | None = None
    approval_service: Any | None = None
    hook_dispatcher: HookDispatcher = field(default_factory=NoopHookDispatcher)

    @property
    def workspace_root(self) -> Path:
        return self.workspace.root

    @property
    def max_file_size_bytes(self) -> int:
        workspace_config = _mapping_section(self.config, "workspace")
        raw_value = workspace_config.get("max_file_size_kb", 256)
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            value = 256
        return max(value, 1) * 1024

    @property
    def workspace_exclusions(self) -> tuple[str, ...]:
        workspace_config = _mapping_section(self.config, "workspace")
        value = workspace_config.get("exclude", ())
        if isinstance(value, list | tuple):
            return tuple(str(item) for item in value)
        if value:
            return (str(value),)
        return ()

    def resolve_path(
        self,
        path: Path | str,
        *,
        operation: PathOperation | str = PathOperation.READ,
        must_exist: bool | None = None,
    ) -> GuardedPath:
        return self.path_guard.resolve(
            path,
            operation=operation,
            must_exist=must_exist,
        )

    def authorize(
        self,
        request: PermissionRequest,
    ) -> PermissionEvaluation:
        return self.permission_manager.authorize(
            request,
            approval_service=self.approval_service,
        )

    def authorize_path(
        self,
        guarded_path: GuardedPath,
        action: PermissionAction,
        *,
        risk: str = ToolRisk.SAFE.value,
        mutates: bool = False,
        detail: str | None = None,
    ) -> PermissionEvaluation:
        return self.authorize(
            PermissionRequest(
                action=action,
                target=guarded_path.relative_posix,
                risk=risk,
                protected=guarded_path.protected,
                mutates=mutates,
                detail=detail,
            )
        )

    def dispatch_hook(
        self,
        event: HookEvent | str,
        payload: dict[str, Any],
    ):
        return self.hook_dispatcher.dispatch(
            event,
            payload,
            session_id=self.session_id,
        )

    def record_audit(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.audit_logger is not None:
            self.audit_logger.record_event(
                event_type,
                payload,
                session_id=self.session_id,
            )

    def record_tool_call(
        self,
        *,
        name: str,
        input_data: Mapping[str, Any],
        result: ToolResult,
    ) -> None:
        self.record_audit(
            "tool_call",
            {
                "name": name,
                "status": result.status,
                "success": result.success,
                "input": dict(input_data),
                "output": result.output,
                "error": result.error,
                "metadata": dict(result.metadata),
            },
        )
        if self.session_store is not None and self.session_id:
            self.session_store.append_tool_call(
                self.session_id,
                ToolCallRecord(
                    name=name,
                    status=result.status,
                    input=dict(input_data),
                    output=result.output if result.success else result.error,
                ),
            )


def _mapping_section(config: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = config.get(name, {})
    return value if isinstance(value, Mapping) else {}
