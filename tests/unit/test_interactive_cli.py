from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

from prompt_toolkit.document import Document
from rich.console import Console

from onbot_cli.app import bootstrap_application
from onbot_cli.commands.internal import create_default_router
from onbot_cli.commands.router import CommandContext
from onbot_cli.config import ConfigManager
from onbot_cli.models import ApplicationContext
from onbot_cli.storage.history import CommandHistory
from onbot_cli.storage.logs import AuditLogger
from onbot_cli.storage.sessions import SessionStore
from onbot_cli.ui.prompts import SlashCommandCompleter
from onbot_cli.ui.renderers import TerminalRenderer
from onbot_cli.ui.repl import InteractiveShell
from onbot_cli.workspace import WorkspaceLayout, WorkspaceManager


class FakePromptInput:
    def __init__(self, values: list[str | BaseException]) -> None:
        self.values = list(values)

    def prompt(self, message: str) -> str:
        if not self.values:
            raise EOFError
        value = self.values.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def test_router_parses_and_handles_unknown_command(tmp_path: Path) -> None:
    router = create_default_router()
    context, output, _ = _command_context(tmp_path)

    parsed = router.parse('/history 5 "quoted value"')
    assert parsed is not None
    assert parsed.name == "history"
    assert parsed.args == ("5", "quoted value")

    result = router.dispatch("/missing", context)

    assert result.status == "error"
    assert "Comando desconhecido" in output.getvalue()


def test_internal_commands_render_core_state(tmp_path: Path) -> None:
    router = create_default_router()
    context, output, _ = _command_context(tmp_path)

    assert router.dispatch("/help", context).status == "ok"
    assert router.dispatch("/status", context).status == "ok"
    assert router.dispatch("/permissions", context).status == "ok"
    assert router.dispatch("/mode", context).status == "ok"
    assert router.dispatch("/tools", context).status == "ok"

    rendered = output.getvalue()
    assert "/help" in rendered
    assert "Status" in rendered
    assert "Permissoes" in rendered
    assert "default" in rendered
    assert "Tool Registry sera implementado" in rendered


def test_config_command_redacts_sensitive_values(tmp_path: Path) -> None:
    router = create_default_router()
    context, output, _ = _command_context(
        tmp_path,
        config_override={
            "model": {
                "base_url": "",
                "api_key": "plain-secret",
                "api_key_env": "OPENAI_API_KEY",
            },
            "permissions": {"mode": "default"},
        },
    )

    result = router.dispatch("/config", context)

    assert result.status == "ok"
    rendered = output.getvalue()
    assert "plain-secret" not in rendered
    assert "***REDACTED***" in rendered
    assert "OPENAI_API_KEY" in rendered


def test_history_command_reads_persisted_entries(tmp_path: Path) -> None:
    router = create_default_router()
    context, output, history = _command_context(tmp_path)
    history.append_entry("first")

    result = router.dispatch("/history 1", context)

    assert result.status == "ok"
    assert "first" in output.getvalue()


def test_completer_suggests_internal_and_custom_commands() -> None:
    completer = SlashCommandCompleter(
        ["/help", "/history"],
        custom_command_provider=lambda: ["/feature"],
    )

    help_items = list(completer.get_completions(Document("/h"), None))
    custom_items = list(completer.get_completions(Document("/f"), None))

    assert [item.text for item in help_items] == ["/help", "/history"]
    assert [item.text for item in custom_items] == ["/feature"]


def test_shell_records_prompts_commands_and_exit(tmp_path: Path) -> None:
    bootstrap = bootstrap_application(tmp_path)
    output = StringIO()
    renderer = TerminalRenderer(_console(output))
    shell = InteractiveShell(
        bootstrap,
        create_default_router(),
        renderer,
        version="0.1.0",
        prompt_input=FakePromptInput(["implemente algo", "/status", "/exit"]),
    )

    shell.run()

    session = SessionStore(bootstrap.layout).load(bootstrap.session_id)
    history_entries = CommandHistory(bootstrap.layout).read()
    rendered = output.getvalue()

    assert [entry["command"] for entry in history_entries] == [
        "implemente algo",
        "/status",
        "/exit",
    ]
    assert session.messages[0]["content"] == "implemente algo"
    assert [command["command"] for command in session.commands] == [
        "/status",
        "/exit",
    ]
    assert any(action["type"] == "session" for action in session.actions)
    assert "Status" in rendered
    assert "Sessao encerrando" in rendered


def test_shell_handles_keyboard_interrupt_without_losing_session(
    tmp_path: Path,
) -> None:
    bootstrap = bootstrap_application(tmp_path)
    output = StringIO()
    renderer = TerminalRenderer(_console(output))
    shell = InteractiveShell(
        bootstrap,
        create_default_router(),
        renderer,
        version="0.1.0",
        prompt_input=FakePromptInput([KeyboardInterrupt(), "/exit"]),
    )

    shell.run()

    history_entries = CommandHistory(bootstrap.layout).read()
    assert [entry["command"] for entry in history_entries] == ["/exit"]
    assert "Entrada cancelada" in output.getvalue()


def test_shell_normalizes_windows_pipe_bom_before_slash_command(
    tmp_path: Path,
) -> None:
    bootstrap = bootstrap_application(tmp_path)
    output = StringIO()
    renderer = TerminalRenderer(_console(output))
    shell = InteractiveShell(
        bootstrap,
        create_default_router(),
        renderer,
        version="0.1.0",
        prompt_input=FakePromptInput(["\u00ef\u00bb\u00bf/status", "/exit"]),
    )

    shell.run()

    history_entries = CommandHistory(bootstrap.layout).read()
    assert [entry["command"] for entry in history_entries] == ["/status", "/exit"]
    assert "Status" in output.getvalue()


def test_renderer_supports_stage03_surfaces() -> None:
    output = StringIO()
    renderer = TerminalRenderer(_console(output))

    renderer.plan({"objetivo": "validar", "passos": ["rodar testes"]})
    renderer.diff("--- a\n+++ b\n")
    renderer.approval_prompt(action="write", target="file.py", risk="CAUTION")

    rendered = output.getvalue()
    assert "Plano" in rendered
    assert "Diff" in rendered
    assert "Aprovacao" in rendered


def _command_context(
    tmp_path: Path,
    *,
    config_override: dict[str, Any] | None = None,
) -> tuple[CommandContext, StringIO, "HistoryHelper"]:
    layout = WorkspaceManager(tmp_path).ensure_workspace().layout
    config = config_override or ConfigManager(
        layout,
        global_config_path=tmp_path / "missing-global.yaml",
    ).load().config
    session = SessionStore(layout).create("session-test")
    output = StringIO()
    renderer = TerminalRenderer(_console(output))
    history = HistoryHelper(layout)

    context = CommandContext(
        app_context=ApplicationContext(
            workspace=WorkspaceManager(tmp_path).workspace,
            config=config,
            session_id=session.id,
        ),
        layout=layout,
        config=config,
        session_store=SessionStore(layout),
        history=history.history,
        audit_logger=AuditLogger(layout),
        renderer=renderer,
    )
    return context, output, history


class HistoryHelper:
    def __init__(self, layout: WorkspaceLayout) -> None:
        self.history = CommandHistory(layout)

    def append_entry(self, command: str) -> None:
        from onbot_cli.storage.history import CommandHistoryEntry

        self.history.append(CommandHistoryEntry(command=command, source="test"))


def _console(output: StringIO) -> Console:
    return Console(file=output, color_system=None, width=120)
