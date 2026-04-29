"""Tool interna de busca textual no workspace."""

from __future__ import annotations

import fnmatch
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from onbot_cli.security.paths import PathGuardError, PathOperation
from onbot_cli.security.permissions import PermissionAction
from onbot_cli.tools.base import ToolContext, ToolOrigin, ToolResult, ToolRisk
from onbot_cli.tools.filesystem import iter_workspace_paths


class SearchTextTool:
    """Busca texto em arquivos do workspace respeitando filtros seguros."""

    name = "search_text"
    description = "Busca ocorrencias textuais em arquivos do workspace."
    risk_level = ToolRisk.SAFE
    origin = ToolOrigin.INTERNAL
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "path": {"type": "string"},
            "file_pattern": {"type": "string"},
            "case_sensitive": {"type": "boolean"},
            "max_matches": {"type": "integer"},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def execute(
        self,
        context: ToolContext,
        input_data: Mapping[str, Any],
    ) -> ToolResult:
        query = str(input_data["query"])
        if not query:
            return ToolResult.fail("Busca vazia.", status="invalid_input")

        base_path = str(input_data.get("path") or ".")
        file_pattern = str(input_data.get("file_pattern") or "*")
        case_sensitive = bool(input_data.get("case_sensitive", False))
        max_matches = _positive_int(input_data.get("max_matches"), default=100)

        guarded_base = context.resolve_path(base_path, operation=PathOperation.READ)
        if not guarded_base.path.is_dir():
            return ToolResult.fail(
                "Path de busca nao e um diretorio.",
                status="invalid_path",
                metadata={"path": guarded_base.relative_posix},
            )

        base_permission = context.authorize_path(
            guarded_base,
            PermissionAction.FILE_READ,
            detail="busca textual",
        )
        if base_permission.denied:
            return ToolResult.fail(
                "Busca negada por permissao.",
                status="denied",
                metadata={"reason": base_permission.reason},
            )

        needle = query if case_sensitive else query.lower()
        matches: list[dict[str, Any]] = []
        skipped = 0
        truncated = False

        for path in iter_workspace_paths(
            context.workspace_root,
            context.config,
            base_dir=guarded_base.path,
            recursive=True,
            include_hidden=False,
            path_guard=context.path_guard,
        ):
            if not path.is_file():
                continue
            try:
                guarded = context.resolve_path(path, operation=PathOperation.READ)
            except PathGuardError:
                skipped += 1
                continue
            if not _matches_file_pattern(guarded.relative, file_pattern):
                continue
            if guarded.path.stat().st_size > context.max_file_size_bytes:
                skipped += 1
                continue
            permission = context.authorize_path(
                guarded,
                PermissionAction.FILE_READ,
                detail="busca textual em arquivo",
            )
            if permission.denied:
                skipped += 1
                continue

            text = _read_text(guarded.path)
            if text is None:
                skipped += 1
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                haystack = line if case_sensitive else line.lower()
                if needle not in haystack:
                    continue
                matches.append(
                    {
                        "path": guarded.relative_posix,
                        "line": line_number,
                        "text": line,
                    }
                )
                if len(matches) >= max_matches:
                    truncated = True
                    break
            if truncated:
                break

        return ToolResult.ok(
            {
                "query": query,
                "matches": matches,
                "count": len(matches),
                "truncated": truncated,
                "skipped": skipped,
            }
        )


def _matches_file_pattern(relative: Path, pattern: str) -> bool:
    normalized = relative.as_posix()
    return fnmatch.fnmatchcase(normalized, pattern) or fnmatch.fnmatchcase(
        relative.name,
        pattern,
    )


def _read_text(path: Path) -> str | None:
    data = path.read_bytes()
    if b"\x00" in data:
        return None
    return data.decode("utf-8", errors="replace")


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(parsed, 1)
