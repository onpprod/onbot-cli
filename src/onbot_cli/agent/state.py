"""Estado multi-turn e interacoes pendentes do agente."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4

from onbot_cli.storage.models import utc_now
from onbot_cli.storage.sessions import SessionStore


class AgentTurnStatus(StrEnum):
    """Estados principais de um turno agentico."""

    IDLE = "idle"
    RUNNING = "running"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    AWAITING_CHOICE = "awaiting_choice"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


class PendingInteractionType(StrEnum):
    """Tipos de interacao que podem bloquear o proximo turno."""

    CONFIRMATION = "confirmation"
    CHOICE = "choice"


class PendingInteractionStatus(StrEnum):
    """Status persistido de uma interacao pendente."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    EXPIRED = "expired"


@dataclass(slots=True)
class PendingInteraction:
    """Estado persistivel de uma confirmacao ou escolha."""

    id: str
    type: str
    prompt: str
    workflow: str | None = None
    step: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    options: list[str] = field(default_factory=list)
    status: str = PendingInteractionStatus.PENDING.value
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    response: str | None = None

    @classmethod
    def create(
        cls,
        *,
        type: PendingInteractionType | str,
        prompt: str,
        workflow: str | None = None,
        step: str | None = None,
        payload: dict[str, Any] | None = None,
        options: list[str] | None = None,
    ) -> "PendingInteraction":
        return cls(
            id=f"pending-{uuid4().hex[:12]}",
            type=str(type),
            prompt=prompt,
            workflow=workflow,
            step=step,
            payload=dict(payload or {}),
            options=list(options or []),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PendingInteraction":
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            prompt=str(data.get("prompt", "")),
            workflow=(
                None if data.get("workflow") is None else str(data.get("workflow"))
            ),
            step=None if data.get("step") is None else str(data.get("step")),
            payload=dict(data.get("payload", {})),
            options=[str(item) for item in data.get("options", [])],
            status=str(data.get("status", PendingInteractionStatus.PENDING.value)),
            created_at=str(data.get("created_at", utc_now())),
            updated_at=str(data.get("updated_at", utc_now())),
            response=None if data.get("response") is None else str(data["response"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def resolve(self, status: PendingInteractionStatus | str, response: str) -> None:
        self.status = str(status)
        self.response = response
        self.updated_at = utc_now()


class ConversationStateManager:
    """Persistencia e roteamento basico de pendencias da sessao."""

    def __init__(self, session_store: SessionStore, session_id: str | None) -> None:
        self.session_store = session_store
        self.session_id = session_id

    def active_pending(self) -> PendingInteraction | None:
        for pending in reversed(self._load_all()):
            if pending.status == PendingInteractionStatus.PENDING.value:
                return pending
        return None

    def create_pending(
        self,
        *,
        type: PendingInteractionType | str,
        prompt: str,
        workflow: str | None = None,
        step: str | None = None,
        payload: dict[str, Any] | None = None,
        options: list[str] | None = None,
    ) -> PendingInteraction:
        pending = PendingInteraction.create(
            type=type,
            prompt=prompt,
            workflow=workflow,
            step=step,
            payload=payload,
            options=options,
        )
        all_items = self._load_all()
        all_items.append(pending)
        self._save_all(all_items)
        return pending

    def resolve_pending(
        self,
        pending_id: str,
        *,
        status: PendingInteractionStatus | str,
        response: str,
    ) -> PendingInteraction | None:
        all_items = self._load_all()
        resolved: PendingInteraction | None = None
        for pending in all_items:
            if pending.id == pending_id:
                pending.resolve(status, response)
                resolved = pending
                break
        self._save_all(all_items)
        return resolved

    def _load_all(self) -> list[PendingInteraction]:
        if not self.session_id:
            return []
        session = self.session_store.load(self.session_id)
        return [
            PendingInteraction.from_dict(item)
            for item in session.pending_interactions
            if isinstance(item, dict)
        ]

    def _save_all(self, pending_interactions: list[PendingInteraction]) -> None:
        if not self.session_id:
            return
        session = self.session_store.load(self.session_id)
        session.pending_interactions = [
            pending.to_dict() for pending in pending_interactions
        ]
        self.session_store.save(session)


def classify_pending_response(text: str) -> str | None:
    """Classifica respostas curtas para pendencias ativas."""

    normalized = text.strip().lower()
    if normalized in {"sim", "s", "yes", "y", "ok", "continuar", "proseguir", "prosseguir"}:
        return "approve"
    if normalized in {"nao", "não", "n", "no", "cancelar", "cancela", "pare", "parar"}:
        return "reject"
    return None


def is_short_confirmation_without_pending(text: str) -> bool:
    return classify_pending_response(text) is not None
