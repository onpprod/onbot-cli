"""Controlador principal do ciclo agentico."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from onbot_cli.agent.context import ContextBundle, ContextManager
from onbot_cli.agent.messages import AgentMessage
from onbot_cli.agent.planner import Plan, Planner
from onbot_cli.agent.workflows import WorkflowEngine, WorkflowRunResult
from onbot_cli.app import BootstrapResult
from onbot_cli.errors import ApplicationError
from onbot_cli.llm import (
    LLMCancelledError,
    LLMClient,
    LLMConfigurationError,
    LLMError,
    LLMRequest,
    OpenAICompatibleClient,
    OpenAICompatibleConfig,
)
from onbot_cli.models import ApplicationContext
from onbot_cli.security.paths import PathGuard
from onbot_cli.security.permissions import PermissionManager
from onbot_cli.storage.logs import AuditLogger
from onbot_cli.storage.models import ActionRecord, MessageRecord
from onbot_cli.storage.sessions import SessionStore
from onbot_cli.tools import ToolContext, ToolRegistry, create_internal_tool_registry
from onbot_cli.workspace import WorkspaceLayout


class AgentControllerError(ApplicationError):
    """Erro do controlador agentico."""

    code = "agent_controller_error"


class AgentStepLimitExceeded(AgentControllerError):
    """Limite configurado de passos excedido."""

    code = "agent_step_limit_exceeded"


@dataclass(frozen=True, slots=True)
class AgentTurnResult:
    """Resultado de um turno do agente."""

    status: str
    content: str
    plan: Plan | None = None
    workflow_result: WorkflowRunResult | None = None
    steps_taken: int = 0
    streamed: bool = False
    error: str | None = None


StreamCallback = Callable[[str], None]
PlanCallback = Callable[[Mapping[str, Any]], None]


class AgentController:
    """Orquestra contexto, planner, workflows, tools internas e LLM."""

    def __init__(
        self,
        app_context: ApplicationContext,
        layout: WorkspaceLayout,
        *,
        config: Mapping[str, Any],
        llm_client: LLMClient | None = None,
        planner: Planner | None = None,
        workflow_engine: WorkflowEngine | None = None,
        tool_registry: ToolRegistry | None = None,
        session_store: SessionStore | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self.app_context = app_context
        self.layout = layout
        self.config = config
        self.llm_config = OpenAICompatibleConfig.from_config(config)
        self.llm_client = llm_client
        self.planner = planner or Planner()
        self.workflow_engine = workflow_engine or WorkflowEngine()
        self.tool_registry = tool_registry or create_internal_tool_registry(config)
        self.session_store = session_store or SessionStore(layout)
        self.audit_logger = audit_logger or AuditLogger(layout)
        self.context_manager = ContextManager(layout, config)
        self._steps_taken = 0

    @classmethod
    def from_bootstrap(
        cls,
        bootstrap: BootstrapResult,
        *,
        llm_client: LLMClient | None = None,
    ) -> "AgentController":
        return cls(
            bootstrap.context,
            bootstrap.layout,
            config=bootstrap.config,
            llm_client=llm_client,
        )

    def run(
        self,
        prompt: str,
        *,
        stream_callback: StreamCallback | None = None,
        plan_callback: PlanCallback | None = None,
    ) -> AgentTurnResult:
        """Executa um turno completo respeitando `agent.max_steps`."""

        self._steps_taken = 0
        plan: Plan | None = None
        workflow_result: WorkflowRunResult | None = None
        streamed = False

        try:
            self._enter_step("select_workflow")
            workflow = self.workflow_engine.select(prompt)

            self._enter_step("summarize_with_tool")
            self._refresh_summary_with_tool()

            self._enter_step("build_context")
            context = self.context_manager.build_context(prompt)

            self._enter_step("plan")
            plan = self.planner.create_plan(
                prompt,
                context=context,
                workflow_name=workflow.name,
            )
            self._record_action(
                "agent_plan",
                "created",
                target=workflow.name,
                detail=plan.to_dict(),
            )
            if plan_callback is not None:
                plan_callback(plan.to_dict())

            self._enter_step("workflow")
            workflow_result = self.workflow_engine.execute(
                workflow,
                objective=prompt,
                progress_callback=self._record_workflow_progress,
            )
            self._record_action(
                "workflow",
                workflow_result.status,
                target=workflow.name,
                detail=workflow_result.to_dict(),
            )

            self._enter_step("llm")
            content, streamed = self._respond_with_llm(
                prompt,
                context=context,
                plan=plan,
                workflow_result=workflow_result,
                stream_callback=stream_callback,
            )
            status = "completed"
            error = None
        except AgentStepLimitExceeded as exc:
            content = _max_steps_message(self.max_steps)
            status = "max_steps_exceeded"
            error = exc.message
            self._record_action("agent_turn", status, detail={"error": error})
        except LLMCancelledError as exc:
            content = "Chamada LLM cancelada."
            status = "cancelled"
            error = exc.message
            self._record_action("llm_response", status, detail={"error": error})
        except LLMError as exc:
            content = f"Falha ao chamar o provedor LLM: {exc.message}"
            if exc.hint:
                content = f"{content}\n{exc.hint}"
            status = "llm_error"
            error = exc.message
            self._record_action("llm_response", status, detail={"error": error})

        self._record_assistant_message(content, status=status)
        return AgentTurnResult(
            status=status,
            content=content,
            plan=plan,
            workflow_result=workflow_result,
            steps_taken=self._steps_taken,
            streamed=streamed,
            error=error,
        )

    @property
    def max_steps(self) -> int:
        agent_config = self.config.get("agent", {})
        if not isinstance(agent_config, Mapping):
            return 20
        try:
            return max(int(agent_config.get("max_steps", 20)), 1)
        except (TypeError, ValueError):
            return 20

    def _respond_with_llm(
        self,
        prompt: str,
        *,
        context: ContextBundle,
        plan: Plan,
        workflow_result: WorkflowRunResult,
        stream_callback: StreamCallback | None,
    ) -> tuple[str, bool]:
        if self.llm_client is None and not self.llm_config.configured:
            return _configuration_fallback(self.llm_config), False

        client = self.llm_client or OpenAICompatibleClient(self.llm_config)
        request = LLMRequest(
            messages=[
                message.to_llm_dict()
                for message in _messages_for(prompt, context, plan, workflow_result)
            ],
            model=self.llm_config.model or None,
            temperature=self.llm_config.temperature,
            generation_params=self.llm_config.generation_params,
            stream=True,
        )
        self.audit_logger.record_event(
            "llm_request",
            {
                "model": request.model,
                "stream": True,
                "message_count": len(request.messages),
            },
            session_id=self.session_id,
        )

        chunks: list[str] = []
        streamed = False
        for chunk in client.stream(request):
            if chunk.content:
                chunks.append(chunk.content)
                streamed = True
                if stream_callback is not None:
                    stream_callback(chunk.content)
        content = "".join(chunks)
        if not content:
            response = client.complete(request)
            content = response.content

        self.audit_logger.record_event(
            "llm_response",
            {
                "model": request.model,
                "status": "completed",
                "streamed": streamed,
                "content_chars": len(content),
            },
            session_id=self.session_id,
        )
        return content, streamed

    def _refresh_summary_with_tool(self) -> None:
        context = self._tool_context()
        result = self.tool_registry.execute(
            "project_summary",
            {"refresh": False},
            context,
        )
        if not result.success:
            self._record_action(
                "tool",
                result.status,
                target="project_summary",
                detail={"error": result.error, "metadata": dict(result.metadata)},
            )

    def _tool_context(self) -> ToolContext:
        permission_manager = PermissionManager(
            self.config,
            audit_logger=self.audit_logger,
            session_store=self.session_store,
            session_id=self.session_id,
        )
        return ToolContext(
            workspace=self.app_context.workspace,
            layout=self.layout,
            config=self.config,
            path_guard=PathGuard(self.layout.root),
            permission_manager=permission_manager,
            audit_logger=self.audit_logger,
            session_store=self.session_store,
            session_id=self.session_id,
        )

    def _record_workflow_progress(self, step: Any, status: str) -> None:
        self._record_action(
            "workflow_step",
            status,
            target=getattr(step, "id", None),
            detail={
                "title": getattr(step, "title", ""),
                "description": getattr(step, "description", ""),
            },
        )

    def _enter_step(self, name: str) -> None:
        self._steps_taken += 1
        if self._steps_taken > self.max_steps:
            raise AgentStepLimitExceeded(
                "Limite maximo de passos excedido.",
                hint=f"agent.max_steps={self.max_steps}, passo={name}",
            )

    def _record_action(
        self,
        action_type: str,
        status: str,
        *,
        target: str | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        self.audit_logger.record_event(
            action_type,
            {
                "status": status,
                "target": target,
                "detail": dict(detail or {}),
            },
            session_id=self.session_id,
        )
        if self.session_id:
            self.session_store.append_action(
                self.session_id,
                ActionRecord(
                    type=action_type,
                    status=status,
                    target=target,
                    detail=dict(detail or {}),
                ),
            )

    def _record_assistant_message(self, content: str, *, status: str) -> None:
        if not self.session_id:
            return
        self.session_store.append_message(
            self.session_id,
            MessageRecord(
                role="assistant",
                content=content,
                metadata={
                    "source": "agent_controller",
                    "status": status,
                    "steps_taken": self._steps_taken,
                },
            ),
        )

    @property
    def session_id(self) -> str | None:
        return self.app_context.session_id


def _messages_for(
    prompt: str,
    context: ContextBundle,
    plan: Plan,
    workflow_result: WorkflowRunResult,
) -> Sequence[AgentMessage]:
    return (
        AgentMessage.system(
            "Voce e o onbot-cli, uma CLI agentica para desenvolvimento local. "
            "Responda em portugues, respeite permissoes, nao invente execucoes "
            "e nunca exponha segredos deliberadamente."
        ),
        AgentMessage.system(_context_payload(context, plan, workflow_result)),
        AgentMessage.user(prompt),
    )


def _context_payload(
    context: ContextBundle,
    plan: Plan,
    workflow_result: WorkflowRunResult,
) -> str:
    summary = dict(context.summary)
    summary["tree"] = list(summary.get("tree", []))[:80]
    snippets = [
        {
            "path": snippet.path,
            "start_line": snippet.start_line,
            "end_line": snippet.end_line,
            "content": snippet.content,
            "score": snippet.score,
        }
        for snippet in context.snippets
    ]
    payload = {
        "project_summary": summary,
        "context_snippets": snippets,
        "context_truncated": context.truncated,
        "plan": plan.to_dict(),
        "workflow": workflow_result.to_dict(),
    }
    return "Contexto local controlado:\n" + json.dumps(
        payload,
        ensure_ascii=True,
        indent=2,
    )


def _configuration_fallback(config: OpenAICompatibleConfig) -> str:
    if not config.model:
        return (
            "Plano estruturado preparado, mas o modelo LLM nao esta configurado. "
            "Defina `model.model` em `.onbot-cli/config.yaml` para conversar "
            "com um provedor OpenAI-compatible."
        )
    return (
        "Plano estruturado preparado, mas a chave de API do provedor nao foi "
        f"encontrada. Defina a variavel de ambiente `{config.api_key_env}`."
    )


def _max_steps_message(max_steps: int) -> str:
    return (
        "Execucao interrompida pelo limite de passos do agente "
        f"(`agent.max_steps={max_steps}`). Revise o objetivo ou aumente o limite "
        "na configuracao local para tarefas maiores."
    )
