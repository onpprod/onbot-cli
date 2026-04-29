from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from onbot_cli.agent.context import ContextManager
from onbot_cli.config import ConfigManager
from onbot_cli.hooks.models import HookEvent, HookResult
from onbot_cli.models import Workspace
from onbot_cli.security.paths import PathGuard
from onbot_cli.security.permissions import PermissionManager
from onbot_cli.storage.logs import AuditLogger
from onbot_cli.storage.sessions import SessionStore
from onbot_cli.tools import ToolContext, create_internal_tool_registry
from onbot_cli.tools.patch import PatchService
from onbot_cli.tools.registry import ToolRegistryError
from onbot_cli.workspace import WorkspaceManager


class RecordingHooks:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def dispatch(
        self,
        event: HookEvent | str,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> HookResult:
        self.events.append((str(event), payload))
        return HookResult(allowed=True, status="ok")


def test_tool_registry_lists_internal_tools_and_validates_schema(
    tmp_path: Path,
) -> None:
    context = _tool_context(tmp_path)
    registry = create_internal_tool_registry(context.config)

    names = {entry.name for entry in registry.list_tools()}

    assert names == {"list_files", "project_summary", "read_file", "search_text"}
    with pytest.raises(ToolRegistryError):
        registry.validate_input("read_file", {})
    with pytest.raises(ToolRegistryError):
        registry.validate_input("read_file", {"path": 42})


def test_tool_registry_honors_disabled_tools_and_records_invocation(
    tmp_path: Path,
) -> None:
    context = _tool_context(
        tmp_path,
        config_override={"tools": {"disabled": ["read_file"]}},
    )
    registry = create_internal_tool_registry(context.config)
    (tmp_path / "README.md").write_text("conteudo", encoding="utf-8")

    result = registry.execute("read_file", {"path": "README.md"}, context)
    session = context.session_store.load(context.session_id or "")

    assert result.status == "disabled"
    assert session.tool_calls[0]["name"] == "read_file"


def test_filesystem_tools_respect_exclusions_size_permissions_and_path_guard(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')", encoding="utf-8")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored" / "skip.py").write_text("skip", encoding="utf-8")
    (tmp_path / "big.txt").write_text("x" * 20, encoding="utf-8")
    (tmp_path / ".env").write_text("TOKEN=secret", encoding="utf-8")

    context = _tool_context(
        tmp_path,
        config_override={
            "workspace": {"exclude": ["ignored/"], "max_file_size_kb": 1},
            "permissions": {
                "mode": "default",
                "allow": [],
                "ask": [],
                "deny": [],
                "protected_paths": [".env", "*.pem", "*.key"],
            },
        },
    )
    registry = create_internal_tool_registry(context.config)

    listed = registry.execute("list_files", {"path": ".", "max_entries": 20}, context)
    read = registry.execute("read_file", {"path": "src/app.py"}, context)
    excluded = registry.execute("read_file", {"path": "ignored/skip.py"}, context)
    too_large = registry.execute("read_file", {"path": "big.txt", "max_bytes": 5}, context)
    protected = registry.execute("read_file", {"path": ".env"}, context)

    listed_paths = {entry["path"] for entry in listed.output["entries"]}
    assert "src/app.py" in listed_paths
    assert "ignored/skip.py" not in listed_paths
    assert read.output["content"] == "print('ok')"
    assert excluded.status == "excluded"
    assert too_large.status == "too_large"
    assert protected.status == "denied"
    assert registry.execute("read_file", {"path": "../outside.txt"}, context).status == "error"


def test_search_tool_finds_text_and_skips_excluded_files(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def main():\n    return 'needle'\n", encoding="utf-8")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "lib.py").write_text("needle", encoding="utf-8")
    context = _tool_context(
        tmp_path,
        config_override={"workspace": {"exclude": ["vendor/"], "max_file_size_kb": 256}},
    )

    result = create_internal_tool_registry(context.config).execute(
        "search_text",
        {"query": "needle", "file_pattern": "*.py"},
        context,
    )

    assert result.success
    assert result.output["count"] == 1
    assert result.output["matches"][0]["path"] == "src/app.py"


def test_project_summary_tool_generates_and_reuses_cache(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("import typer\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'dependencies = ["typer>=0.1", "rich>=1.0"]',
                "",
                "[tool.poetry.dependencies]",
                'python = ">=3.14"',
                'prompt-toolkit = ">=3"',
            ]
        ),
        encoding="utf-8",
    )
    context = _tool_context(tmp_path)
    registry = create_internal_tool_registry(context.config)

    generated = registry.execute("project_summary", {"refresh": True}, context)
    cached = registry.execute("project_summary", {}, context)

    dependency_names = {item["name"] for item in generated.output["dependencies"]}
    assert generated.status == "generated"
    assert cached.status == "cached"
    assert "Python" in {item["name"] for item in generated.output["languages"]}
    assert {"typer", "rich", "prompt-toolkit"}.issubset(dependency_names)
    assert generated.output["commands"]["test"] == "poetry run pytest"


def test_context_manager_selects_relevant_snippets_and_caches_summary(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "alpha.py").write_text("def alpha_feature():\n    return 1\n", encoding="utf-8")
    (tmp_path / "src" / "beta.py").write_text("def beta():\n    return 2\n", encoding="utf-8")
    layout = WorkspaceManager(tmp_path).ensure_workspace().layout
    config = ConfigManager(layout, global_config_path=tmp_path / "missing.yaml").load().config
    manager = ContextManager(layout, config)

    summary = manager.structural_summary(refresh=True)
    bundle = manager.build_context("alpha feature", max_snippets=1)

    assert summary["generated_at"] is not None
    assert bundle.snippets[0].path == "src/alpha.py"
    assert "alpha_feature" in bundle.snippets[0].content
    assert manager.structural_summary()["generated_at"] == summary["generated_at"]


def test_patch_service_generates_diff_applies_and_emits_file_changed_hook(
    tmp_path: Path,
) -> None:
    target = tmp_path / "src"
    target.mkdir()
    (target / "app.py").write_text("old\n", encoding="utf-8")
    hooks = RecordingHooks()
    context = _tool_context(
        tmp_path,
        config_override={"permissions": {"mode": "accept_edits", "allow": [], "ask": [], "deny": []}},
        hook_dispatcher=hooks,
    )
    service = PatchService(context)

    proposal = service.propose({"src/app.py": "new\n"})
    result = service.apply({"src/app.py": "new\n"})

    assert "--- a/src/app.py" in proposal.diff
    assert "+new" in proposal.diff
    assert result.applied
    assert (target / "app.py").read_text(encoding="utf-8") == "new\n"
    assert (str(HookEvent.FILE_CHANGED), {"path": "src/app.py", "created": False, "diff": proposal.diff}) in hooks.events
    assert any(event["type"] == "patch_applied" for event in context.audit_logger.read_audit_events())


def test_patch_service_denies_when_mode_requires_unavailable_approval(
    tmp_path: Path,
) -> None:
    (tmp_path / "file.txt").write_text("old\n", encoding="utf-8")
    context = _tool_context(
        tmp_path,
        config_override={"permissions": {"mode": "default", "allow": [], "ask": [], "deny": []}},
    )

    result = PatchService(context).apply({"file.txt": "new\n"})

    assert not result.applied
    assert result.status == "denied"
    assert (tmp_path / "file.txt").read_text(encoding="utf-8") == "old\n"


def _tool_context(
    tmp_path: Path,
    *,
    config_override: dict[str, Any] | None = None,
    hook_dispatcher: Any | None = None,
) -> ToolContext:
    layout = WorkspaceManager(tmp_path).ensure_workspace().layout
    config = ConfigManager(layout, global_config_path=tmp_path / "missing.yaml").load().config
    if config_override:
        _deep_merge(config, config_override)
    session_store = SessionStore(layout)
    session = session_store.create("tools-test")
    audit = AuditLogger(layout)
    permission_manager = PermissionManager(
        config,
        audit_logger=audit,
        session_store=session_store,
        session_id=session.id,
    )
    return ToolContext(
        workspace=Workspace(tmp_path.resolve()),
        layout=layout,
        config=config,
        path_guard=PathGuard(tmp_path),
        permission_manager=permission_manager,
        audit_logger=audit,
        session_store=session_store,
        session_id=session.id,
        hook_dispatcher=hook_dispatcher or RecordingHooks(),
    )


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value
