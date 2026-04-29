"""Prompt e autocomplete da CLI interativa."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document


class SlashCommandCompleter(Completer):
    """Autocomplete inicial para comandos internos e customizados simples."""

    def __init__(
        self,
        commands: Iterable[str],
        *,
        custom_command_provider: Callable[[], Iterable[str]] | None = None,
    ) -> None:
        self._commands = tuple(sorted(_normalize(command) for command in commands))
        self._custom_command_provider = custom_command_provider

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/") or " " in text:
            return

        current = text
        for command in self._all_commands():
            if command.startswith(current):
                yield Completion(command, start_position=-len(current))

    def _all_commands(self) -> tuple[str, ...]:
        commands = set(self._commands)
        if self._custom_command_provider is not None:
            commands.update(
                _normalize(command)
                for command in self._custom_command_provider()
                if command
            )
        return tuple(sorted(commands))


def _normalize(command: str) -> str:
    normalized = command.strip()
    if not normalized:
        return normalized
    return normalized if normalized.startswith("/") else f"/{normalized}"
