"""Modelos compartilhados pela fundacao do onbot-cli."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


def _empty_metadata() -> Mapping[str, Any]:
    return MappingProxyType({})


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Resultado padronizado para comandos locais futuros."""

    command: str
    cwd: Path
    exit_code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True, slots=True)
class Workspace:
    """Representa o diretorio tratado como workspace da sessao."""

    root: Path

    @property
    def name(self) -> str:
        return self.root.name


@dataclass(frozen=True, slots=True)
class ApplicationContext:
    """Contexto minimo compartilhado entre CLI e servicos."""

    workspace: Workspace
    metadata: Mapping[str, Any] = field(default_factory=_empty_metadata)
