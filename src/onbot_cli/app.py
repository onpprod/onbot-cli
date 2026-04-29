"""Bootstrap minimo da aplicacao."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from onbot_cli.models import ApplicationContext, Workspace
from onbot_cli.config import ConfigManager
from onbot_cli.storage.cache import ProjectSummaryCache
from onbot_cli.storage.logs import AuditLogger
from onbot_cli.storage.sessions import SessionStore
from onbot_cli.workspace import WorkspaceLayout, WorkspaceManager


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """Resultado do bootstrap inicial da CLI."""

    context: ApplicationContext
    layout: WorkspaceLayout
    config: Mapping[str, Any]
    session_id: str
    interactive_ready: bool
    message: str

    @property
    def workspace(self) -> Workspace:
        return self.context.workspace


def bootstrap_application(start_path: Path | str | None = None) -> BootstrapResult:
    """Prepara contexto, workspace local, config, sessao e auditoria."""

    workspace_manager = WorkspaceManager(start_path)
    workspace_result = workspace_manager.ensure_workspace()
    layout = workspace_result.layout

    config_result = ConfigManager(layout).load()
    cache_created = ProjectSummaryCache(layout).ensure()

    session_store = SessionStore(layout)
    session = session_store.create()

    audit_logger = AuditLogger(layout)
    audit_logger.record_event(
        "session_start",
        {
            "workspace": str(workspace_result.workspace.root),
            "workspace_created_directories": [
                str(path.relative_to(workspace_result.workspace.root))
                for path in workspace_result.created_directories
            ],
            "local_config_created": config_result.local_created,
            "project_summary_cache_created": cache_created,
        },
        session_id=session.id,
    )

    context = ApplicationContext(
        workspace=workspace_result.workspace,
        config=config_result.config,
        session_id=session.id,
        metadata={
            "stage": "workspace-storage",
            "workspace_dir": str(layout.onbot_dir),
            "config_path": str(config_result.local_path),
        },
    )
    return BootstrapResult(
        context=context,
        layout=layout,
        config=config_result.config,
        session_id=session.id,
        interactive_ready=False,
        message="Workspace local e persistencia inicial prontos.",
    )
