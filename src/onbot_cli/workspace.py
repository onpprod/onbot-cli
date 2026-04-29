"""Resolucao do workspace atual."""

from __future__ import annotations

from pathlib import Path

from onbot_cli.errors import WorkspaceError
from onbot_cli.models import Workspace


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
