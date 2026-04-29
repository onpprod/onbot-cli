"""Leitura e escrita de configuracao local e global permitida."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from onbot_cli.errors import ConfigurationError
from onbot_cli.security.redaction import is_sensitive_key, redact_data
from onbot_cli.workspace import WorkspaceLayout


@dataclass(frozen=True, slots=True)
class ConfigDefaults:
    """Defaults publicos materializados na persistencia local."""

    base_url: str = ""
    api_key_env: str = "OPENAI_API_KEY"
    model: str = ""
    temperature: float = 0.2
    max_steps: int = 20
    mode: str = "default"


DEFAULT_CONFIG = ConfigDefaults()

DEFAULT_CONFIG_DATA: dict[str, Any] = {
    "model": {
        "base_url": DEFAULT_CONFIG.base_url,
        "api_key_env": DEFAULT_CONFIG.api_key_env,
        "model": DEFAULT_CONFIG.model,
        "temperature": DEFAULT_CONFIG.temperature,
    },
    "agent": {
        "max_steps": DEFAULT_CONFIG.max_steps,
    },
    "workspace": {
        "max_file_size_kb": 256,
        "exclude": [
            ".git/",
            ".onbot-cli/logs/",
            "node_modules/",
            ".venv/",
        ],
    },
    "permissions": {
        "mode": DEFAULT_CONFIG.mode,
        "allow": [],
        "ask": [],
        "deny": [],
        "protected_paths": [
            ".git/",
            ".onbot-cli/config.yaml",
            ".onbot-cli/logs/",
            ".idea/",
            ".vscode/",
            ".env",
            "*.pem",
            "*.key",
        ],
    },
    "git": {
        "enabled": True,
        "require_confirmation_for_remote": True,
        "require_confirmation_for_destructive": True,
    },
    "tools": {
        "enabled": [],
        "disabled": [],
        "paths": [".onbot-cli/tools"],
    },
    "hooks": {
        "enabled": True,
        "paths": [".onbot-cli/hooks"],
    },
    "commands": {
        "paths": [".onbot-cli/commands"],
    },
}

GLOBAL_CONFIG_ALLOWED_KEYS = frozenset({"model", "agent", "preferences"})


@dataclass(frozen=True, slots=True)
class ConfigLoadResult:
    """Resultado previsivel do carregamento de configuracao."""

    config: Mapping[str, Any]
    local_path: Path
    global_path: Path | None
    local_created: bool
    global_loaded: bool
    redacted: Mapping[str, Any] = field(repr=False)


class ConfigManager:
    """Gerencia defaults, config local e config global nao sensivel."""

    def __init__(
        self,
        layout: WorkspaceLayout,
        *,
        global_config_path: Path | str | None = None,
    ) -> None:
        self.layout = layout
        self.local_path = layout.config_file
        self.global_config_path = (
            Path(global_config_path).expanduser()
            if global_config_path is not None
            else default_global_config_path()
        )

    def load(self) -> ConfigLoadResult:
        local_created = self.ensure_local_config()
        global_data = self._read_yaml_file(self.global_config_path, required=False)
        local_data = self._read_yaml_file(self.local_path, required=True)

        config = deepcopy(DEFAULT_CONFIG_DATA)
        global_loaded = bool(global_data)
        _deep_merge(config, _filter_global_config(global_data))
        _deep_merge(config, local_data)

        return ConfigLoadResult(
            config=config,
            local_path=self.local_path,
            global_path=self.global_config_path,
            local_created=local_created,
            global_loaded=global_loaded,
            redacted=redact_data(config),
        )

    def ensure_local_config(self) -> bool:
        if self.local_path.exists():
            return False

        self.write(DEFAULT_CONFIG_DATA)
        return True

    def write(self, config: Mapping[str, Any]) -> None:
        self.local_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = yaml.safe_dump(
            dict(config),
            sort_keys=False,
            allow_unicode=False,
            default_flow_style=False,
        )
        self.local_path.write_text(serialized, encoding="utf-8")

    def _read_yaml_file(self, path: Path, *, required: bool) -> dict[str, Any]:
        if not path.exists():
            if required:
                raise ConfigurationError(
                    "Configuracao local nao encontrada.",
                    hint=f"Arquivo esperado: {path}",
                )
            return {}

        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return {}

        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise ConfigurationError(
                "Configuracao invalida.",
                hint=f"Revise o YAML em: {path}",
            ) from exc

        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ConfigurationError(
                "Configuracao invalida.",
                hint=f"O arquivo precisa conter um objeto YAML: {path}",
            )

        return data


def default_global_config_path() -> Path:
    appdata = _env_path("APPDATA")
    if appdata is not None:
        return appdata / "onbot-cli" / "config.yaml"

    xdg_config_home = _env_path("XDG_CONFIG_HOME")
    if xdg_config_home is not None:
        return xdg_config_home / "onbot-cli" / "config.yaml"

    return Path.home() / ".config" / "onbot-cli" / "config.yaml"


def safe_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    return redact_data(config)


def _env_path(name: str) -> Path | None:
    import os

    value = os.environ.get(name)
    if not value:
        return None
    return Path(value).expanduser()


def _deep_merge(target: dict[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in source.items():
        if (
            key in target
            and isinstance(target[key], dict)
            and isinstance(value, Mapping)
        ):
            _deep_merge(target[key], value)
        else:
            target[key] = deepcopy(value)
    return target


def _filter_global_config(config: Mapping[str, Any]) -> dict[str, Any]:
    filtered: dict[str, Any] = {}
    for key, value in config.items():
        if key not in GLOBAL_CONFIG_ALLOWED_KEYS or is_sensitive_key(str(key)):
            continue
        if isinstance(value, Mapping):
            clean_value = _filter_sensitive_mapping(value)
            if clean_value:
                filtered[key] = clean_value
        else:
            filtered[key] = deepcopy(value)
    return filtered


def _filter_sensitive_mapping(config: Mapping[str, Any]) -> dict[str, Any]:
    filtered: dict[str, Any] = {}
    for key, value in config.items():
        if is_sensitive_key(str(key)):
            continue
        if isinstance(value, Mapping):
            filtered[key] = _filter_sensitive_mapping(value)
        else:
            filtered[key] = deepcopy(value)
    return filtered
