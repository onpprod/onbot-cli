"""Servico de aprovacao explicita do usuario."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from onbot_cli.security.permissions import PermissionEvaluation
from onbot_cli.storage.logs import AuditLogger


class ApprovalScope(StrEnum):
    """Escopo inicial de uma aprovacao."""

    ONCE = "once"
    SESSION = "session"


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    """Decisao capturada do usuario."""

    approved: bool
    decision: str
    scope: ApprovalScope = ApprovalScope.ONCE
    reason: str | None = None


class ApprovalService:
    """Renderiza o pedido de aprovacao e captura uma decisao explicita."""

    def __init__(
        self,
        *,
        renderer: Any | None = None,
        input_provider: Callable[[str], str] | None = None,
        audit_logger: AuditLogger | None = None,
        session_id: str | None = None,
    ) -> None:
        self.renderer = renderer
        self.input_provider = input_provider or input
        self.audit_logger = audit_logger
        self.session_id = session_id

    def request_approval(
        self,
        evaluation: PermissionEvaluation,
    ) -> ApprovalResult:
        request = evaluation.request
        if self.renderer is not None:
            self.renderer.approval_prompt(
                action=str(request.action),
                target=request.target,
                risk=str(request.risk),
                detail=request.detail or evaluation.reason,
            )

        try:
            raw_decision = self.input_provider(
                "Digite 'yes' para permitir uma vez, 'always' para permitir "
                "na sessao, ou 'no' para negar: "
            )
        except (EOFError, KeyboardInterrupt):
            return self._record(
                evaluation,
                ApprovalResult(
                    approved=False,
                    decision="interrupted",
                    reason="aprovacao interrompida",
                ),
            )

        normalized = raw_decision.strip().lower()
        if normalized in {"yes", "y", "sim", "s", "allow", "permitir"}:
            return self._record(
                evaluation,
                ApprovalResult(
                    approved=True,
                    decision="approved",
                    reason="usuario aprovou",
                ),
            )

        if normalized in {"always", "session", "sessao", "sempre"}:
            return self._record(
                evaluation,
                ApprovalResult(
                    approved=True,
                    decision="approved_session",
                    scope=ApprovalScope.SESSION,
                    reason="usuario aprovou para a sessao",
                ),
            )

        return self._record(
            evaluation,
            ApprovalResult(
                approved=False,
                decision="denied",
                reason="usuario negou ou nao confirmou explicitamente",
            ),
        )

    def _record(
        self,
        evaluation: PermissionEvaluation,
        result: ApprovalResult,
    ) -> ApprovalResult:
        if self.audit_logger is not None:
            self.audit_logger.record_event(
                "approval_decision",
                {
                    "action": str(evaluation.request.action),
                    "target": evaluation.request.target,
                    "risk": evaluation.request.risk,
                    "decision": result.decision,
                    "approved": result.approved,
                    "scope": result.scope.value,
                    "reason": result.reason,
                },
                session_id=self.session_id,
            )
        return result
