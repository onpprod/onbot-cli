import tomllib
from pathlib import Path

from onbot_cli import __version__


def test_project_version_matches_package_version() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == __version__


def test_onbot_cli_script_entrypoint_is_configured() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["onbot-cli"] == "onbot_cli.cli:app"
