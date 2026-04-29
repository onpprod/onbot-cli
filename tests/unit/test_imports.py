import importlib

from typer import Typer

import onbot_cli
from onbot_cli.cli import app


def test_package_import_has_version() -> None:
    assert onbot_cli.__version__ == "0.1.0"


def test_typer_app_is_instantiable() -> None:
    assert isinstance(app, Typer)


def test_foundation_modules_import_without_side_effects() -> None:
    modules = [
        "onbot_cli.agent",
        "onbot_cli.commands",
        "onbot_cli.config",
        "onbot_cli.git",
        "onbot_cli.hooks",
        "onbot_cli.llm",
        "onbot_cli.security",
        "onbot_cli.storage",
        "onbot_cli.tools",
        "onbot_cli.ui",
        "onbot_cli.workspace",
    ]

    for module in modules:
        assert importlib.import_module(module)
