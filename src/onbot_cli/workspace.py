"""Resolucao do workspace atual."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from onbot_cli.errors import WorkspaceError
from onbot_cli.models import Workspace


WORKSPACE_DIR_NAME = ".onbot-cli"
WORKSPACE_SUBDIRS = (
    "sessions",
    "history",
    "logs",
    "cache",
    "tools",
    "hooks",
    "commands",
)


def resolve_workspace(path: Path | str | None = None) -> Workspace:
    """Resolve e valida o diretorio usado como workspace."""

    candidate = Path.cwd() if path is None else Path(path)

    try:
        resolved = candidate.expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        raise WorkspaceError(
            "Workspace nao encontrado.",
            hint=f"Verifique se o caminho existe: {candidate}",
        ) from exc

    if not resolved.is_dir():
        raise WorkspaceError(
            "Workspace invalido.",
            hint=f"O caminho precisa ser um diretorio: {resolved}",
        )

    return Workspace(root=resolved)


@dataclass(frozen=True, slots=True)
class WorkspaceLayout:
    """Caminhos padrao da persistencia local do workspace."""

    root: Path
    onbot_dir: Path
    config_file: Path
    sessions_dir: Path
    history_dir: Path
    logs_dir: Path
    cache_dir: Path
    tools_dir: Path
    hooks_dir: Path
    commands_dir: Path

    @classmethod
    def from_workspace(cls, workspace: Workspace) -> "WorkspaceLayout":
        onbot_dir = workspace.root / WORKSPACE_DIR_NAME
        return cls(
            root=workspace.root,
            onbot_dir=onbot_dir,
            config_file=onbot_dir / "config.yaml",
            sessions_dir=onbot_dir / "sessions",
            history_dir=onbot_dir / "history",
            logs_dir=onbot_dir / "logs",
            cache_dir=onbot_dir / "cache",
            tools_dir=onbot_dir / "tools",
            hooks_dir=onbot_dir / "hooks",
            commands_dir=onbot_dir / "commands",
        )

    @property
    def directories(self) -> tuple[Path, ...]:
        return (
            self.onbot_dir,
            self.sessions_dir,
            self.history_dir,
            self.logs_dir,
            self.cache_dir,
            self.tools_dir,
            self.hooks_dir,
            self.commands_dir,
        )


@dataclass(frozen=True, slots=True)
class WorkspaceInitResult:
    """Resultado da criacao idempotente do workspace local."""

    workspace: Workspace
    layout: WorkspaceLayout
    created_directories: tuple[Path, ...]


class WorkspaceManager:
    """Resolve o workspace e materializa a arvore `.onbot-cli`."""

    def __init__(self, start_path: Path | str | None = None) -> None:
        self.workspace = resolve_workspace(start_path)
        self.layout = WorkspaceLayout.from_workspace(self.workspace)

    def ensure_workspace(self) -> WorkspaceInitResult:
        created: list[Path] = []

        for directory in self.layout.directories:
            if not directory.exists():
                created.append(directory)
            directory.mkdir(parents=True, exist_ok=True)
            if not directory.is_dir():
                raise WorkspaceError(
                    "Workspace local invalido.",
                    hint=f"O caminho precisa ser um diretorio: {directory}",
                )

        return WorkspaceInitResult(
            workspace=self.workspace,
            layout=self.layout,
            created_directories=tuple(created),
        )

    def expected_directories(self) -> Iterable[Path]:
        return self.layout.directories
