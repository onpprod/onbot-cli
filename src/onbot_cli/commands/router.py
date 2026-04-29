"""Roteamento de slash commands internos."""

from __future__ import annotations

import shlex
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from onbot_cli.errors import ApplicationError
from onbot_cli.models import ApplicationContext, Workspace
from onbot_cli.storage.history import CommandHistory
from onbot_cli.storage.logs import AuditLogger
from onbot_cli.storage.sessions import SessionStore
from onbot_cli.workspace import WorkspaceLayout


class CommandError(ApplicationError):
    """Erro de comando exibido sem derrubar a sessao."""

    code = "command_error"


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    """Representa uma entrada slash command ja tokenizada."""

    raw: str
    name: str
    args: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Resultado de execucao de comando interno."""

    name: str
    status: str = "ok"
    should_exit: bool = False


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """Contrato publico de um comando interno."""

    name: str
    summary: str
    usage: str
    handler: Callable[["CommandContext", Sequence[str]], CommandResult]
    aliases: tuple[str, ...] = ()
    help_text: str | None = None

    @property
    def display_name(self) -> str:
        return f"/{self.name}"


@dataclass(frozen=True, slots=True)
class CommandContext:
    """Dependencias compartilhadas pelos handlers de comandos."""

    app_context: ApplicationContext
    layout: WorkspaceLayout
    config: Mapping[str, Any]
    session_store: SessionStore
    history: CommandHistory
    audit_logger: AuditLogger
    renderer: Any

    @property
    def workspace(self) -> Workspace:
        return self.app_context.workspace

    @property
    def session_id(self) -> str:
        return self.app_context.session_id or ""


class CommandRouter:
    """Interpreta e despacha entradas iniciadas por `/`."""

    def __init__(self, specs: Sequence[CommandSpec]) -> None:
        self._specs_by_name: dict[str, CommandSpec] = {}
        for spec in specs:
            self._register(spec)

    @property
    def specs(self) -> tuple[CommandSpec, ...]:
        unique: dict[str, CommandSpec] = {}
        for spec in self._specs_by_name.values():
            unique[spec.name] = spec
        return tuple(sorted(unique.values(), key=lambda item: item.name))

    @property
    def command_names(self) -> tuple[str, ...]:
        return tuple(spec.display_name for spec in self.specs)

    def parse(self, text: str) -> ParsedCommand | None:
        stripped = text.strip()
        if not stripped.startswith("/"):
            return None
        if stripped == "/":
            raise CommandError(
                "Comando vazio.",
                hint="Digite /help para ver os comandos disponiveis.",
            )

        try:
            tokens = shlex.split(stripped[1:])
        except ValueError as exc:
            raise CommandError(
                "Comando invalido.",
                hint=str(exc),
            ) from exc

        if not tokens:
            raise CommandError(
                "Comando vazio.",
                hint="Digite /help para ver os comandos disponiveis.",
            )

        return ParsedCommand(
            raw=stripped,
            name=tokens[0].lower(),
            args=tuple(tokens[1:]),
        )

    def dispatch(self, text: str, context: CommandContext) -> CommandResult:
        try:
            parsed = self.parse(text)
            if parsed is None:
                return CommandResult(name="", status="ignored")

            spec = self._specs_by_name.get(parsed.name)
            if spec is None:
                raise CommandError(
                    f"Comando desconhecido: /{parsed.name}",
                    hint="Digite /help para ver os comandos disponiveis.",
                )

            result = spec.handler(context, parsed.args)
            context.audit_logger.record_event(
                "slash_command",
                {
                    "command": parsed.name,
                    "args": list(parsed.args),
                    "status": result.status,
                },
                session_id=context.session_id or None,
            )
            return result
        except CommandError as exc:
            message = exc.to_message()
            context.renderer.error(message.message, message.hint)
            context.audit_logger.record_event(
                "slash_command_error",
                {"input": text, "error": message.message, "hint": message.hint},
                session_id=context.session_id or None,
            )
            return CommandResult(name="", status="error")

    def get_spec(self, name: str) -> CommandSpec | None:
        return self._specs_by_name.get(name.lstrip("/").lower())

    def _register(self, spec: CommandSpec) -> None:
        names = (spec.name, *spec.aliases)
        for name in names:
            normalized = name.lower().lstrip("/")
            if normalized in self._specs_by_name:
                raise ValueError(f"Comando duplicado: /{normalized}")
            self._specs_by_name[normalized] = spec
