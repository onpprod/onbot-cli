"""Auditoria local e log operacional."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from onbot_cli.security.redaction import redact_data
from onbot_cli.storage.models import utc_now
from onbot_cli.workspace import WorkspaceLayout


@dataclass(slots=True)
class AuditEvent:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    timestamp: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditLogger:
    """Registra eventos auditaveis e mensagens operacionais."""

    def __init__(self, layout: WorkspaceLayout) -> None:
        self.audit_path = layout.logs_dir / "audit.jsonl"
        self.operational_log_path = layout.logs_dir / "onbot-cli.log"

    def record_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        event = AuditEvent(
            type=event_type,
            payload=payload or {},
            session_id=session_id,
        )
        redacted = redact_data(event.to_dict())
        self._append_jsonl(self.audit_path, redacted)
        self.log_info(
            f"audit:{event_type}",
            {"event": redacted},
        )
        return redacted

    def log_info(
        self,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {
            "timestamp": utc_now(),
            "level": "INFO",
            "message": message,
            "data": data or {},
        }
        redacted = redact_data(record)
        self._append_jsonl(self.operational_log_path, redacted)
        return redacted

    def read_audit_events(self) -> list[dict[str, Any]]:
        return self._read_jsonl(self.audit_path)

    def _append_jsonl(self, path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(data, ensure_ascii=True, sort_keys=True))
            file.write("\n")

    def _read_jsonl(self, path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
