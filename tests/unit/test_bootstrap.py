from pathlib import Path

from typer.testing import CliRunner

from onbot_cli.app import bootstrap_application
from onbot_cli.cli import app


def test_bootstrap_resolves_workspace(tmp_path: Path) -> None:
    result = bootstrap_application(tmp_path)

    assert result.workspace.root == tmp_path.resolve()
    assert result.context.workspace == result.workspace
    assert result.context.metadata["stage"] == "foundation"


def test_cli_bootstrap_outputs_current_workspace(tmp_path: Path) -> None:
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path):
        current = Path.cwd().resolve()
        result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "onbot-cli 0.1.0" in result.output
    assert f"Workspace: {current}" in result.output
    assert "Modo interativo: preparado" in result.output
