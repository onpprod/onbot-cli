import json
from pathlib import Path

from onbot_cli.config import ConfigManager
from onbot_cli.security.redaction import REDACTED, redact_data
from onbot_cli.storage.cache import ProjectSummaryCache
from onbot_cli.storage.history import CommandHistory, CommandHistoryEntry
from onbot_cli.storage.logs import AuditLogger
from onbot_cli.storage.models import MessageRecord
from onbot_cli.storage.sessions import SessionStore
from onbot_cli.workspace import WorkspaceManager


def test_workspace_manager_creates_expected_tree_idempotently(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path)

    first = manager.ensure_workspace()
    second = manager.ensure_workspace()

    expected = {
        ".onbot-cli",
        ".onbot-cli/sessions",
        ".onbot-cli/history",
        ".onbot-cli/logs",
        ".onbot-cli/cache",
        ".onbot-cli/tools",
        ".onbot-cli/hooks",
        ".onbot-cli/commands",
    }
    actual = {
        directory.relative_to(tmp_path).as_posix()
        for directory in first.layout.directories
    }

    assert actual == expected
    assert all(directory.is_dir() for directory in first.layout.directories)
    assert second.created_directories == ()


def test_config_manager_merges_defaults_global_and_local(tmp_path: Path) -> None:
    layout = WorkspaceManager(tmp_path).ensure_workspace().layout
    global_path = tmp_path / "global.yaml"

    global_path.write_text(
        "\n".join(
            [
                "model:",
                "  base_url: https://llm.example.test/v1",
                "  api_key: should-not-load",
                "  api_key_env: GLOBAL_API_KEY",
                "agent:",
                "  max_steps: 30",
                "permissions:",
                "  mode: trusted",
            ]
        ),
        encoding="utf-8",
    )
    layout.config_file.write_text(
        "\n".join(
            [
                "model:",
                "  model: local-model",
                "agent:",
                "  max_steps: 7",
            ]
        ),
        encoding="utf-8",
    )

    result = ConfigManager(layout, global_config_path=global_path).load()

    assert result.global_loaded is True
    assert result.local_created is False
    assert result.config["model"]["base_url"] == "https://llm.example.test/v1"
    assert result.config["model"]["model"] == "local-model"
    assert result.config["model"]["api_key_env"] == "GLOBAL_API_KEY"
    assert "api_key" not in result.config["model"]
    assert result.config["agent"]["max_steps"] == 7
    assert result.config["permissions"]["mode"] == "default"


def test_config_manager_writes_defaults_without_overwriting_existing(
    tmp_path: Path,
) -> None:
    layout = WorkspaceManager(tmp_path).ensure_workspace().layout
    manager = ConfigManager(layout, global_config_path=tmp_path / "missing.yaml")

    first = manager.load()
    before = layout.config_file.read_text(encoding="utf-8")
    second = manager.load()
    after = layout.config_file.read_text(encoding="utf-8")

    assert first.local_created is True
    assert second.local_created is False
    assert before == after
    assert first.config["workspace"]["max_file_size_kb"] == 256


def test_session_store_creates_updates_and_reads_session(tmp_path: Path) -> None:
    layout = WorkspaceManager(tmp_path).ensure_workspace().layout
    store = SessionStore(layout)

    session = store.create("session-test")
    store.append_message(
        session.id,
        MessageRecord(role="user", content="Use api_key=plain-secret"),
    )
    loaded = store.load(session.id)

    assert loaded.id == "session-test"
    assert loaded.messages[0]["role"] == "user"
    assert "plain-secret" not in loaded.messages[0]["content"]
    assert REDACTED in loaded.messages[0]["content"]


def test_history_and_audit_are_append_only_and_redacted(tmp_path: Path) -> None:
    layout = WorkspaceManager(tmp_path).ensure_workspace().layout
    history = CommandHistory(layout)
    audit = AuditLogger(layout)

    history.append(CommandHistoryEntry(command="run token=command-secret"))
    audit.record_event(
        "tool_call",
        {
            "api_key": "audit-secret",
            "authorization": "Bearer bearer-secret",
            ".env": "OPENAI_API_KEY=env-secret",
        },
    )

    history_text = (layout.history_dir / "commands.jsonl").read_text(encoding="utf-8")
    audit_text = (layout.logs_dir / "audit.jsonl").read_text(encoding="utf-8")
    operational_text = (layout.logs_dir / "onbot-cli.log").read_text(
        encoding="utf-8"
    )

    assert "command-secret" not in history_text
    assert "audit-secret" not in audit_text
    assert "bearer-secret" not in audit_text
    assert "env-secret" not in audit_text
    assert REDACTED in history_text
    assert REDACTED in audit_text
    assert REDACTED in operational_text


def test_project_summary_cache_contract(tmp_path: Path) -> None:
    layout = WorkspaceManager(tmp_path).ensure_workspace().layout
    cache = ProjectSummaryCache(layout)

    assert cache.ensure() is True
    initial = cache.read()
    cache.write({**initial, "languages": ["Python"]})
    updated = cache.read()

    assert updated["schema_version"] == 1
    assert updated["workspace"]["root"] == str(tmp_path.resolve())
    assert updated["languages"] == ["Python"]
    assert updated["updated_at"] is not None


def test_redact_data_handles_nested_secrets() -> None:
    redacted = redact_data(
        {
            "model": {"api_key_env": "OPENAI_API_KEY"},
            "api_key": "secret",
            "nested": ["Authorization: Bearer secret-token"],
        }
    )

    assert redacted["model"]["api_key_env"] == "OPENAI_API_KEY"
    assert redacted["api_key"] == REDACTED
    assert "secret-token" not in redacted["nested"][0]


def test_audit_events_can_be_read_back(tmp_path: Path) -> None:
    layout = WorkspaceManager(tmp_path).ensure_workspace().layout
    audit = AuditLogger(layout)

    written = audit.record_event("session_start", {"ok": True}, session_id="s1")
    read = audit.read_audit_events()

    assert read == [json.loads(json.dumps(written, sort_keys=True))]
