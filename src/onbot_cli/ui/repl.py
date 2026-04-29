"""Loop interativo baseado em prompt_toolkit."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Protocol

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

from onbot_cli.agent.controller import AgentController
from onbot_cli.app import BootstrapResult
from onbot_cli.commands.internal import discover_custom_command_names
from onbot_cli.commands.router import CommandContext, CommandRouter
from onbot_cli.storage.history import CommandHistory, CommandHistoryEntry
from onbot_cli.storage.logs import AuditLogger
from onbot_cli.storage.models import ActionRecord, CommandRecord, MessageRecord
from onbot_cli.storage.sessions import SessionStore
from onbot_cli.ui.prompts import SlashCommandCompleter
from onbot_cli.ui.renderers import TerminalRenderer


class PromptInput(Protocol):
    """Contrato minimo para tornar o REPL testavel."""

    def prompt(self, message: str) -> str:
        """Le uma entrada do usuario."""


class PlainPromptInput:
    """Fallback para ambientes sem TTY real, como testes automatizados."""

    def prompt(self, message: str) -> str:
        print(message, end="", flush=True)
        line = sys.stdin.readline()
        if line == "":
            raise EOFError
        return line.rstrip("\r\n")


class InteractiveShell:
    """Executa a sessao interativa continua do onbot-cli."""

    def __init__(
        self,
        bootstrap: BootstrapResult,
        router: CommandRouter,
        renderer: TerminalRenderer,
        *,
        version: str,
        prompt_input: PromptInput | None = None,
        agent_stub: Callable[[str], str] | None = None,
        agent_controller: AgentController | None = None,
    ) -> None:
        self.bootstrap = bootstrap
        self.router = router
        self.renderer = renderer
        self.version = version
        self.session_store = SessionStore(bootstrap.layout)
        self.history = CommandHistory(bootstrap.layout)
        self.audit_logger = AuditLogger(bootstrap.layout)
        self.prompt_input = prompt_input or self._create_prompt_input()
        self.agent_stub = agent_stub
        self.agent_controller = agent_controller or AgentController.from_bootstrap(
            bootstrap
        )
        self._closed = False

    def run(self) -> None:
        """Inicia o prompt continuo e retorna apenas ao encerrar a sessao."""

        self.renderer.welcome(
            version=self.version,
            workspace=self.bootstrap.workspace.root,
            persistence_dir=self.bootstrap.layout.onbot_dir,
            session_id=self.bootstrap.session_id,
        )

        reason = "eof"
        try:
            while True:
                try:
                    raw_input = self.prompt_input.prompt("onbot> ")
                except KeyboardInterrupt:
                    self.renderer.warning(
                        "Entrada cancelada. A sessao continua ativa."
                    )
                    continue
                except EOFError:
                    self.renderer.info("Sessao encerrada por EOF.")
                    break

                text = _normalize_terminal_input(raw_input)
                if not text:
                    continue

                self._record_user_input(text)

                if text.startswith("/"):
                    result = self.router.dispatch(text, self._command_context())
                    self.session_store.append_action(
                        self.bootstrap.session_id,
                        ActionRecord(
                            type="slash_command",
                            status=result.status,
                            target=result.name or text,
                            detail={"should_exit": result.should_exit},
                        ),
                    )
                    if result.should_exit:
                        reason = "command"
                        break
                    continue

                self._handle_agent_prompt(text)
        finally:
            self.close(reason=reason)

    def close(self, *, reason: str = "closed") -> None:
        """Persiste o encerramento da sessao uma unica vez."""

        if self._closed:
            return
        self._closed = True
        self.session_store.append_action(
            self.bootstrap.session_id,
            ActionRecord(type="session", status="closed", detail={"reason": reason}),
        )
        self.audit_logger.record_event(
            "session_end",
            {"reason": reason},
            session_id=self.bootstrap.session_id,
        )

    def _record_user_input(self, text: str) -> None:
        input_type = "slash_command" if text.startswith("/") else "prompt"
        self.history.append(
            CommandHistoryEntry(
                command=text,
                session_id=self.bootstrap.session_id,
                source=input_type,
                metadata={"input_type": input_type},
            )
        )
        self.audit_logger.record_event(
            "user_prompt_submit",
            {"input_type": input_type, "content": text},
            session_id=self.bootstrap.session_id,
        )

        if input_type == "slash_command":
            self.session_store.append_command(
                self.bootstrap.session_id,
                CommandRecord(command=text, cwd=str(self.bootstrap.workspace.root)),
            )
            return

        self.session_store.append_message(
            self.bootstrap.session_id,
            MessageRecord(
                role="user",
                content=text,
                metadata={"source": "interactive_shell"},
            ),
        )

    def _handle_agent_prompt(self, text: str) -> None:
        if self.agent_stub is not None:
            message = self.agent_stub(text)
            self.renderer.panel("Agente", message, style="green")
            self.session_store.append_action(
                self.bootstrap.session_id,
                ActionRecord(
                    type="agent_prompt",
                    status="stub",
                    detail={"message": message},
                ),
            )
            return

        stream_started = False

        def stream_chunk(chunk: str) -> None:
            nonlocal stream_started
            if not stream_started:
                self.renderer.stream_start("Agente")
                stream_started = True
            self.renderer.stream_chunk(chunk)

        result = self.agent_controller.run(
            text,
            stream_callback=stream_chunk,
            plan_callback=self.renderer.plan,
        )
        if stream_started:
            self.renderer.stream_end()
        else:
            style = "red" if result.status.endswith("error") else "green"
            self.renderer.panel("Agente", result.content, style=style)

    def _command_context(self) -> CommandContext:
        return CommandContext(
            app_context=self.bootstrap.context,
            layout=self.bootstrap.layout,
            config=self.bootstrap.config,
            session_store=self.session_store,
            history=self.history,
            audit_logger=self.audit_logger,
            renderer=self.renderer,
        )

    def _create_prompt_input(self) -> PromptInput:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            return PlainPromptInput()

        history_path = self.bootstrap.layout.history_dir / "prompt_toolkit.txt"
        completer = SlashCommandCompleter(
            self.router.command_names,
            custom_command_provider=lambda: discover_custom_command_names(
                self.bootstrap.layout.commands_dir
            ),
        )
        return PromptSession(
            history=FileHistory(str(history_path)),
            completer=completer,
            complete_while_typing=True,
        )

    def _default_agent_stub(self, _: str) -> str:
        return (
            "Processamento agentico sera conectado nas etapas 05 e 06. "
            "A entrada foi registrada na sessao e no historico local."
        )


def _normalize_terminal_input(value: str) -> str:
    text = value.strip()
    for prefix in ("\ufeff", "\u00ef\u00bb\u00bf"):
        if text.startswith(prefix):
            text = text.removeprefix(prefix).strip()
    return text
