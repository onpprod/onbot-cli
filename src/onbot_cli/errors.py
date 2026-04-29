"""Excecoes e mensagens padronizadas da aplicacao."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ErrorMessage:
    """Mensagem estruturada para exibicao controlada na CLI."""

    code: str
    message: str
    hint: str | None = None


class ApplicationError(Exception):
    """Erro base de dominio com codigo e exit code previsiveis."""

    code = "application_error"
    exit_code = 1

    def __init__(
        self,
        message: str,
        *,
        hint: str | None = None,
        code: str | None = None,
        exit_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        if code is not None:
            self.code = code
        if exit_code is not None:
            self.exit_code = exit_code

    def to_message(self) -> ErrorMessage:
        return ErrorMessage(code=self.code, message=self.message, hint=self.hint)


class WorkspaceError(ApplicationError):
    """Erro ao resolver ou validar o workspace atual."""

    code = "workspace_error"


class ConfigurationError(ApplicationError):
    """Erro relacionado a configuracao da aplicacao."""

    code = "configuration_error"


class StorageError(ApplicationError):
    """Erro relacionado a persistencia local da aplicacao."""

    code = "storage_error"
