from __future__ import annotations

import sys
from pathlib import Path

import pytest

from onbot_cli.security.approval import ApprovalService
from onbot_cli.security.commands import CommandPolicy, CommandRisk, CommandRunner
from onbot_cli.security.paths import PathGuard, PathGuardError, PathOperation
from onbot_cli.security.permissions import (
    PermissionAction,
    PermissionEffect,
    PermissionManager,
    PermissionRequest,
)
from onbot_cli.storage.logs import AuditLogger
from onbot_cli.storage.sessions import SessionStore
from onbot_cli.workspace import WorkspaceManager


def test_path_guard_resolves_workspace_paths_and_protected_patterns(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "src").mkdir()
    (workspace / "src" / "app.py").write_text("print('ok')", encoding="utf-8")
    (workspace / ".env").write_text("TOKEN=secret", encoding="utf-8")
    (workspace / "cert.pem").write_text("secret", encoding="utf-8")

    guard = PathGuard(workspace)

    resolved = guard.resolve("src/app.py")
    env_file = guard.resolve(".env")
    key_file = guard.resolve("cert.pem")

    assert resolved.relative_posix == "src/app.py"
    assert env_file.protected is True
    assert env_file.protected_pattern == ".env"
    assert key_file.protected is True
    assert key_file.protected_pattern == "*.pem"


def test_path_guard_denies_traversal_outside_workspace_and_external_symlinks(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("fora", encoding="utf-8")

    guard = PathGuard(workspace)

    with pytest.raises(PathGuardError):
        guard.resolve("../outside.txt", operation=PathOperation.READ)

    with pytest.raises(PathGuardError):
        guard.resolve(outside)

    external_dir = tmp_path / "external"
    external_dir.mkdir()
    (external_dir / "secret.txt").write_text("fora", encoding="utf-8")
    link = workspace / "link"
    try:
        link.symlink_to(external_dir, target_is_directory=True)
    except OSError:
        return

    with pytest.raises(PathGuardError):
        guard.resolve("link/secret.txt")


def test_permission_manager_modes_and_protected_paths() -> None:
    config = _permissions_config("plan")
    manager = PermissionManager(config)

    assert manager.evaluate(_request(PermissionAction.FILE_READ)).allowed
    assert manager.evaluate(_request(PermissionAction.FILE_WRITE)).denied
    assert manager.evaluate(_request(PermissionAction.COMMAND)).allowed

    config["permissions"]["mode"] = "default"
    assert manager.evaluate(_request(PermissionAction.FILE_WRITE)).requires_approval

    config["permissions"]["mode"] = "accept_edits"
    assert manager.evaluate(_request(PermissionAction.FILE_WRITE)).allowed
    assert manager.evaluate(
        _request(PermissionAction.FILE_WRITE, protected=True)
    ).requires_approval

    config["permissions"]["mode"] = "trusted"
    assert manager.evaluate(
        _request(PermissionAction.COMMAND, risk="DANGEROUS", mutates=True)
    ).allowed

    config["permissions"]["mode"] = "locked"
    assert manager.evaluate(_request(PermissionAction.FILE_READ)).denied
    manager.add_rule(PermissionEffect.ALLOW, PermissionAction.FILE_READ, "README.md")
    assert manager.evaluate(
        PermissionRequest(action=PermissionAction.FILE_READ, target="README.md")
    ).allowed


def test_permission_rules_respect_deny_ask_allow_precedence() -> None:
    config = _permissions_config("trusted")
    manager = PermissionManager(config)
    manager.add_rule(PermissionEffect.ALLOW, PermissionAction.COMMAND, "poetry *")
    manager.add_rule(PermissionEffect.ASK, PermissionAction.COMMAND, "poetry run pytest")
    manager.add_rule(
        PermissionEffect.DENY,
        PermissionAction.COMMAND,
        "poetry run pytest -q",
    )

    denied = manager.evaluate(
        PermissionRequest(action=PermissionAction.COMMAND, target="poetry run pytest -q")
    )
    asked = manager.evaluate(
        PermissionRequest(action=PermissionAction.COMMAND, target="poetry run pytest")
    )
    allowed = manager.evaluate(
        PermissionRequest(action=PermissionAction.COMMAND, target="poetry install")
    )

    assert denied.decision == PermissionEffect.DENY
    assert asked.decision == PermissionEffect.ASK
    assert allowed.decision == PermissionEffect.ALLOW


def test_approval_service_turns_ask_into_explicit_allow() -> None:
    manager = PermissionManager(_permissions_config("default"))
    request = PermissionRequest(
        action=PermissionAction.FILE_WRITE,
        target="src/app.py",
        risk="CAUTION",
        mutates=True,
    )
    approval = ApprovalService(input_provider=lambda _: "yes")

    final = manager.authorize(request, approval_service=approval)

    assert final.allowed
    assert final.reason == "usuario aprovou"


def test_command_policy_classifies_safe_dangerous_and_blocked_commands() -> None:
    policy = CommandPolicy()

    assert policy.classify("poetry run pytest").risk == CommandRisk.SAFE
    assert policy.classify("rm -rf /").risk == CommandRisk.BLOCKED
    assert policy.classify("format c:").risk == CommandRisk.BLOCKED
    assert policy.classify("shutdown /s /t 0").risk == CommandRisk.BLOCKED

    reset = policy.classify("git reset --hard")
    assert reset.risk == CommandRisk.DANGEROUS
    assert reset.mutates is True


def test_command_runner_executes_allowed_commands_and_blocks_forbidden_ones(
    tmp_path: Path,
) -> None:
    layout = WorkspaceManager(tmp_path).ensure_workspace().layout
    session_store = SessionStore(layout)
    session = session_store.create("stage04")
    audit = AuditLogger(layout)
    config = _permissions_config("trusted")
    manager = PermissionManager(
        config,
        audit_logger=audit,
        session_store=session_store,
        session_id=session.id,
    )
    runner = CommandRunner(
        tmp_path,
        manager,
        audit_logger=audit,
        session_store=session_store,
        session_id=session.id,
    )

    result = runner.run("echo stage04", timeout=10)
    blocked = runner.run("shutdown /s /t 0", timeout=10)

    events = audit.read_audit_events()
    loaded_session = session_store.load(session.id)

    assert result.succeeded
    assert "stage04" in result.stdout
    assert blocked.status == "blocked"
    assert blocked.exit_code is None
    assert any(event["type"] == "permission_decision" for event in events)
    assert any(event["type"] == "command_execution" for event in events)
    assert [command["command"] for command in loaded_session.commands] == [
        "echo stage04",
        "shutdown /s /t 0",
    ]


def test_command_runner_reports_timeout(tmp_path: Path) -> None:
    config = _permissions_config("trusted")
    runner = CommandRunner(tmp_path, PermissionManager(config))

    result = runner.run(
        f'"{sys.executable}" -c "import time; time.sleep(2)"',
        timeout=0.1,
    )

    assert result.status == "timeout"
    assert result.timed_out is True


def _permissions_config(mode: str) -> dict[str, object]:
    return {
        "permissions": {
            "mode": mode,
            "allow": [],
            "ask": [],
            "deny": [],
            "protected_paths": [".git/", ".env", "*.pem", "*.key"],
        }
    }


def _request(
    action: PermissionAction,
    *,
    target: str = "target",
    risk: str = "SAFE",
    protected: bool = False,
    mutates: bool = False,
) -> PermissionRequest:
    return PermissionRequest(
        action=action,
        target=target,
        risk=risk,
        protected=protected,
        mutates=mutates,
    )
