"""Cliente HTTP para provedores OpenAI-compatible."""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from onbot_cli.llm.client import (
    LLMCancelledError,
    LLMConfigurationError,
    LLMRequest,
    LLMResponse,
    LLMResponseError,
    LLMStreamChunk,
    LLMTransportError,
)


DEFAULT_BASE_URL = "https://api.openai.com/v1"
SUPPORTED_GENERATION_KEYS = frozenset(
    {
        "max_tokens",
        "top_p",
        "frequency_penalty",
        "presence_penalty",
        "stop",
        "seed",
        "response_format",
    }
)


@dataclass(frozen=True, slots=True)
class OpenAICompatibleConfig:
    """Configuracao materializada sem expor segredo em repr."""

    base_url: str = DEFAULT_BASE_URL
    api_key_env: str = "OPENAI_API_KEY"
    model: str = ""
    temperature: float = 0.2
    generation_params: Mapping[str, Any] = field(default_factory=dict)
    timeout: float = 60
    _api_key: str | None = field(default=None, repr=False)

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "OpenAICompatibleConfig":
        section = config.get("model", {})
        if not isinstance(section, Mapping):
            section = {}

        api_key_env = str(section.get("api_key_env") or "OPENAI_API_KEY")
        inline_api_key = section.get("api_key")
        api_key = (
            str(inline_api_key)
            if inline_api_key is not None and str(inline_api_key)
            else os.environ.get(api_key_env)
        )
        base_url = str(section.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        model = str(section.get("model") or "")
        temperature = _float_value(section.get("temperature"), default=0.2)
        timeout = _float_value(section.get("timeout"), default=60)

        generation_params: dict[str, Any] = {}
        nested = section.get("generation_params", {})
        if isinstance(nested, Mapping):
            generation_params.update(
                {
                    str(key): value
                    for key, value in nested.items()
                    if value is not None and str(key) in SUPPORTED_GENERATION_KEYS
                }
            )
        for key in SUPPORTED_GENERATION_KEYS:
            if key in section and section[key] is not None:
                generation_params[key] = section[key]

        return cls(
            base_url=base_url,
            api_key_env=api_key_env,
            model=model,
            temperature=temperature,
            generation_params=generation_params,
            timeout=timeout,
            _api_key=api_key,
        )

    @property
    def api_key(self) -> str | None:
        return self._api_key

    @property
    def configured(self) -> bool:
        return bool(self.model and self.api_key)

    @property
    def chat_completions_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def validate(self) -> None:
        if not self.model:
            raise LLMConfigurationError(
                "Modelo LLM nao configurado.",
                hint="Defina model.model em .onbot-cli/config.yaml.",
            )
        if not self.api_key:
            raise LLMConfigurationError(
                "Chave de API do provedor nao encontrada.",
                hint=f"Defina a variavel de ambiente {self.api_key_env}.",
            )


class OpenAICompatibleClient:
    """Cliente sincrono para `/chat/completions` com streaming SSE."""

    def __init__(
        self,
        config: OpenAICompatibleConfig,
        *,
        opener: Any | None = None,
        cancellation_event: threading.Event | None = None,
    ) -> None:
        self.config = config
        self._opener = opener or urllib.request.urlopen
        self._cancellation_event = cancellation_event

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "OpenAICompatibleClient":
        return cls(OpenAICompatibleConfig.from_config(config))

    def complete(self, request: LLMRequest) -> LLMResponse:
        payload = self._payload(request, stream=False)
        data = self._post_json(payload)
        choices = data.get("choices", [])
        if not choices:
            raise LLMResponseError(
                "Resposta LLM sem escolhas.",
                hint="O provedor retornou um payload sem choices.",
            )

        first = choices[0]
        message = first.get("message", {}) if isinstance(first, Mapping) else {}
        content = str(message.get("content") or "")
        return LLMResponse(
            content=content,
            model=str(data.get("model") or request.model or self.config.model),
            raw=data,
            finish_reason=_finish_reason(first),
        )

    def stream(self, request: LLMRequest) -> Iterable[LLMStreamChunk]:
        payload = self._payload(request, stream=True)
        response = self._open(payload)
        model: str | None = None
        try:
            for raw_line in response:
                self._raise_if_cancelled()
                line = _decode_line(raw_line).strip()
                if not line or not line.startswith("data:"):
                    continue
                data_text = line.removeprefix("data:").strip()
                if data_text == "[DONE]":
                    break
                try:
                    data = json.loads(data_text)
                except json.JSONDecodeError as exc:
                    raise LLMResponseError(
                        "Chunk de streaming invalido.",
                        hint="O provedor retornou SSE que nao e JSON valido.",
                    ) from exc

                if model is None and data.get("model"):
                    model = str(data.get("model"))
                choice = _first_choice(data)
                if choice is None:
                    continue
                delta = choice.get("delta", {})
                content = str(delta.get("content") or "") if isinstance(delta, Mapping) else ""
                finish_reason = _finish_reason(choice)
                if content or finish_reason:
                    yield LLMStreamChunk(
                        content=content,
                        model=model or request.model or self.config.model,
                        finish_reason=finish_reason,
                        raw=data,
                    )
                if finish_reason:
                    break
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    def _payload(self, request: LLMRequest, *, stream: bool) -> dict[str, Any]:
        self.config.validate()
        payload: dict[str, Any] = {
            "model": request.model or self.config.model,
            "messages": list(request.messages),
            "stream": stream,
            "temperature": (
                request.temperature
                if request.temperature is not None
                else self.config.temperature
            ),
        }
        payload.update(dict(self.config.generation_params))
        payload.update(
            {
                str(key): value
                for key, value in request.generation_params.items()
                if value is not None
            }
        )
        return payload

    def _post_json(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        response = self._open(payload)
        try:
            body = response.read()
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
        try:
            data = json.loads(_decode_line(body))
        except json.JSONDecodeError as exc:
            raise LLMResponseError(
                "Resposta LLM invalida.",
                hint="O provedor retornou JSON invalido.",
            ) from exc
        if not isinstance(data, dict):
            raise LLMResponseError("Resposta LLM invalida.")
        _raise_provider_error(data)
        return data

    def _open(self, payload: Mapping[str, Any]) -> Any:
        self._raise_if_cancelled()
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        request = urllib.request.Request(
            self.config.chat_completions_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            return self._opener(request, timeout=self.config.timeout)
        except urllib.error.HTTPError as exc:
            detail = _http_error_detail(exc)
            raise LLMTransportError(
                "Erro HTTP ao chamar provedor LLM.",
                hint=detail,
            ) from exc
        except urllib.error.URLError as exc:
            raise LLMTransportError(
                "Falha de transporte ao chamar provedor LLM.",
                hint=str(exc.reason),
            ) from exc
        except TimeoutError as exc:
            raise LLMTransportError(
                "Tempo limite ao chamar provedor LLM.",
                hint="Ajuste model.timeout ou tente novamente.",
            ) from exc

    def _raise_if_cancelled(self) -> None:
        if self._cancellation_event is not None and self._cancellation_event.is_set():
            raise LLMCancelledError("Chamada LLM cancelada.")


def _float_value(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _decode_line(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _first_choice(data: Mapping[str, Any]) -> Mapping[str, Any] | None:
    choices = data.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    return first if isinstance(first, Mapping) else None


def _finish_reason(choice: Any) -> str | None:
    if isinstance(choice, Mapping) and choice.get("finish_reason") is not None:
        return str(choice.get("finish_reason"))
    return None


def _raise_provider_error(data: Mapping[str, Any]) -> None:
    error = data.get("error")
    if not isinstance(error, Mapping):
        return
    message = str(error.get("message") or "Erro retornado pelo provedor LLM.")
    error_type = str(error.get("type") or "provider_error")
    raise LLMResponseError(message, hint=error_type)


def _http_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read()
    except Exception:
        raw = b""
    if not raw:
        return f"HTTP {exc.code}"
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return f"HTTP {exc.code}"
    error = data.get("error") if isinstance(data, Mapping) else None
    if isinstance(error, Mapping) and error.get("message"):
        return f"HTTP {exc.code}: {error['message']}"
    return f"HTTP {exc.code}"
