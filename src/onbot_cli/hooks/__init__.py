"""Fronteira de hooks configurados pelo usuario."""
"""Interfaces de hooks do onbot-cli."""

from onbot_cli.hooks.models import (
    HookDispatcher,
    HookEvent,
    HookResult,
    NoopHookDispatcher,
)

__all__ = [
    "HookDispatcher",
    "HookEvent",
    "HookResult",
    "NoopHookDispatcher",
]
