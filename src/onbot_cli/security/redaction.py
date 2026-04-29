"""Redacao basica de segredos para logs e exibicao controlada."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


REDACTED = "***REDACTED***"

SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "access_key",
    "secret",
    "token",
    "authorization",
    "password",
    "passwd",
    "credential",
)

SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?key|token|authorization|password|secret)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")
ENV_LINE_RE = re.compile(
    r"(?im)^([A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|AUTHORIZATION)[A-Z0-9_]*=).+$"
)


def is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    if normalized.endswith("_env") or normalized.endswith("_variable"):
        return False
    return (
        normalized == ".env"
        or normalized.endswith("/.env")
        or normalized.endswith("\\.env")
        or any(part in normalized for part in SENSITIVE_KEY_PARTS)
    )


def redact_data(value: Any) -> Any:
    """Recursively redact obvious secrets while preserving data shape."""

    if isinstance(value, Mapping):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            if is_sensitive_key(str(key)):
                redacted[key] = REDACTED
            else:
                redacted[key] = redact_data(item)
        return redacted

    if isinstance(value, tuple):
        return tuple(redact_data(item) for item in value)

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_data(item) for item in value]

    if isinstance(value, str):
        return redact_string(value)

    return value


def redact_string(value: str) -> str:
    redacted = ENV_LINE_RE.sub(r"\1" + REDACTED, value)
    redacted = BEARER_RE.sub("Bearer " + REDACTED, redacted)
    redacted = SENSITIVE_ASSIGNMENT_RE.sub(r"\1\2" + REDACTED, redacted)
    redacted = OPENAI_KEY_RE.sub(REDACTED, redacted)
    return redacted
