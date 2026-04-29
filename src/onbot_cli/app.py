"""Bootstrap minimo da aplicacao."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from onbot_cli.models import ApplicationContext, Workspace
from onbot_cli.workspace import resolve_workspace


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """Resultado do bootstrap inicial da CLI."""

    context: ApplicationContext
    interactive_ready: bool
    message: str

    @property
    def workspace(self) -> Workspace:
        return self.context.workspace


def bootstrap_application(start_path: Path | str | None = None) -> BootstrapResult:
    """Prepara o contexto minimo sem criar persistencia local ainda."""

    workspace = resolve_workspace(start_path)
    context = ApplicationContext(
        workspace=workspace,
        metadata={"stage": "foundation"},
    )
    return BootstrapResult(
        context=context,
        interactive_ready=False,
        message="Bootstrap minimo concluido.",
    )
