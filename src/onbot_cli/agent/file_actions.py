"""Acoes estruturadas de arquivo propostas pelo LLM e aplicadas pelo agente."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from onbot_cli.hooks.models import HookEvent
from onbot_cli.security.approval import ApprovalResult
from onbot_cli.security.paths import PathOperation
from onbot_cli.security.permissions import PermissionAction, PermissionRequest
from onbot_cli.tools import PatchService, ToolContext, ToolRisk


ACTION_TYPES = {
    "create_file",
    "write_file",
    "edit_file",
    "delete_file",
    "move_file",
}


@dataclass(frozen=True, slots=True)
class AgentFileAction:
    """Uma mutacao de arquivo solicitada em formato estruturado."""

    type: str
    path: str | None = None
    content: str | None = None
    source: str | None = None
    destination: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentFileAction":
        action_type = str(data.get("type", "")).strip()
        return cls(
            type=action_type,
            path=_optional_text(data.get("path")),
            content=_optional_text(data.get("content")),
            source=_optional_text(data.get("source", data.get("from"))),
            destination=_optional_text(data.get("destination", data.get("to"))),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AgentActionPlan:
    """Plano estruturado extraido da resposta do LLM."""

    response: str
    actions: tuple[AgentFileAction, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentActionPlan":
        raw_actions = data.get("actions", [])
        if not isinstance(raw_actions, list):
            raw_actions = []
        actions = tuple(
            action
            for item in raw_actions
            if isinstance(item, dict)
            for action in (AgentFileAction.from_dict(item),)
            if action.type in ACTION_TYPES
        )
        response = str(data.get("response") or data.get("message") or "")
        return cls(response=response, actions=actions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "response": self.response,
            "actions": [action.to_dict() for action in self.actions],
        }


@dataclass(frozen=True, slots=True)
class FileActionResult:
    """Resultado de uma acao de arquivo."""

    action: str
    status: str
    target: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FileActionApplyResult:
    """Resultado agregado da aplicacao de acoes reais."""

    applied: bool
    status: str
    results: tuple[FileActionResult, ...]
    summary: str


class StaticApprovalService:
    """ApprovalService minimo para uma decisao ja capturada via pendencia."""

    def __init__(self, *, approved: bool, reason: str) -> None:
        self.approved = approved
        self.reason = reason

    def request_approval(self, evaluation: Any) -> ApprovalResult:
        return ApprovalResult(
            approved=self.approved,
            decision="approved_pending" if self.approved else "denied_pending",
            reason=self.reason,
        )


class FileActionExecutor:
    """Aplica create/edit/delete/move usando PathGuard e PermissionManager."""

    def __init__(self, context: ToolContext) -> None:
        self.context = context

    def preview(self, plan: AgentActionPlan) -> str:
        lines: list[str] = []
        write_changes = _write_changes(plan)
        if write_changes:
            proposal = PatchService(self.context).propose(write_changes)
            if proposal.diff:
                lines.append(proposal.diff)
        for action in plan.actions:
            if action.type == "delete_file" and action.path:
                lines.append(f"delete {action.path}")
            if action.type == "move_file" and action.source and action.destination:
                lines.append(f"move {action.source} -> {action.destination}")
        return "\n".join(lines).strip()

    def apply(
        self,
        plan: AgentActionPlan,
        *,
        approval_service: Any | None = None,
    ) -> FileActionApplyResult:
        approval = approval_service or StaticApprovalService(
            approved=True,
            reason="usuario aprovou interacao pendente",
        )
        results: list[FileActionResult] = []

        write_changes = _write_changes(plan)
        if write_changes:
            patch_result = PatchService(self.context).apply(
                write_changes,
                approval_service=approval,
            )
            if not patch_result.applied:
                return FileActionApplyResult(
                    applied=False,
                    status=patch_result.status,
                    results=tuple(results),
                    summary=patch_result.reason or "Patch negado.",
                )
            results.extend(
                FileActionResult(
                    action="write_file",
                    status=patch_result.status,
                    target=path,
                    detail="conteudo gravado",
                )
                for path in patch_result.changed_paths
            )

        for action in plan.actions:
            if action.type == "delete_file":
                results.append(self._delete(action, approval))
            elif action.type == "move_file":
                results.append(self._move(action, approval))

        failed = [item for item in results if item.status not in {"applied", "moved", "deleted"}]
        if failed:
            return FileActionApplyResult(
                applied=False,
                status="partial" if len(failed) < len(results) else "failed",
                results=tuple(results),
                summary="Uma ou mais acoes de arquivo falharam.",
            )
        return FileActionApplyResult(
            applied=True,
            status="applied",
            results=tuple(results),
            summary=_summary_for(results),
        )

    def _delete(
        self,
        action: AgentFileAction,
        approval_service: Any,
    ) -> FileActionResult:
        if not action.path:
            return FileActionResult("delete_file", "invalid", "", "path ausente")
        guarded = self.context.resolve_path(
            action.path,
            operation=PathOperation.DELETE,
            must_exist=True,
        )
        if not guarded.path.is_file():
            return FileActionResult(
                "delete_file",
                "invalid",
                guarded.relative_posix,
                "apenas arquivos podem ser excluidos por esta acao",
            )
        permission = self.context.permission_manager.authorize(
            PermissionRequest(
                action=PermissionAction.PATCH,
                target=guarded.relative_posix,
                risk=ToolRisk.DANGEROUS.value,
                protected=guarded.protected,
                mutates=True,
                detail=f"delete {guarded.relative_posix}",
            ),
            approval_service=approval_service,
        )
        if permission.denied:
            return FileActionResult(
                "delete_file",
                "denied",
                guarded.relative_posix,
                permission.reason,
            )
        guarded.path.unlink()
        self.context.dispatch_hook(
            HookEvent.FILE_CHANGED,
            {"path": guarded.relative_posix, "deleted": True},
        )
        self.context.record_audit(
            "file_deleted",
            {"path": guarded.relative_posix},
        )
        return FileActionResult("delete_file", "deleted", guarded.relative_posix)

    def _move(
        self,
        action: AgentFileAction,
        approval_service: Any,
    ) -> FileActionResult:
        if not action.source or not action.destination:
            return FileActionResult("move_file", "invalid", "", "source/destination ausentes")
        source = self.context.resolve_path(
            action.source,
            operation=PathOperation.READ,
            must_exist=True,
        )
        destination = self.context.resolve_path(
            action.destination,
            operation=PathOperation.WRITE,
            must_exist=False,
        )
        if not source.path.is_file():
            return FileActionResult(
                "move_file",
                "invalid",
                source.relative_posix,
                "apenas arquivos podem ser movidos por esta acao",
            )
        if destination.path.exists():
            return FileActionResult(
                "move_file",
                "invalid",
                destination.relative_posix,
                "destino ja existe",
            )
        permission = self.context.permission_manager.authorize(
            PermissionRequest(
                action=PermissionAction.PATCH,
                target=f"{source.relative_posix} -> {destination.relative_posix}",
                risk=ToolRisk.CAUTION.value,
                protected=source.protected or destination.protected,
                mutates=True,
                detail=f"move {source.relative_posix} -> {destination.relative_posix}",
            ),
            approval_service=approval_service,
        )
        if permission.denied:
            return FileActionResult(
                "move_file",
                "denied",
                source.relative_posix,
                permission.reason,
            )
        destination.path.parent.mkdir(parents=True, exist_ok=True)
        source.path.replace(destination.path)
        self.context.dispatch_hook(
            HookEvent.FILE_CHANGED,
            {
                "source": source.relative_posix,
                "destination": destination.relative_posix,
                "moved": True,
            },
        )
        self.context.record_audit(
            "file_moved",
            {
                "source": source.relative_posix,
                "destination": destination.relative_posix,
            },
        )
        return FileActionResult(
            "move_file",
            "moved",
            f"{source.relative_posix} -> {destination.relative_posix}",
        )


def parse_action_plan(content: str) -> AgentActionPlan | None:
    """Extrai plano de acoes de blocos JSON conhecidos."""

    for candidate in _json_candidates(content):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("actions"), list):
            plan = AgentActionPlan.from_dict(data)
            if plan.actions:
                response = plan.response or _remove_candidate(content, candidate).strip()
                return AgentActionPlan(response=response, actions=plan.actions)
    return None


def _json_candidates(content: str) -> list[str]:
    candidates: list[str] = []
    candidates.extend(
        match.group(1).strip()
        for match in re.finditer(
            r"<onbot-actions>\s*(.*?)\s*</onbot-actions>",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
    )
    candidates.extend(
        match.group(1).strip()
        for match in re.finditer(
            r"```(?:json)?\s*(.*?)\s*```",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
    )
    stripped = content.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        candidates.append(stripped)
    return candidates


def _remove_candidate(content: str, candidate: str) -> str:
    return content.replace(candidate, "")


def _write_changes(plan: AgentActionPlan) -> dict[str, str]:
    changes: dict[str, str] = {}
    for action in plan.actions:
        if action.type not in {"create_file", "write_file", "edit_file"}:
            continue
        if action.path is None or action.content is None:
            continue
        changes[action.path] = action.content
    return changes


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _summary_for(results: list[FileActionResult]) -> str:
    if not results:
        return "Nenhuma alteracao de arquivo foi aplicada."
    lines = ["Alteracoes aplicadas:"]
    for result in results:
        lines.append(f"- {result.action}: {result.target} ({result.status})")
    return "\n".join(lines)
