"""Validacao de paths usados por tools internas."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Iterable

from onbot_cli.errors import ApplicationError


DEFAULT_PROTECTED_PATHS = (
    ".git/",
    ".onbot-cli/config.yaml",
    ".onbot-cli/logs/",
    ".idea/",
    ".vscode/",
    ".env",
    "*.pem",
    "*.key",
)


class PathOperation(StrEnum):
    """Operacoes de filesystem avaliadas pelo PathGuard."""

    READ = "read"
    WRITE = "write"
    CREATE = "create"
    DELETE = "delete"


class PathGuardError(ApplicationError):
    """Erro de validacao de path dentro do sandbox logico."""

    code = "path_guard_error"


@dataclass(frozen=True, slots=True)
class GuardedPath:
    """Resultado de resolucao e classificacao de um path."""

    original: str
    path: Path
    relative: Path
    protected: bool = False
    protected_pattern: str | None = None

    @property
    def relative_posix(self) -> str:
        return self.relative.as_posix()


class PathGuard:
    """Resolve paths e impede saida do workspace para tools internas."""

    def __init__(
        self,
        workspace_root: Path | str,
        *,
        protected_paths: Iterable[str] | None = None,
    ) -> None:
        try:
            self.workspace_root = Path(workspace_root).expanduser().resolve(
                strict=True
            )
        except FileNotFoundError as exc:
            raise PathGuardError(
                "Workspace nao encontrado.",
                hint=f"Verifique o caminho: {workspace_root}",
            ) from exc

        if not self.workspace_root.is_dir():
            raise PathGuardError(
                "Workspace invalido.",
                hint=f"O caminho precisa ser um diretorio: {self.workspace_root}",
            )

        self.protected_paths = tuple(protected_paths or DEFAULT_PROTECTED_PATHS)

    def resolve(
        self,
        path: Path | str,
        *,
        operation: PathOperation | str = PathOperation.READ,
        must_exist: bool | None = None,
    ) -> GuardedPath:
        """Resolve um path, nega traversal e garante pertencimento ao workspace."""

        raw = str(path)
        candidate = Path(path).expanduser()
        if _has_traversal(candidate):
            raise PathGuardError(
                "Traversal de path negado.",
                hint=f"Use um caminho sem '..': {raw}",
            )

        target = candidate if candidate.is_absolute() else self.workspace_root / candidate
        path_operation = PathOperation(str(operation))
        effective_must_exist = must_exist
        if effective_must_exist is None:
            effective_must_exist = path_operation == PathOperation.READ

        resolved = self._resolve_target(target, must_exist=effective_must_exist)
        relative = self._relative_to_workspace(resolved)
        protected_pattern = self.match_protected(relative)

        return GuardedPath(
            original=raw,
            path=resolved,
            relative=relative,
            protected=protected_pattern is not None,
            protected_pattern=protected_pattern,
        )

    def assert_unprotected(self, guarded_path: GuardedPath) -> None:
        """Nega explicitamente paths classificados como protegidos."""

        if not guarded_path.protected:
            return
        raise PathGuardError(
            "Path protegido.",
            hint=(
                f"O path '{guarded_path.relative_posix}' corresponde a "
                f"'{guarded_path.protected_pattern}'."
            ),
        )

    def match_protected(self, path: Path | str) -> str | None:
        """Retorna o padrao protegido correspondente, quando houver."""

        relative = _normalize_relative(path)
        for pattern in self.protected_paths:
            normalized_pattern = _normalize_pattern(pattern)
            if _matches_pattern(relative, normalized_pattern):
                return pattern
        return None

    def _resolve_target(self, target: Path, *, must_exist: bool) -> Path:
        if must_exist:
            try:
                return target.resolve(strict=True)
            except FileNotFoundError as exc:
                raise PathGuardError(
                    "Path nao encontrado.",
                    hint=f"Verifique o caminho: {target}",
                ) from exc

        if target.exists():
            return target.resolve(strict=True)

        try:
            parent = target.parent.resolve(strict=True)
        except FileNotFoundError as exc:
            raise PathGuardError(
                "Diretorio pai nao encontrado.",
                hint=f"Verifique o caminho: {target.parent}",
            ) from exc
        return parent / target.name

    def _relative_to_workspace(self, path: Path) -> Path:
        try:
            return path.relative_to(self.workspace_root)
        except ValueError as exc:
            raise PathGuardError(
                "Path fora do workspace.",
                hint=f"Operacao negada para: {path}",
            ) from exc


def _has_traversal(path: Path) -> bool:
    return any(part == ".." for part in path.parts)


def _normalize_pattern(pattern: str) -> str:
    normalized = pattern.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lower()


def _normalize_relative(path: Path | str) -> str:
    relative = path.as_posix() if isinstance(path, Path) else str(path)
    relative = relative.replace("\\", "/").strip("/")
    while relative.startswith("./"):
        relative = relative[2:]
    return relative.lower()


def _matches_pattern(relative: str, pattern: str) -> bool:
    if pattern.endswith("/"):
        directory = pattern.rstrip("/")
        return relative == directory or relative.startswith(f"{directory}/")

    has_glob = any(token in pattern for token in "*?[")
    if has_glob:
        return fnmatch.fnmatchcase(relative, pattern) or fnmatch.fnmatchcase(
            Path(relative).name,
            pattern,
        )

    if "/" not in pattern:
        return relative == pattern or relative.endswith(f"/{pattern}")

    return relative == pattern
