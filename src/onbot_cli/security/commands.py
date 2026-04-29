"""Classificacao e execucao controlada de comandos locais."""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from onbot_cli.security.permissions import (
    PermissionAction,
    PermissionEvaluation,
    PermissionManager,
    PermissionRequest,
)
from onbot_cli.storage.logs import AuditLogger
from onbot_cli.storage.models import CommandRecord
from onbot_cli.storage.sessions import SessionStore


class CommandRisk(StrEnum):
    """Niveis de risco de comandos shell."""

    SAFE = "SAFE"
    CAUTION = "CAUTION"
    DANGEROUS = "DANGEROUS"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class CommandClassification:
    """Resultado da politica de comandos."""

    command: str
    risk: CommandRisk
    reason: str
    mutates: bool = False

    @property
    def blocked(self) -> bool:
        return self.risk == CommandRisk.BLOCKED


@dataclass(frozen=True, slots=True)
class CommandRunResult:
    """Resultado da execucao controlada de um comando."""

    command: str
    cwd: Path
    status: str
    classification: CommandClassification
    permission: PermissionEvaluation
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    cancelled: bool = False

    @property
    def succeeded(self) -> bool:
        return self.status == "completed" and self.exit_code == 0


class CommandPolicy:
    """Classifica comandos como SAFE, CAUTION, DANGEROUS ou BLOCKED."""

    def classify(self, command: str) -> CommandClassification:
        text = command.strip()
        if not text:
            return CommandClassification(
                command=command,
                risk=CommandRisk.BLOCKED,
                reason="comando vazio",
            )

        tokens = _tokens(text)
        base = _base_command(tokens[0]) if tokens else ""
        normalized = _normalize_command(text)

        if _is_blocked(base, tokens, normalized):
            return CommandClassification(
                command=command,
                risk=CommandRisk.BLOCKED,
                reason="comando bloqueado pela politica inicial",
                mutates=True,
            )

        if _is_dangerous(base, tokens, normalized):
            return CommandClassification(
                command=command,
                risk=CommandRisk.DANGEROUS,
                reason="comando potencialmente destrutivo",
                mutates=True,
            )

        caution, mutates, reason = _caution_reason(base, tokens, normalized)
        if caution:
            return CommandClassification(
                command=command,
                risk=CommandRisk.CAUTION,
                reason=reason,
                mutates=mutates,
            )

        return CommandClassification(
            command=command,
            risk=CommandRisk.SAFE,
            reason="comando reconhecido como consulta ou validacao local",
            mutates=False,
        )


class CommandRunner:
    """Executa comandos aprovados no cwd do workspace."""

    def __init__(
        self,
        workspace_root: Path | str,
        permission_manager: PermissionManager,
        *,
        command_policy: CommandPolicy | None = None,
        audit_logger: AuditLogger | None = None,
        session_store: SessionStore | None = None,
        session_id: str | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).expanduser().resolve(strict=True)
        self.permission_manager = permission_manager
        self.command_policy = command_policy or CommandPolicy()
        self.audit_logger = audit_logger
        self.session_store = session_store
        self.session_id = session_id

    def run(
        self,
        command: str,
        *,
        timeout: float | None = 60,
        approval_service: Any | None = None,
    ) -> CommandRunResult:
        classification = self.command_policy.classify(command)
        permission = self.permission_manager.authorize(
            PermissionRequest(
                action=PermissionAction.COMMAND,
                target=command,
                risk=classification.risk.value,
                mutates=classification.mutates,
                detail=classification.reason,
            ),
            approval_service=approval_service,
        )

        if classification.blocked or permission.denied:
            status = "blocked" if classification.blocked else "denied"
            result = CommandRunResult(
                command=command,
                cwd=self.workspace_root,
                status=status,
                classification=classification,
                permission=permission,
                stderr=classification.reason if classification.blocked else permission.reason,
            )
            self._record_result(result)
            return result

        try:
            completed = subprocess.run(
                command,
                cwd=self.workspace_root,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            result = CommandRunResult(
                command=command,
                cwd=self.workspace_root,
                status="completed",
                classification=classification,
                permission=permission,
                exit_code=completed.returncode,
                stdout=completed.stdout or "",
                stderr=completed.stderr or "",
            )
        except subprocess.TimeoutExpired as exc:
            result = CommandRunResult(
                command=command,
                cwd=self.workspace_root,
                status="timeout",
                classification=classification,
                permission=permission,
                stdout=_output_text(exc.stdout),
                stderr=_output_text(exc.stderr) or "Tempo limite excedido.",
                timed_out=True,
            )
        except KeyboardInterrupt:
            result = CommandRunResult(
                command=command,
                cwd=self.workspace_root,
                status="cancelled",
                classification=classification,
                permission=permission,
                stderr="Execucao cancelada pelo usuario.",
                cancelled=True,
            )

        self._record_result(result)
        return result

    def _record_result(self, result: CommandRunResult) -> None:
        payload = {
            "command": result.command,
            "cwd": str(result.cwd),
            "status": result.status,
            "risk": result.classification.risk.value,
            "risk_reason": result.classification.reason,
            "permission_decision": result.permission.decision.value,
            "permission_reason": result.permission.reason,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": result.timed_out,
            "cancelled": result.cancelled,
        }
        if self.audit_logger is not None:
            self.audit_logger.record_event(
                "command_execution",
                payload,
                session_id=self.session_id,
            )
        if self.session_store is not None and self.session_id:
            self.session_store.append_command(
                self.session_id,
                CommandRecord(
                    command=result.command,
                    cwd=str(result.cwd),
                    exit_code=result.exit_code,
                    stdout=result.stdout,
                    stderr=result.stderr,
                ),
            )


def _tokens(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return command.split()


def _normalize_command(command: str) -> str:
    return " ".join(command.lower().split())


def _base_command(token: str) -> str:
    cleaned = token.strip().strip("\"'")
    name = cleaned.replace("\\", "/").split("/")[-1].lower()
    for suffix in (".exe", ".cmd", ".bat", ".ps1"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _is_blocked(base: str, tokens: list[str], normalized: str) -> bool:
    if base in {
        "shutdown",
        "reboot",
        "halt",
        "poweroff",
        "format",
        "diskpart",
        "stop-computer",
        "restart-computer",
    }:
        return True

    if base in {"mkfs", "mkfs.ext4", "mkfs.ntfs"}:
        return True

    if _is_rm_root(tokens):
        return True

    return " :(){ :|:& };: " in f" {normalized} "


def _is_rm_root(tokens: list[str]) -> bool:
    if not tokens or _base_command(tokens[0]) != "rm":
        return False
    options = "".join(token.lower().lstrip("-") for token in tokens[1:] if token.startswith("-"))
    recursive_force = "r" in options and "f" in options
    if not recursive_force:
        return False
    targets = [token.strip("\"'") for token in tokens[1:] if not token.startswith("-")]
    return any(target in {"/", "/*", "\\", "\\*"} for target in targets)


def _is_dangerous(base: str, tokens: list[str], normalized: str) -> bool:
    if base == "rm" and any(token.startswith("-r") or "r" in token for token in tokens[1:]):
        return True
    if base in {"del", "erase", "rmdir", "rd"} and any(
        token.lower() in {"/s", "-r", "-recurse"} for token in tokens[1:]
    ):
        return True
    if base == "remove-item" and (
        "-recurse" in normalized or "-r " in normalized
    ):
        return True
    if base == "git" and " reset --hard" in f" {normalized}":
        return True
    if base == "git" and " clean" in f" {normalized}":
        return True
    if base == "git" and (" push --force" in normalized or " push -f" in normalized):
        return True
    if base == "git" and " branch -d" in normalized:
        return True
    if base in {"dd", "chmod", "chown"} and " -r" in normalized:
        return True
    return False


def _caution_reason(
    base: str,
    tokens: list[str],
    normalized: str,
) -> tuple[bool, bool, str]:
    if any(marker in normalized for marker in (" > ", " >> ", " 2>")):
        return True, True, "comando usa redirecionamento de saida"

    if base == "git":
        safe_git = {"status", "diff", "log", "show"}
        subcommand = tokens[1].lower() if len(tokens) > 1 else ""
        if subcommand in safe_git:
            return False, False, ""
        if subcommand == "branch" and "--show-current" in normalized:
            return False, False, ""
        return True, subcommand not in safe_git, "operacao Git mutavel ou sensivel"

    if base == "poetry":
        if " run pytest" in normalized or " run py.test" in normalized:
            return False, False, ""
        if " run ruff check" in normalized or " run mypy" in normalized:
            return False, False, ""
        mutating = {
            "add",
            "remove",
            "update",
            "install",
            "lock",
            "build",
            "publish",
            "config",
        }
        subcommand = tokens[1].lower() if len(tokens) > 1 else ""
        if subcommand in mutating:
            return True, True, "comando Poetry altera ambiente, lockfile ou pacote"
        return False, False, ""

    if base in {"pip", "pip3", "uv", "npm", "yarn", "pnpm"}:
        mutating_terms = {"install", "uninstall", "add", "remove", "update", "publish"}
        mutates = any(term in normalized.split() for term in mutating_terms)
        return True, mutates, "gerenciador de pacotes requer atencao"

    if base in {
        "cp",
        "copy",
        "mv",
        "move",
        "touch",
        "mkdir",
        "new-item",
        "set-content",
        "add-content",
        "out-file",
    }:
        return True, True, "comando altera arquivos"

    if base in {"python", "py"} and " -c " in f" {normalized} ":
        return True, False, "codigo inline requer atencao"

    return False, False, ""


def _output_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
