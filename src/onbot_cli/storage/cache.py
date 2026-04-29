"""Cache estrutural inicial do workspace."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from onbot_cli.storage.models import utc_now
from onbot_cli.workspace import WorkspaceLayout


PROJECT_SUMMARY_VERSION = 1


class ProjectSummaryCache:
    """Contrato de leitura e escrita para `cache/project-summary.json`."""

    def __init__(self, layout: WorkspaceLayout) -> None:
        self.layout = layout
        self.path = layout.cache_dir / "project-summary.json"

    def ensure(self) -> bool:
        if self.path.exists():
            return False

        self.write(default_project_summary(self.layout))
        return True

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            self.ensure()

        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default_project_summary(self.layout)
        return data

    def write(self, summary: dict[str, Any]) -> None:
        payload = deepcopy(summary)
        payload.setdefault("schema_version", PROJECT_SUMMARY_VERSION)
        payload["updated_at"] = utc_now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.path)


def default_project_summary(layout: WorkspaceLayout) -> dict[str, Any]:
    return {
        "schema_version": PROJECT_SUMMARY_VERSION,
        "generated_at": None,
        "updated_at": None,
        "workspace": {
            "name": layout.root.name,
            "root": str(layout.root),
        },
        "tree": [],
        "languages": [],
        "dependencies": [],
        "commands": {
            "test": None,
            "lint": None,
            "format": None,
            "build": None,
        },
        "config_files": [],
        "conventions": [],
    }
