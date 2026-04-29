from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from onbot_cli.agent.context import ContextBundle, ContextSnippet
from onbot_cli.agent.controller import AgentController
from onbot_cli.agent.messages import AgentMessage, AgentToolCall
from onbot_cli.agent.planner import Planner
from onbot_cli.agent.workflows import WorkflowEngine
from onbot_cli.app import bootstrap_application
from onbot_cli.commands.internal import create_default_router
from onbot_cli.llm import (
    LLMConfigurationError,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
    OpenAICompatibleClient,
    OpenAICompatibleConfig,
)
from onbot_cli.storage.sessions import SessionStore
from onbot_cli.ui.renderers import TerminalRenderer
from onbot_cli.ui.repl import InteractiveShell


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


class FakePromptInput:
    def __init__(self, values: list[str]) -> None:
        self.values = list(values)

    def prompt(self, message: str) -> str:
        if not self.values:
            raise EOFError
        return self.values.pop(0)


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
    assert result.status == "planned"
    assert {step.status for step in result.step_results} == {"planned"}
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


def test_agent_controller_does_not_present_unapplied_file_claim_as_execution(
    tmp_path: Path,
) -> None:
    bootstrap = bootstrap_application(tmp_path)
    fake_llm = FakeLLM(
        [
            "1. **Novo Arquivo Criado:** `index.html`.\n",
            "2. **Conteúdo:** HTML basico foi escrito.\n",
            "A pagina esta pronta.",
        ]
    )
    controller = AgentController.from_bootstrap(bootstrap, llm_client=fake_llm)

    result = controller.run("crie uma landing page em index.html")
    session = SessionStore(bootstrap.layout).load(bootstrap.session_id)

    assert result.status == "completed"
    assert result.content.startswith("Nenhuma alteracao foi aplicada")
    assert "nao como execucao concluida" in result.content
    assert not (tmp_path / "index.html").exists()
    assert session.messages[-1]["content"] == result.content


def test_agent_controller_creates_pending_file_action_and_applies_after_yes(
    tmp_path: Path,
) -> None:
    action_payload = {
        "response": "Vou criar o arquivo solicitado apos sua confirmacao.",
        "actions": [
            {
                "type": "create_file",
                "path": "index.html",
                "content": "<!doctype html>\n<title>Portfolio</title>\n",
            }
        ],
    }
    bootstrap = bootstrap_application(tmp_path)
    fake_llm = FakeLLM(
        [f"<onbot-actions>{json.dumps(action_payload)}</onbot-actions>"]
    )
    controller = AgentController.from_bootstrap(bootstrap, llm_client=fake_llm)

    proposed = controller.run("crie index.html")
    session_after_proposal = SessionStore(bootstrap.layout).load(bootstrap.session_id)
    target = tmp_path / "index.html"
    exists_before_confirmation = target.exists()
    applied = controller.run("sim")
    session_after_apply = SessionStore(bootstrap.layout).load(bootstrap.session_id)

    assert proposed.status == "awaiting_confirmation"
    assert "Responda `sim`" in proposed.content
    assert not exists_before_confirmation
    assert session_after_proposal.pending_interactions[-1]["status"] == "pending"
    assert applied.status == "completed"
    assert target.read_text(encoding="utf-8") == "<!doctype html>\n<title>Portfolio</title>\n"
    assert session_after_apply.pending_interactions[-1]["status"] == "completed"
    assert "create_file" in applied.content or "write_file" in applied.content


def test_agent_controller_can_edit_move_and_delete_real_files_after_confirmation(
    tmp_path: Path,
) -> None:
    (tmp_path / "edit_me.txt").write_text("old\n", encoding="utf-8")
    (tmp_path / "delete_me.txt").write_text("remove\n", encoding="utf-8")
    action_payload = {
        "response": "Vou editar, mover e excluir os arquivos apos confirmacao.",
        "actions": [
            {
                "type": "edit_file",
                "path": "edit_me.txt",
                "content": "new\n",
            },
            {
                "type": "move_file",
                "source": "edit_me.txt",
                "destination": "moved.txt",
            },
            {
                "type": "delete_file",
                "path": "delete_me.txt",
            },
        ],
    }
    bootstrap = bootstrap_application(tmp_path)
    fake_llm = FakeLLM(
        [f"```json\n{json.dumps(action_payload)}\n```"]
    )
    controller = AgentController.from_bootstrap(bootstrap, llm_client=fake_llm)

    proposed = controller.run("altere os arquivos")
    applied = controller.run("sim")

    assert proposed.status == "awaiting_confirmation"
    assert applied.status == "completed"
    assert not (tmp_path / "edit_me.txt").exists()
    assert (tmp_path / "moved.txt").read_text(encoding="utf-8") == "new\n"
    assert not (tmp_path / "delete_me.txt").exists()
    assert applied.file_action_result is not None
    assert {result.action for result in applied.file_action_result.results} == {
        "write_file",
        "move_file",
        "delete_file",
    }


def test_agent_controller_cancels_pending_file_action_after_no(tmp_path: Path) -> None:
    action_payload = {
        "response": "Vou criar o arquivo apos confirmacao.",
        "actions": [
            {"type": "create_file", "path": "cancelled.txt", "content": "nope\n"}
        ],
    }
    bootstrap = bootstrap_application(tmp_path)
    fake_llm = FakeLLM(
        [f"<onbot-actions>{json.dumps(action_payload)}</onbot-actions>"]
    )
    controller = AgentController.from_bootstrap(bootstrap, llm_client=fake_llm)

    proposed = controller.run("crie cancelled.txt")
    cancelled = controller.run("nao")
    session = SessionStore(bootstrap.layout).load(bootstrap.session_id)

    assert proposed.status == "awaiting_confirmation"
    assert cancelled.status == "cancelled"
    assert not (tmp_path / "cancelled.txt").exists()
    assert session.pending_interactions[-1]["status"] == "cancelled"


def test_agent_controller_does_not_treat_yes_without_pending_as_new_task(
    tmp_path: Path,
) -> None:
    bootstrap = bootstrap_application(tmp_path)
    fake_llm = FakeLLM()
    controller = AgentController.from_bootstrap(bootstrap, llm_client=fake_llm)

    result = controller.run("sim")

    assert result.status == "clarification_required"
    assert "Nao ha nenhuma acao pendente" in result.content
    assert fake_llm.requests == []


def test_interactive_shell_routes_yes_to_pending_file_action(tmp_path: Path) -> None:
    action_payload = {
        "response": "Vou criar o arquivo apos confirmacao.",
        "actions": [
            {"type": "create_file", "path": "shell.txt", "content": "ok\n"}
        ],
    }
    bootstrap = bootstrap_application(tmp_path)
    fake_llm = FakeLLM(
        [f"<onbot-actions>{json.dumps(action_payload)}</onbot-actions>"]
    )
    output = StringIO()
    renderer = TerminalRenderer(Console(file=output, color_system=None, width=120))
    controller = AgentController.from_bootstrap(bootstrap, llm_client=fake_llm)
    shell = InteractiveShell(
        bootstrap,
        create_default_router(),
        renderer,
        version="0.1.0",
        prompt_input=FakePromptInput(["crie shell.txt", "sim", "/exit"]),
        agent_controller=controller,
    )

    shell.run()

    assert (tmp_path / "shell.txt").read_text(encoding="utf-8") == "ok\n"
    assert len(fake_llm.requests) == 1
    rendered = output.getvalue()
    assert "Alteracoes pendentes de confirmacao" in rendered
    assert "Alteracoes aplicadas" in rendered


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
