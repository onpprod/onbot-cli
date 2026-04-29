"""Resumo estrutural do projeto para contexto e catalogo de tools."""

from __future__ import annotations

import json
import tomllib
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from onbot_cli.security.paths import PathGuard, PathGuardError, PathOperation
from onbot_cli.storage.cache import ProjectSummaryCache
from onbot_cli.storage.models import utc_now
from onbot_cli.tools.base import ToolContext, ToolOrigin, ToolResult, ToolRisk
from onbot_cli.tools.filesystem import iter_workspace_paths, max_file_size_bytes
from onbot_cli.workspace import WorkspaceLayout


LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".json": "JSON",
    ".md": "Markdown",
    ".toml": "TOML",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".html": "HTML",
    ".css": "CSS",
    ".sh": "Shell",
    ".ps1": "PowerShell",
}

KNOWN_CONFIG_FILES = {
    "pyproject.toml",
    "poetry.lock",
    "requirements.txt",
    "setup.cfg",
    "ruff.toml",
    ".ruff.toml",
    "mypy.ini",
    "pytest.ini",
    "package.json",
    "tsconfig.json",
    "vite.config.ts",
    "README.md",
}


class ProjectSummaryTool:
    """Gera e cacheia um resumo estrutural do workspace."""

    name = "project_summary"
    description = "Gera resumo estrutural, linguagens, dependencias e comandos."
    risk_level = ToolRisk.SAFE
    origin = ToolOrigin.INTERNAL
    input_schema = {
        "type": "object",
        "properties": {
            "refresh": {"type": "boolean"},
            "max_entries": {"type": "integer"},
        },
        "additionalProperties": False,
    }

    def execute(
        self,
        context: ToolContext,
        input_data: Mapping[str, Any],
    ) -> ToolResult:
        refresh = bool(input_data.get("refresh", False))
        max_entries = _positive_int(input_data.get("max_entries"), default=200)
        cache = ProjectSummaryCache(context.layout)
        cached = cache.read()
        if not refresh and cached.get("generated_at"):
            return ToolResult.ok(cached, status="cached")

        summary = generate_project_summary(
            context.layout,
            context.config,
            path_guard=context.path_guard,
            max_entries=max_entries,
        )
        cache.write(summary)
        return ToolResult.ok(cache.read(), status="generated")


def generate_project_summary(
    layout: WorkspaceLayout,
    config: Mapping[str, Any],
    *,
    path_guard: PathGuard | None = None,
    max_entries: int = 200,
) -> dict[str, Any]:
    """Cria um resumo estrutural sem ler arquivos sensiveis."""

    guard = path_guard or PathGuard(layout.root)
    limit = max_file_size_bytes(config)
    files = _safe_files(layout, config, guard=guard)
    tree = [path.relative_to(layout.root).as_posix() for path in files[:max_entries]]
    extension_counts = Counter(path.suffix.lower() for path in files if path.suffix)
    languages = [
        {
            "name": LANGUAGE_BY_EXTENSION[extension],
            "files": count,
        }
        for extension, count in sorted(extension_counts.items())
        if extension in LANGUAGE_BY_EXTENSION
    ]
    dependencies = _detect_dependencies(layout, guard=guard, limit=limit)
    commands = _detect_commands(layout, dependencies)
    config_files = [
        path.relative_to(layout.root).as_posix()
        for path in files
        if path.name in KNOWN_CONFIG_FILES
    ]

    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "workspace": {
            "name": layout.root.name,
            "root": str(layout.root),
        },
        "tree": tree,
        "tree_truncated": len(files) > max_entries,
        "languages": languages,
        "dependencies": dependencies,
        "commands": commands,
        "config_files": config_files,
        "conventions": _detect_conventions(layout, files, dependencies),
    }


def _safe_files(
    layout: WorkspaceLayout,
    config: Mapping[str, Any],
    *,
    guard: PathGuard,
) -> list[Path]:
    files: list[Path] = []
    for path in iter_workspace_paths(
        layout.root,
        config,
        recursive=True,
        include_hidden=False,
        path_guard=guard,
    ):
        if not path.is_file():
            continue
        try:
            guarded = guard.resolve(path, operation=PathOperation.READ)
        except PathGuardError:
            continue
        if guarded.protected:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(layout.root).as_posix())


def _detect_dependencies(
    layout: WorkspaceLayout,
    *,
    guard: PathGuard,
    limit: int,
) -> list[dict[str, str]]:
    dependencies: list[dict[str, str]] = []
    pyproject = layout.root / "pyproject.toml"
    if _readable(pyproject, guard=guard, limit=limit):
        dependencies.extend(_dependencies_from_pyproject(pyproject))

    requirements = layout.root / "requirements.txt"
    if _readable(requirements, guard=guard, limit=limit):
        dependencies.extend(
            {
                "name": _requirement_name(line),
                "source": "requirements.txt",
            }
            for line in requirements.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )

    package_json = layout.root / "package.json"
    if _readable(package_json, guard=guard, limit=limit):
        dependencies.extend(_dependencies_from_package_json(package_json))

    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for dependency in dependencies:
        key = (dependency["name"].lower(), dependency["source"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(dependency)
    return sorted(unique, key=lambda item: (item["source"], item["name"].lower()))


def _dependencies_from_pyproject(path: Path) -> list[dict[str, str]]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return []

    dependencies: list[dict[str, str]] = []
    project = data.get("project", {})
    if isinstance(project, Mapping):
        for item in project.get("dependencies", []) or []:
            dependencies.append(
                {"name": _requirement_name(str(item)), "source": "pyproject.toml"}
            )

    tool_section = data.get("tool", {})
    poetry = (
        tool_section.get("poetry", {})
        if isinstance(tool_section, Mapping)
        else {}
    )
    if isinstance(poetry, Mapping):
        poetry_dependencies = poetry.get("dependencies", {})
        if isinstance(poetry_dependencies, Mapping):
            for name in poetry_dependencies:
                if str(name).lower() != "python":
                    dependencies.append(
                        {"name": str(name), "source": "pyproject.toml"}
                    )
        groups = poetry.get("group", {})
        if isinstance(groups, Mapping):
            for group in groups.values():
                group_dependencies = (
                    group.get("dependencies", {}) if isinstance(group, Mapping) else {}
                )
                if isinstance(group_dependencies, Mapping):
                    dependencies.extend(
                        {"name": str(name), "source": "pyproject.toml"}
                        for name in group_dependencies
                    )

    return dependencies


def _dependencies_from_package_json(path: Path) -> list[dict[str, str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    dependencies: list[dict[str, str]] = []
    for section in ("dependencies", "devDependencies"):
        values = data.get(section, {})
        if isinstance(values, Mapping):
            dependencies.extend(
                {"name": str(name), "source": f"package.json:{section}"}
                for name in values
            )
    return dependencies


def _detect_commands(
    layout: WorkspaceLayout,
    dependencies: list[dict[str, str]],
) -> dict[str, str | None]:
    names = {item["name"].lower() for item in dependencies}
    has_pyproject = (layout.root / "pyproject.toml").exists()
    package_scripts = _package_scripts(layout.root / "package.json")

    test = package_scripts.get("test")
    lint = package_scripts.get("lint")
    formatter = package_scripts.get("format")
    build = package_scripts.get("build")

    if test is None and has_pyproject:
        test = "poetry run pytest"
    if lint is None and ("ruff" in names or (layout.root / "ruff.toml").exists()):
        lint = "poetry run ruff check"
    if formatter is None and "ruff" in names:
        formatter = "poetry run ruff format"
    if formatter is None and "black" in names:
        formatter = "poetry run black ."
    if build is None and has_pyproject:
        build = "poetry build"

    return {
        "test": test,
        "lint": lint,
        "format": formatter,
        "build": build,
    }


def _package_scripts(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    scripts = data.get("scripts", {})
    if not isinstance(scripts, Mapping):
        return {}
    return {
        key: f"npm run {key}"
        for key in ("test", "lint", "format", "build")
        if key in scripts
    }


def _detect_conventions(
    layout: WorkspaceLayout,
    files: list[Path],
    dependencies: list[dict[str, str]],
) -> list[str]:
    conventions: list[str] = []
    names = {item["name"].lower() for item in dependencies}
    relative_paths = {path.relative_to(layout.root).as_posix() for path in files}

    if (layout.root / "src").is_dir():
        conventions.append("src-layout")
    if (layout.root / "tests").is_dir():
        conventions.append("tests-directory")
    if (layout.root / "pyproject.toml").exists():
        conventions.append("pyproject")
    if "typer" in names:
        conventions.append("typer-cli")
    if "rich" in names:
        conventions.append("rich-output")
    if "prompt-toolkit" in names or "prompt_toolkit" in names:
        conventions.append("prompt-toolkit")
    if any(path.startswith("docs/") for path in relative_paths):
        conventions.append("docs-directory")

    return conventions


def _readable(path: Path, *, guard: PathGuard, limit: int) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        guarded = guard.resolve(path, operation=PathOperation.READ)
    except PathGuardError:
        return False
    return not guarded.protected and path.stat().st_size <= limit


def _requirement_name(value: str) -> str:
    separators = ("==", ">=", "<=", "~=", "!=", ">", "<", "[", ";")
    name = value.strip()
    for separator in separators:
        if separator in name:
            name = name.split(separator, 1)[0]
    return name.strip()


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(parsed, 1)
