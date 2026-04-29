from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from onbot_cli.agent.context import ContextBundle, ContextSnippet
from onbot_cli.agent.controller import AgentController
from onbot_cli.agent.messages import AgentMessage, AgentToolCall
from onbot_cli.agent.planner import Planner
from onbot_cli.agent.workflows import WorkflowEngine
from onbot_cli.app import bootstrap_application
from onbot_cli.llm import (
    LLMConfigurationError,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
    OpenAICompatibleClient,
    OpenAICompatibleConfig,
)
from onbot_cli.storage.sessions import SessionStore


class FakeStreamingResponse:
    def __init__(self, lines: list[bytes]) -> None:
        self.lines = lines
        self.closed = False

    def __iter__(self):
        return iter(self.lines)

    def close(self) -> None:
        self.closed = True


class FakeLLM:
    def __init__(self, chunks: list[str] | None = None) -> None:
        self.chunks = chunks or ["resposta ", "final"]
        self.requests: list[LLMRequest] = []
        self.complete_calls = 0

    def stream(self, request: LLMRequest):
        self.requests.append(request)
        for index, chunk in enumerate(self.chunks):
            finish_reason = "stop" if index == len(self.chunks) - 1 else None
            yield LLMStreamChunk(content=chunk, finish_reason=finish_reason)

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.complete_calls += 1
        return LLMResponse(content="fallback completo")


def test_openai_compatible_client_streams_sse_and_uses_env_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_OPENAI_KEY", "sk-test-secret-value")
    captured: dict[str, Any] = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["authorization"] = request.headers["Authorization"]
        return FakeStreamingResponse(
            [
                b'data: {"model":"fake","choices":[{"delta":{"content":"ola "}}]}\n',
                b'data: {"choices":[{"delta":{"content":"mundo"},"finish_reason":"stop"}]}\n',
                b"data: [DONE]\n",
            ]
        )

    config = OpenAICompatibleConfig.from_config(
        {
            "model": {
                "base_url": "https://example.test/v1",
                "api_key_env": "TEST_OPENAI_KEY",
                "model": "fake-model",
                "temperature": 0.1,
            }
        }
    )
    client = OpenAICompatibleClient(config, opener=opener)

    chunks = list(
        client.stream(
            LLMRequest(messages=[{"role": "user", "content": "ola"}])
        )
    )

    assert "".join(chunk.content for chunk in chunks) == "ola mundo"
    assert chunks[-1].finish_reason == "stop"
    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["payload"]["stream"] is True
    assert captured["payload"]["model"] == "fake-model"
    assert captured["authorization"] == "Bearer sk-test-secret-value"
    assert "sk-test-secret-value" not in repr(config)


def test_openai_config_reports_missing_secret_without_exposing_value() -> None:
    config = OpenAICompatibleConfig.from_config(
        {"model": {"api_key_env": "MISSING_KEY", "model": "fake"}}
    )
    inline = OpenAICompatibleConfig.from_config(
        {"model": {"api_key": "plain-secret", "model": "fake"}}
    )

    with pytest.raises(LLMConfigurationError) as raised:
        config.validate()

    assert "MISSING_KEY" in (raised.value.hint or "")
    assert "plain-secret" not in repr(inline)


def test_agent_messages_support_tool_calls_and_results() -> None:
    tool_call = AgentToolCall(
        id="call-1",
        name="read_file",
        arguments={"path": "README.md"},
    )
    assistant = AgentMessage.assistant("", tool_calls=[tool_call])
    result = AgentMessage.tool_result(
        "conteudo",
        tool_call_id="call-1",
        name="read_file",
    )

    payload = assistant.to_llm_dict()
    arguments = payload["tool_calls"][0]["function"]["arguments"]

    assert payload["role"] == "assistant"
    assert json.loads(arguments) == {"path": "README.md"}
    assert result.to_llm_dict()["tool_call_id"] == "call-1"


def test_planner_and_workflow_engine_create_structured_development_paths() -> None:
    context = ContextBundle(
        summary={
            "commands": {"test": "poetry run pytest", "lint": "poetry run ruff check"},
            "config_files": ["pyproject.toml"],
        },
        snippets=(
            ContextSnippet(
                path="src/onbot_cli/app.py",
                start_line=1,
                end_line=2,
                content="def app(): pass",
                score=4,
            ),
        ),
        total_chars=14,
    )
    engine = WorkflowEngine()
    workflow = engine.select("corrigir bug no app")
    result = engine.execute(workflow, objective="corrigir bug no app")
    plan = Planner().create_plan(
        "corrigir bug no app",
        context=context,
        workflow_name=workflow.name,
    )

    assert workflow.name == "bugfix"
    assert [step.step_id for step in result.step_results] == [
        "collect",
        "locate",
        "investigate",
        "fix",
        "regression",
        "explain",
    ]
    assert plan.objective == "corrigir bug no app"
    assert "src" in plan.likely_areas
    assert "poetry run pytest" in plan.validations


def test_agent_controller_builds_context_invokes_tool_streams_and_persists(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    bootstrap = bootstrap_application(tmp_path)
    fake_llm = FakeLLM(["ola ", "mundo"])
    streamed: list[str] = []
    plans: list[dict[str, Any]] = []

    controller = AgentController.from_bootstrap(bootstrap, llm_client=fake_llm)
    result = controller.run(
        "implementar feature nova",
        stream_callback=streamed.append,
        plan_callback=plans.append,
    )

    session = SessionStore(bootstrap.layout).load(bootstrap.session_id)
    action_types = [action["type"] for action in session.actions]

    assert result.status == "completed"
    assert result.streamed is True
    assert result.content == "ola mundo"
    assert streamed == ["ola ", "mundo"]
    assert plans[0]["objetivo"] == "implementar feature nova"
    assert result.workflow_result is not None
    assert result.workflow_result.workflow.name == "feature"
    assert session.tool_calls[0]["name"] == "project_summary"
    assert "agent_plan" in action_types
    assert "workflow" in action_types
    assert session.messages[-1]["role"] == "assistant"
    assert session.messages[-1]["content"] == "ola mundo"
    assert fake_llm.requests[0].messages[0]["role"] == "system"


def test_agent_controller_returns_clear_fallback_when_llm_is_not_configured(
    tmp_path: Path,
) -> None:
    bootstrap = bootstrap_application(tmp_path)
    controller = AgentController.from_bootstrap(bootstrap)

    result = controller.run("documentar README")

    assert result.status == "completed"
    assert result.streamed is False
    assert "modelo LLM nao esta configurado" in result.content
    assert result.plan is not None
    assert result.workflow_result is not None
    assert result.workflow_result.workflow.name == "documentation"


def test_agent_controller_stops_when_max_steps_is_exceeded(tmp_path: Path) -> None:
    bootstrap = bootstrap_application(tmp_path)
    bootstrap.config["agent"]["max_steps"] = 2
    fake_llm = FakeLLM()
    controller = AgentController.from_bootstrap(bootstrap, llm_client=fake_llm)

    result = controller.run("implementar algo")

    assert result.status == "max_steps_exceeded"
    assert "agent.max_steps=2" in result.content
    assert result.steps_taken == 3
    assert fake_llm.requests == []
