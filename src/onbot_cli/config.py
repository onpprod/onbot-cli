"""Contratos iniciais de configuracao."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConfigDefaults:
    """Defaults publicos que serao materializados na etapa de persistencia."""

    api_key_env: str = "OPENAI_API_KEY"
    max_steps: int = 20
    mode: str = "default"


DEFAULT_CONFIG = ConfigDefaults()
