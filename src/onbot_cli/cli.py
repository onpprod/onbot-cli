"""Ponto de entrada Typer do onbot-cli."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console

from onbot_cli import __version__
from onbot_cli.app import bootstrap_application
from onbot_cli.commands.internal import create_default_router
from onbot_cli.errors import ApplicationError
from onbot_cli.ui.renderers import TerminalRenderer
from onbot_cli.ui.repl import InteractiveShell


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
    """Inicializa a CLI em modo interativo."""

    if ctx.invoked_subcommand is not None:
        return

    console = Console(color_system=None)
    renderer = TerminalRenderer(console)

    try:
        result = bootstrap_application()
        shell = InteractiveShell(
            result,
            create_default_router(),
            renderer,
            version=__version__,
        )
        shell.run()
    except ApplicationError as exc:
        message = exc.to_message()
        renderer.error(message.message, message.hint)
        raise typer.Exit(exc.exit_code) from exc
