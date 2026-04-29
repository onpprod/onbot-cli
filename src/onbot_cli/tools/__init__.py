"""Fronteira do catalogo de tools internas e locais."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from onbot_cli.tools.base import Tool, ToolContext, ToolOrigin, ToolResult, ToolRisk
from onbot_cli.tools.filesystem import ListFilesTool, ReadFileTool
from onbot_cli.tools.patch import PatchApplyResult, PatchProposal, PatchService
from onbot_cli.tools.registry import (
    ToolCatalogEntry,
    ToolRegistry,
    ToolRegistryError,
)
from onbot_cli.tools.search import SearchTextTool
from onbot_cli.tools.summary import ProjectSummaryTool


def create_internal_tool_registry(config: Mapping[str, Any] | None = None) -> ToolRegistry:
    """Cria o catalogo com as tools internas iniciais."""

    registry = (
        ToolRegistry.from_config(config)
        if config is not None
        else ToolRegistry()
    )
    registry.register(ListFilesTool())
    registry.register(ReadFileTool())
    registry.register(SearchTextTool())
    registry.register(ProjectSummaryTool())
    return registry


__all__ = [
    "ListFilesTool",
    "PatchApplyResult",
    "PatchProposal",
    "PatchService",
    "ProjectSummaryTool",
    "ReadFileTool",
    "SearchTextTool",
    "Tool",
    "ToolCatalogEntry",
    "ToolContext",
    "ToolOrigin",
    "ToolRegistry",
    "ToolRegistryError",
    "ToolResult",
    "ToolRisk",
    "create_internal_tool_registry",
]
