"""Tools internas de listagem e leitura de arquivos."""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from onbot_cli.security.paths import PathGuardError, PathOperation
from onbot_cli.security.permissions import PermissionAction
from onbot_cli.tools.base import ToolContext, ToolOrigin, ToolResult, ToolRisk


class ListFilesTool:
    """Lista arquivos do workspace respeitando exclusoes e PathGuard."""

    name = "list_files"
    description = "Lista arquivos e diretorios dentro do workspace."
    risk_level = ToolRisk.SAFE
    origin = ToolOrigin.INTERNAL
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "recursive": {"type": "boolean"},
            "max_entries": {"type": "integer"},
            "include_hidden": {"type": "boolean"},
        },
        "additionalProperties": False,
    }

    def execute(
        self,
        context: ToolContext,
        input_data: Mapping[str, Any],
    ) -> ToolResult:
        target = str(input_data.get("path") or ".")
        recursive = bool(input_data.get("recursive", True))
        max_entries = _positive_int(input_data.get("max_entries"), default=200)
        include_hidden = bool(input_data.get("include_hidden", False))

        guarded = context.resolve_path(target, operation=PathOperation.READ)
        if not guarded.path.is_dir():
            return ToolResult.fail(
                "Path nao e um diretorio.",
                status="invalid_path",
                metadata={"path": guarded.relative_posix},
            )

        permission = context.authorize_path(
            guarded,
            PermissionAction.FILE_READ,
            detail="listagem de diretorio",
        )
        if permission.denied:
            return ToolResult.fail(
                "Listagem negada por permissao.",
                status="denied",
                metadata={"reason": permission.reason},
            )

        entries: list[dict[str, Any]] = []
        truncated = False
        for path in iter_workspace_paths(
            context.workspace_root,
            context.config,
            base_dir=guarded.path,
            recursive=recursive,
            include_hidden=include_hidden,
            path_guard=context.path_guard,
        ):
            try:
                item = context.resolve_path(path, operation=PathOperation.READ)
            except PathGuardError:
                continue
            if item.path == guarded.path:
                continue
            entries.append(_entry_for(item.path, item.relative))
            if len(entries) >= max_entries:
                truncated = True
                break

        return ToolResult.ok(
            {
                "root": guarded.relative_posix or ".",
                "entries": entries,
                "count": len(entries),
                "truncated": truncated,
            }
        )


class ReadFileTool:
    """Le um arquivo permitido dentro do workspace."""

    name = "read_file"
    description = "Le conteudo textual de um arquivo dentro do workspace."
    risk_level = ToolRisk.SAFE
    origin = ToolOrigin.INTERNAL
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "max_bytes": {"type": "integer"},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def execute(
        self,
        context: ToolContext,
        input_data: Mapping[str, Any],
    ) -> ToolResult:
        guarded = context.resolve_path(
            str(input_data["path"]),
            operation=PathOperation.READ,
        )
        if guarded.path.is_dir():
            return ToolResult.fail(
                "Path e um diretorio.",
                status="invalid_path",
                metadata={"path": guarded.relative_posix},
            )
        if is_excluded(guarded.relative, context.workspace_exclusions):
            return ToolResult.fail(
                "Arquivo excluido pela configuracao do workspace.",
                status="excluded",
                metadata={"path": guarded.relative_posix},
            )

        permission = context.authorize_path(
            guarded,
            PermissionAction.FILE_READ,
            detail="leitura de arquivo",
        )
        if permission.denied:
            return ToolResult.fail(
                "Leitura negada por permissao.",
                status="denied",
                metadata={"reason": permission.reason},
            )

        limit = _positive_int(
            input_data.get("max_bytes"),
            default=context.max_file_size_bytes,
        )
        size = guarded.path.stat().st_size
        if size > limit:
            return ToolResult.fail(
                "Arquivo excede o limite de leitura.",
                status="too_large",
                metadata={
                    "path": guarded.relative_posix,
                    "size": size,
                    "limit": limit,
                },
            )

        data = guarded.path.read_bytes()
        if b"\x00" in data:
            return ToolResult.fail(
                "Arquivo binario nao sera lido como texto.",
                status="binary",
                metadata={"path": guarded.relative_posix},
            )

        return ToolResult.ok(
            {
                "path": guarded.relative_posix,
                "size": size,
                "content": data.decode("utf-8", errors="replace"),
            }
        )


def iter_workspace_paths(
    workspace_root: Path,
    config: Mapping[str, Any],
    *,
    base_dir: Path | None = None,
    recursive: bool = True,
    include_hidden: bool = False,
    path_guard: Any | None = None,
) -> Iterable[Path]:
    """Itera paths do workspace aplicando exclusoes configuradas."""

    root = workspace_root.resolve()
    start = (base_dir or root).resolve()
    exclude_patterns = workspace_exclude_patterns(config)

    def walk(directory: Path) -> Iterable[Path]:
        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name.lower())
        except OSError:
            return

        for child in children:
            try:
                relative = child.resolve(strict=False).relative_to(root)
            except ValueError:
                continue
            if not include_hidden and is_hidden_path(relative):
                continue
            if is_excluded(relative, exclude_patterns):
                continue
            if path_guard is not None:
                try:
                    path_guard.resolve(child, operation=PathOperation.READ)
                except PathGuardError:
                    continue

            yield child
            if recursive and child.is_dir() and not child.is_symlink():
                yield from walk(child)

    yield from walk(start)


def workspace_exclude_patterns(config: Mapping[str, Any]) -> tuple[str, ...]:
    workspace_config = config.get("workspace", {})
    if not isinstance(workspace_config, Mapping):
        return ()
    raw = workspace_config.get("exclude", ())
    if isinstance(raw, list | tuple):
        return tuple(str(item) for item in raw)
    if raw:
        return (str(raw),)
    return ()


def max_file_size_bytes(config: Mapping[str, Any], *, default_kb: int = 256) -> int:
    workspace_config = config.get("workspace", {})
    if not isinstance(workspace_config, Mapping):
        return default_kb * 1024
    try:
        value = int(workspace_config.get("max_file_size_kb", default_kb))
    except (TypeError, ValueError):
        value = default_kb
    return max(value, 1) * 1024


def is_excluded(relative: Path | str, patterns: Iterable[str]) -> bool:
    normalized = _normalize_relative(relative)
    for pattern in patterns:
        normalized_pattern = _normalize_pattern(pattern)
        if not normalized_pattern:
            continue
        if normalized_pattern.endswith("/"):
            directory = normalized_pattern.rstrip("/")
            if normalized == directory or normalized.startswith(f"{directory}/"):
                return True
            continue
        if fnmatch.fnmatchcase(normalized, normalized_pattern):
            return True
        if fnmatch.fnmatchcase(Path(normalized).name, normalized_pattern):
            return True
    return False


def is_hidden_path(relative: Path | str) -> bool:
    parts = relative.parts if isinstance(relative, Path) else Path(relative).parts
    return any(part.startswith(".") for part in parts if part not in {"", "."})


def _entry_for(path: Path, relative: Path) -> dict[str, Any]:
    is_directory = path.is_dir()
    size = None if is_directory else path.stat().st_size
    return {
        "path": relative.as_posix(),
        "type": "directory" if is_directory else "file",
        "size": size,
        "symlink": path.is_symlink(),
    }


def _normalize_pattern(pattern: str) -> str:
    normalized = str(pattern).replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lower()


def _normalize_relative(relative: Path | str) -> str:
    value = relative.as_posix() if isinstance(relative, Path) else str(relative)
    value = value.replace("\\", "/").strip("/")
    while value.startswith("./"):
        value = value[2:]
    return value.lower()


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(parsed, 1)
