"""Modelos de mensagens trocadas pelo agente."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AgentRole(StrEnum):
    """Roles aceitos no historico e nos payloads OpenAI-compatible."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class AgentToolCall:
    """Chamada de tool solicitada pelo modelo."""

    id: str
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)

    def to_llm_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(dict(self.arguments), ensure_ascii=True),
            },
        }


@dataclass(frozen=True, slots=True)
class AgentMessage:
    """Mensagem independente de provedor."""

    role: AgentRole | str
    content: str = ""
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: Sequence[AgentToolCall] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def system(cls, content: str, **metadata: Any) -> "AgentMessage":
        return cls(AgentRole.SYSTEM, content, metadata=metadata)

    @classmethod
    def user(cls, content: str, **metadata: Any) -> "AgentMessage":
        return cls(AgentRole.USER, content, metadata=metadata)

    @classmethod
    def assistant(
        cls,
        content: str,
        *,
        tool_calls: Sequence[AgentToolCall] = (),
        **metadata: Any,
    ) -> "AgentMessage":
        return cls(
            AgentRole.ASSISTANT,
            content,
            tool_calls=tuple(tool_calls),
            metadata=metadata,
        )

    @classmethod
    def tool_result(
        cls,
        content: str,
        *,
        tool_call_id: str,
        name: str | None = None,
        **metadata: Any,
    ) -> "AgentMessage":
        return cls(
            AgentRole.TOOL,
            content,
            name=name,
            tool_call_id=tool_call_id,
            metadata=metadata,
        )

    def to_llm_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "role": str(self.role),
            "content": self.content,
        }
        if self.name:
            payload["name"] = self.name
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            payload["tool_calls"] = [
                tool_call.to_llm_dict() for tool_call in self.tool_calls
            ]
        return payload

    def to_record(self) -> dict[str, Any]:
        return {
            "role": str(self.role),
            "content": self.content,
            "name": self.name,
            "tool_call_id": self.tool_call_id,
            "tool_calls": [
                {
                    "id": item.id,
                    "name": item.name,
                    "arguments": dict(item.arguments),
                }
                for item in self.tool_calls
            ],
            "metadata": dict(self.metadata),
        }
