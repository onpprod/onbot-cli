"""Catalogo e invocacao controlada de tools."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from onbot_cli.errors import ApplicationError
from onbot_cli.hooks.models import HookEvent
from onbot_cli.security.permissions import PermissionAction, PermissionRequest
from onbot_cli.tools.base import Tool, ToolContext, ToolOrigin, ToolResult, ToolRisk


class ToolRegistryError(ApplicationError):
    """Erro no catalogo ou na validacao de uma tool."""

    code = "tool_registry_error"


@dataclass(frozen=True, slots=True)
class ToolCatalogEntry:
    """Linha renderizavel do catalogo de tools."""

    name: str
    description: str
    input_schema: Mapping[str, Any]
    risk_level: str
    origin: str
    enabled: bool = True


class ToolRegistry:
    """Registra, lista, habilita, desabilita e executa tools."""

    def __init__(
        self,
        *,
        enabled: Sequence[str] | None = None,
        disabled: Sequence[str] | None = None,
    ) -> None:
        self._tools: dict[str, Tool] = {}
        self._enabled_filter = {item.lower() for item in enabled or ()}
        self._disabled = {item.lower() for item in disabled or ()}

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "ToolRegistry":
        tools_config = config.get("tools", {})
        if not isinstance(tools_config, Mapping):
            tools_config = {}
        return cls(
            enabled=_as_text_list(tools_config.get("enabled")),
            disabled=_as_text_list(tools_config.get("disabled")),
        )

    def register(self, tool: Tool) -> Tool:
        self._validate_tool_contract(tool)
        name = tool.name.lower()
        if name in self._tools:
            raise ToolRegistryError(
                "Tool duplicada.",
                hint=f"Ja existe uma tool registrada como: {tool.name}",
            )
        self._tools[name] = tool
        return tool

    def get(self, name: str) -> Tool:
        normalized = name.lower()
        try:
            return self._tools[normalized]
        except KeyError as exc:
            raise ToolRegistryError(
                "Tool nao encontrada.",
                hint=f"Nome solicitado: {name}",
            ) from exc

    def list_tools(
        self,
        *,
        include_disabled: bool = False,
    ) -> tuple[ToolCatalogEntry, ...]:
        entries: list[ToolCatalogEntry] = []
        for tool in sorted(self._tools.values(), key=lambda item: item.name):
            enabled = self.is_enabled(tool.name)
            if not include_disabled and not enabled:
                continue
            entries.append(
                ToolCatalogEntry(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                    risk_level=str(tool.risk_level),
                    origin=str(tool.origin),
                    enabled=enabled,
                )
            )
        return tuple(entries)

    def enable(self, name: str) -> None:
        self.get(name)
        normalized = name.lower()
        self._disabled.discard(normalized)
        if self._enabled_filter:
            self._enabled_filter.add(normalized)

    def disable(self, name: str) -> None:
        self.get(name)
        self._disabled.add(name.lower())

    def is_enabled(self, name: str) -> bool:
        normalized = name.lower()
        if normalized in self._disabled:
            return False
        if self._enabled_filter and normalized not in self._enabled_filter:
            return False
        return normalized in self._tools

    def validate_input(
        self,
        name: str,
        input_data: Mapping[str, Any],
    ) -> None:
        tool = self.get(name)
        _validate_json_schema(tool.input_schema, input_data, path="input")

    def execute(
        self,
        name: str,
        input_data: Mapping[str, Any] | None,
        context: ToolContext,
    ) -> ToolResult:
        tool = self.get(name)
        payload = dict(input_data or {})

        if not self.is_enabled(tool.name):
            result = ToolResult.fail(
                "Tool desabilitada por configuracao.",
                status="disabled",
                metadata={"tool": tool.name},
            )
            context.record_tool_call(name=tool.name, input_data=payload, result=result)
            return result

        self.validate_input(tool.name, payload)
        permission = context.authorize(
            PermissionRequest(
                action=PermissionAction.TOOL,
                target=tool.name,
                risk=str(tool.risk_level),
                mutates=_risk_mutates(str(tool.risk_level)),
                detail=tool.description,
            )
        )
        if permission.denied:
            result = ToolResult.fail(
                "Invocacao de tool negada.",
                status="denied",
                metadata={"reason": permission.reason},
            )
            context.record_tool_call(name=tool.name, input_data=payload, result=result)
            return result

        pre_hook = context.dispatch_hook(
            HookEvent.PRE_TOOL_USE,
            {
                "tool": tool.name,
                "origin": str(tool.origin),
                "risk": str(tool.risk_level),
                "input": payload,
            },
        )
        if not pre_hook.allowed:
            result = ToolResult.fail(
                pre_hook.reason or "Hook pre_tool_use negou a invocacao.",
                status="denied",
                metadata={"hook_status": pre_hook.status},
            )
            context.record_tool_call(name=tool.name, input_data=payload, result=result)
            return result

        try:
            result = tool.execute(context, payload)
        except ApplicationError as exc:
            result = ToolResult.fail(
                exc.message,
                status="error",
                metadata={"code": exc.code, "hint": exc.hint},
            )
        except Exception as exc:  # pragma: no cover - guardrail defensivo.
            result = ToolResult.fail(
                "Erro inesperado na tool.",
                status="error",
                metadata={"error_type": type(exc).__name__},
            )

        context.dispatch_hook(
            HookEvent.POST_TOOL_USE,
            {
                "tool": tool.name,
                "origin": str(tool.origin),
                "risk": str(tool.risk_level),
                "input": payload,
                "status": result.status,
                "success": result.success,
            },
        )
        context.record_tool_call(name=tool.name, input_data=payload, result=result)
        return result

    def _validate_tool_contract(self, tool: Tool) -> None:
        if not tool.name.strip():
            raise ToolRegistryError("Tool invalida.", hint="Nome e obrigatorio.")
        if not tool.description.strip():
            raise ToolRegistryError(
                "Tool invalida.",
                hint=f"Descricao e obrigatoria para: {tool.name}",
            )
        try:
            ToolRisk(str(tool.risk_level))
        except ValueError as exc:
            raise ToolRegistryError(
                "Risco de tool invalido.",
                hint=f"Tool: {tool.name}, risco: {tool.risk_level}",
            ) from exc
        try:
            ToolOrigin(str(tool.origin))
        except ValueError as exc:
            raise ToolRegistryError(
                "Origem de tool invalida.",
                hint=f"Tool: {tool.name}, origem: {tool.origin}",
            ) from exc
        if not isinstance(tool.input_schema, Mapping):
            raise ToolRegistryError(
                "Schema de entrada invalido.",
                hint=f"Tool: {tool.name}",
            )


def _validate_json_schema(
    schema: Mapping[str, Any],
    value: Any,
    *,
    path: str,
) -> None:
    expected_type = schema.get("type")
    if expected_type is None:
        return

    if isinstance(expected_type, list | tuple):
        if any(_matches_type(item, value) for item in expected_type):
            return
        raise _schema_error(path, expected_type, value)

    if not _matches_type(str(expected_type), value):
        raise _schema_error(path, expected_type, value)

    if expected_type == "object":
        if not isinstance(value, Mapping):
            raise _schema_error(path, expected_type, value)
        required = schema.get("required", ())
        if not isinstance(required, list | tuple):
            required = ()
        missing = [item for item in required if item not in value]
        if missing:
            raise ToolRegistryError(
                "Entrada de tool invalida.",
                hint=f"Campos obrigatorios ausentes em {path}: {', '.join(missing)}",
            )

        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            properties = {}
        additional_allowed = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key not in properties:
                if additional_allowed is False:
                    raise ToolRegistryError(
                        "Entrada de tool invalida.",
                        hint=f"Campo inesperado em {path}: {key}",
                    )
                continue
            property_schema = properties[key]
            if isinstance(property_schema, Mapping):
                _validate_json_schema(
                    property_schema,
                    item,
                    path=f"{path}.{key}",
                )

    if expected_type == "array":
        if not isinstance(value, list | tuple):
            raise _schema_error(path, expected_type, value)
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                _validate_json_schema(item_schema, item, path=f"{path}[{index}]")

    enum_values = schema.get("enum")
    if enum_values is not None and value not in enum_values:
        raise ToolRegistryError(
            "Entrada de tool invalida.",
            hint=f"Valor fora do enum em {path}: {value}",
        )


def _matches_type(expected_type: str, value: Any) -> bool:
    if expected_type == "object":
        return isinstance(value, Mapping)
    if expected_type == "array":
        return isinstance(value, list | tuple)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return True


def _schema_error(path: str, expected_type: Any, value: Any) -> ToolRegistryError:
    return ToolRegistryError(
        "Entrada de tool invalida.",
        hint=(
            f"{path} esperava tipo {expected_type}, "
            f"recebeu {type(value).__name__}."
        ),
    )


def _risk_mutates(risk: str) -> bool:
    return risk.upper() in {ToolRisk.CAUTION.value, ToolRisk.DANGEROUS.value}


def _as_text_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value)
    if value:
        return (str(value),)
    return ()
