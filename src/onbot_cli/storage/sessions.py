"""Persistencia de sessoes em `.onbot-cli/sessions`."""

from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import uuid4

from onbot_cli.errors import StorageError
from onbot_cli.security.redaction import redact_data
from onbot_cli.storage.models import (
    ActionRecord,
    CommandRecord,
    GitOperationRecord,
    HookRecord,
    MessageRecord,
    PermissionDecisionRecord,
    SessionRecord,
    ToolCallRecord,
    utc_now,
)
from onbot_cli.workspace import WorkspaceLayout


SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class SessionStore:
    """Cria, atualiza e le sessoes persistidas como JSON."""

    def __init__(self, layout: WorkspaceLayout) -> None:
        self.layout = layout
        self.sessions_dir = layout.sessions_dir

    def create(self, session_id: str | None = None) -> SessionRecord:
        session = SessionRecord.create(session_id or new_session_id())
        self.save(session)
        return session

    def load(self, session_id: str) -> SessionRecord:
        path = self._path_for(session_id)
        if not path.exists():
            raise StorageError(
                "Sessao nao encontrada.",
                hint=f"Arquivo esperado: {path}",
            )

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StorageError(
                "Sessao invalida.",
                hint=f"Revise o JSON em: {path}",
            ) from exc

        if not isinstance(data, dict):
            raise StorageError(
                "Sessao invalida.",
                hint=f"O arquivo precisa conter um objeto JSON: {path}",
            )

        return SessionRecord.from_dict(data)

    def save(self, session: SessionRecord) -> None:
        session.touch()
        payload = redact_data(session.to_dict())
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(self._path_for(session.id), payload)

    def append_message(self, session_id: str, message: MessageRecord) -> SessionRecord:
        session = self.load(session_id)
        session.messages.append(redact_data(message.to_dict()))
        self.save(session)
        return session

    def append_action(self, session_id: str, action: ActionRecord) -> SessionRecord:
        session = self.load(session_id)
        session.actions.append(redact_data(action.to_dict()))
        self.save(session)
        return session

    def append_tool_call(
        self,
        session_id: str,
        tool_call: ToolCallRecord,
    ) -> SessionRecord:
        session = self.load(session_id)
        session.tool_calls.append(redact_data(tool_call.to_dict()))
        self.save(session)
        return session

    def append_command(
        self,
        session_id: str,
        command: CommandRecord,
    ) -> SessionRecord:
        session = self.load(session_id)
        session.commands.append(redact_data(command.to_dict()))
        self.save(session)
        return session

    def append_git_operation(
        self,
        session_id: str,
        operation: GitOperationRecord,
    ) -> SessionRecord:
        session = self.load(session_id)
        session.git_operations.append(redact_data(operation.to_dict()))
        self.save(session)
        return session

    def append_permission_decision(
        self,
        session_id: str,
        decision: PermissionDecisionRecord,
    ) -> SessionRecord:
        session = self.load(session_id)
        session.permission_decisions.append(redact_data(decision.to_dict()))
        self.save(session)
        return session

    def append_hook(self, session_id: str, hook: HookRecord) -> SessionRecord:
        session = self.load(session_id)
        session.hooks.append(redact_data(hook.to_dict()))
        self.save(session)
        return session

    def _path_for(self, session_id: str) -> Path:
        if not SESSION_ID_RE.fullmatch(session_id):
            raise StorageError(
                "ID de sessao invalido.",
                hint="Use apenas letras, numeros, ponto, hifen ou sublinhado.",
            )
        return self.sessions_dir / f"{session_id}.json"


def new_session_id() -> str:
    timestamp = utc_now().replace("-", "").replace(":", "").replace(".", "")
    timestamp = timestamp.replace("Z", "Z").replace("+0000", "Z")
    return f"{timestamp}-{uuid4().hex[:8]}"


def _write_json_atomic(path: Path, data: object) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)
