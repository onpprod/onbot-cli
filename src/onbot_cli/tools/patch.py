"""Servico de diff e aplicacao controlada de patches."""

from __future__ import annotations

import difflib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from onbot_cli.hooks.models import HookEvent
from onbot_cli.security.paths import GuardedPath, PathOperation
from onbot_cli.security.permissions import PermissionAction, PermissionRequest
from onbot_cli.tools.base import ToolContext, ToolRisk


@dataclass(frozen=True, slots=True)
class FilePatch:
    """Alteracao completa de conteudo para um arquivo."""

    path: str
    guarded_path: GuardedPath
    old_content: str
    new_content: str
    exists: bool


@dataclass(frozen=True, slots=True)
class PatchProposal:
    """Diff gerado antes da aplicacao."""

    patches: tuple[FilePatch, ...]
    diff: str


@dataclass(frozen=True, slots=True)
class PatchApplyResult:
    """Resultado da aplicacao de um conjunto de patches."""

    applied: bool
    status: str
    proposal: PatchProposal
    changed_paths: tuple[str, ...] = ()
    reason: str | None = None


class PatchService:
    """Gera diff, valida paths, aplica alteracoes e registra auditoria."""

    def __init__(self, context: ToolContext) -> None:
        self.context = context

    def propose(self, changes: Mapping[str, str]) -> PatchProposal:
        patches: list[FilePatch] = []
        diff_chunks: list[str] = []

        for relative_path, new_content in changes.items():
            guarded = self.context.resolve_path(
                relative_path,
                operation=PathOperation.WRITE,
                must_exist=False,
            )
            exists = guarded.path.exists()
            old_content = (
                guarded.path.read_text(encoding="utf-8", errors="replace")
                if exists and guarded.path.is_file()
                else ""
            )
            patch = FilePatch(
                path=guarded.relative_posix,
                guarded_path=guarded,
                old_content=old_content,
                new_content=str(new_content),
                exists=exists,
            )
            patches.append(patch)
            diff_chunks.extend(_diff_for_patch(patch))

        return PatchProposal(
            patches=tuple(patches),
            diff="\n".join(diff_chunks),
        )

    def apply(
        self,
        changes: Mapping[str, str],
        *,
        approval_service: Any | None = None,
    ) -> PatchApplyResult:
        proposal = self.propose(changes)
        if not proposal.patches:
            return PatchApplyResult(
                applied=True,
                status="noop",
                proposal=proposal,
            )

        for patch in proposal.patches:
            permission = self.context.permission_manager.authorize(
                PermissionRequest(
                    action=PermissionAction.PATCH,
                    target=patch.path,
                    risk=ToolRisk.CAUTION.value,
                    protected=patch.guarded_path.protected,
                    mutates=True,
                    detail=proposal.diff,
                ),
                approval_service=approval_service or self.context.approval_service,
            )
            if permission.denied:
                result = PatchApplyResult(
                    applied=False,
                    status="denied",
                    proposal=proposal,
                    reason=permission.reason,
                )
                self.context.record_audit(
                    "patch_denied",
                    {
                        "paths": [item.path for item in proposal.patches],
                        "reason": permission.reason,
                    },
                )
                return result

        changed_paths: list[str] = []
        for patch in proposal.patches:
            patch.guarded_path.path.parent.mkdir(parents=True, exist_ok=True)
            _write_text_atomic(patch.guarded_path.path, patch.new_content)
            changed_paths.append(patch.path)
            self.context.dispatch_hook(
                HookEvent.FILE_CHANGED,
                {
                    "path": patch.path,
                    "created": not patch.exists,
                    "diff": "\n".join(_diff_for_patch(patch)),
                },
            )

        self.context.record_audit(
            "patch_applied",
            {
                "paths": changed_paths,
                "diff": proposal.diff,
            },
        )
        return PatchApplyResult(
            applied=True,
            status="applied",
            proposal=proposal,
            changed_paths=tuple(changed_paths),
        )


def _diff_for_patch(patch: FilePatch) -> list[str]:
    old_lines = patch.old_content.splitlines(keepends=True)
    new_lines = patch.new_content.splitlines(keepends=True)
    if patch.new_content and not patch.new_content.endswith(("\n", "\r")):
        new_lines[-1] = f"{new_lines[-1]}\n"
    if patch.old_content and not patch.old_content.endswith(("\n", "\r")):
        old_lines[-1] = f"{old_lines[-1]}\n"
    return list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{patch.path}" if patch.exists else "/dev/null",
            tofile=f"b/{patch.path}",
            lineterm="",
        )
    )


def _write_text_atomic(path: Path, content: str) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
