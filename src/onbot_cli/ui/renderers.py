"""Renderizadores Rich usados pela experiencia interativa."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from onbot_cli.config import safe_config


class TerminalRenderer:
    """Centraliza a renderizacao de tabelas, paineis e erros."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console(color_system=None)

    def welcome(
        self,
        *,
        version: str,
        workspace: Path,
        persistence_dir: Path,
        session_id: str,
    ) -> None:
        self.console.print(f"[bold]onbot-cli[/bold] {version}")
        self.console.print(f"Workspace: {workspace}", soft_wrap=True)
        self.console.print(f"Persistencia: {persistence_dir}", soft_wrap=True)
        self.console.print(f"Sessao: {session_id}")

    def info(self, message: str) -> None:
        self.console.print(f"[cyan]{message}[/cyan]", soft_wrap=True)

    def warning(self, message: str) -> None:
        self.console.print(f"[yellow]{message}[/yellow]", soft_wrap=True)

    def error(self, message: str, hint: str | None = None) -> None:
        text = Text()
        text.append("Erro: ", style="bold red")
        text.append(message)
        if hint:
            text.append("\n")
            text.append(hint, style="dim")
        self.console.print(Panel(text, border_style="red", expand=False))

    def table(
        self,
        title: str,
        columns: Sequence[str],
        rows: Iterable[Sequence[Any]],
    ) -> None:
        table = Table(title=title, box=box.SIMPLE, show_lines=False)
        for column in columns:
            table.add_column(column)
        for row in rows:
            table.add_row(*(self._to_cell(value) for value in row))
        self.console.print(table)

    def panel(self, title: str, body: str, *, style: str = "cyan") -> None:
        self.console.print(Panel(body, title=title, border_style=style, expand=False))

    def config(self, config: Mapping[str, Any], *, section: str | None = None) -> None:
        value: Any
        if section is None:
            value = safe_config(config)
            title = "Configuracao ativa"
        else:
            value = safe_config(config).get(section)
            title = f"Configuracao: {section}"

        serialized = yaml.safe_dump(
            value,
            sort_keys=False,
            allow_unicode=False,
            default_flow_style=False,
        ).strip()
        self.console.print(
            Panel(
                Syntax(serialized or "null", "yaml", word_wrap=True),
                title=title,
                border_style="cyan",
                expand=False,
            )
        )

    def status(
        self,
        *,
        workspace: Path,
        persistence_dir: Path,
        session_id: str,
        mode: str,
        git_detected: bool,
    ) -> None:
        self.table(
            "Status",
            ("Campo", "Valor"),
            (
                ("workspace", workspace),
                ("persistencia", persistence_dir),
                ("sessao", session_id),
                ("modo", mode),
                ("git", "detectado" if git_detected else "nao detectado"),
            ),
        )

    def history(self, entries: Sequence[Mapping[str, Any]]) -> None:
        if not entries:
            self.info("Historico local vazio.")
            return

        rows = []
        for entry in entries:
            rows.append(
                (
                    str(entry.get("timestamp", "")),
                    str(entry.get("source", "")),
                    str(entry.get("command", "")),
                )
            )
        self.table("Historico", ("Timestamp", "Origem", "Entrada"), rows)

    def plan(self, plan: Mapping[str, Any]) -> None:
        body = yaml.safe_dump(
            dict(plan),
            sort_keys=False,
            allow_unicode=False,
            default_flow_style=False,
        ).strip()
        self.panel("Plano", body, style="magenta")

    def diff(self, diff_text: str) -> None:
        self.console.print(
            Panel(
                Syntax(diff_text or "(sem diff)", "diff", word_wrap=True),
                title="Diff",
                border_style="yellow",
                expand=False,
            )
        )

    def approval_prompt(
        self,
        *,
        action: str,
        target: str,
        risk: str,
        detail: str | None = None,
    ) -> None:
        rows: list[tuple[str, str]] = [
            ("acao", action),
            ("alvo", target),
            ("risco", risk),
        ]
        if detail:
            rows.append(("detalhe", detail))
        table = Table.grid(padding=(0, 1))
        table.add_column(style="bold")
        table.add_column()
        for key, value in rows:
            table.add_row(key, value)
        self.console.print(
            Panel(
                Group(table, Text("Confirme explicitamente para continuar.")),
                title="Aprovacao",
                border_style="yellow",
                expand=False,
            )
        )

    def commands(self, rows: Iterable[Sequence[Any]]) -> None:
        self.table("Comandos internos", ("Comando", "Resumo", "Uso"), rows)

    def _to_cell(self, value: Any) -> str:
        if isinstance(value, Path):
            return str(value)
        if value is None:
            return ""
        return str(value)
