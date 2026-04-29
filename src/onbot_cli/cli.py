"""Ponto de entrada Typer do onbot-cli."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from onbot_cli import __version__
from onbot_cli.app import bootstrap_application
from onbot_cli.errors import ApplicationError


app = typer.Typer(
    add_completion=False,
    help="CLI interativa agentica para desenvolvimento de software local.",
    invoke_without_command=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Mostra a versao instalada.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Inicializa a CLI em modo interativo preparado."""

    if ctx.invoked_subcommand is not None:
        return

    console = Console(color_system=None)

    try:
        result = bootstrap_application()
    except ApplicationError as exc:
        message = exc.to_message()
        console.print(f"[bold red]Erro:[/bold red] {message.message}")
        if message.hint:
            console.print(message.hint)
        raise typer.Exit(exc.exit_code) from exc

    console.print(f"[bold]onbot-cli[/bold] {__version__}")
    console.print(f"Workspace: {result.workspace.root}", soft_wrap=True)
    console.print(f"Persistencia: {result.layout.onbot_dir}", soft_wrap=True)
    console.print(f"Sessao: {result.session_id}")
    console.print(result.message)
    console.print("Modo interativo: preparado para as proximas etapas.")
