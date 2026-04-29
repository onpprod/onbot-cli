"""Historico append-only de comandos."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from onbot_cli.security.redaction import redact_data
from onbot_cli.storage.models import utc_now
from onbot_cli.workspace import WorkspaceLayout


@dataclass(slots=True)
class CommandHistoryEntry:
    command: str
    session_id: str | None = None
    source: str = "user"
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CommandHistory:
    """Grava comandos em JSONL sem reescrever entradas anteriores."""

    def __init__(self, layout: WorkspaceLayout) -> None:
        self.path = layout.history_dir / "commands.jsonl"

    def append(self, entry: CommandHistoryEntry) -> dict[str, Any]:
        payload = redact_data(entry.to_dict())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=True, sort_keys=True))
            file.write("\n")
        return payload

    def read(self, limit: int | None = None) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []

        lines = self.path.read_text(encoding="utf-8").splitlines()
        if limit is not None:
            lines = lines[-limit:]
        return [json.loads(line) for line in lines if line.strip()]
