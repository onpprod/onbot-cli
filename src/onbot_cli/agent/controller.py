"""Controlador principal do ciclo agentico."""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from onbot_cli.agent.context import ContextBundle, ContextManager
from onbot_cli.agent.file_actions import (
    AgentActionPlan,
    FileActionApplyResult,
    FileActionExecutor,
    StaticApprovalService,
    parse_action_plan,
)
from onbot_cli.agent.messages import AgentMessage
from onbot_cli.agent.planner import Plan, Planner
from onbot_cli.agent.state import (
    AgentTurnStatus,
    ConversationStateManager,
    PendingInteraction,
    PendingInteractionStatus,
    PendingInteractionType,
    classify_pending_response,
    is_short_confirmation_without_pending,
)
from onbot_cli.agent.workflows import WorkflowEngine, WorkflowRunResult
from onbot_cli.app import BootstrapResult
from onbot_cli.errors import ApplicationError
from onbot_cli.llm import (
    LLMCancelledError,
    LLMClient,
    LLMError,
    LLMRequest,
    OpenAICompatibleClient,
    OpenAICompatibleConfig,
)
from onbot_cli.models import ApplicationContext
from onbot_cli.security.paths import PathGuard
from onbot_cli.security.permissions import PermissionManager
from onbot_cli.security.redaction import redact_data
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
    pending_interaction: PendingInteraction | None = None
    file_action_result: FileActionApplyResult | None = None


@dataclass(frozen=True, slots=True)
class LLMTurnOutput:
    """Saida completa do LLM apos parsing de acoes estruturadas."""

    content: str
    streamed: bool = False
    action_plan: AgentActionPlan | None = None


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
        self.state_manager = ConversationStateManager(
            self.session_store,
            app_context.session_id,
        )
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
        pending_interaction: PendingInteraction | None = None
        file_action_result: FileActionApplyResult | None = None

        pending = self.state_manager.active_pending()
        if pending is not None:
            try:
                result = self._handle_pending_response(pending, prompt)
            except ApplicationError as exc:
                content = f"Falha ao processar acao pendente: {exc.message}"
                if exc.hint:
                    content = f"{content}\n{exc.hint}"
                self._record_action(
                    "pending_interaction",
                    "failed",
                    target=pending.id,
                    detail={"error": exc.message, "hint": exc.hint},
                )
                result = AgentTurnResult(
                    status=AgentTurnStatus.FAILED.value,
                    content=content,
                    pending_interaction=pending,
                    error=exc.message,
                )
            self._record_assistant_message(result.content, status=result.status)
            return result

        if is_short_confirmation_without_pending(prompt):
            content = (
                "Nao ha nenhuma acao pendente para confirmar. "
                "Descreva a tarefa que deseja executar."
            )
            self._record_action(
                "agent_turn",
                "clarification_required",
                detail={"input": prompt, "reason": "short_confirmation_without_pending"},
            )
            self._record_assistant_message(
                content,
                status="clarification_required",
            )
            return AgentTurnResult(
                status="clarification_required",
                content=content,
                steps_taken=self._steps_taken,
            )

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
            llm_output = self._respond_with_llm(
                prompt,
                context=context,
                plan=plan,
                workflow_result=workflow_result,
                recent_messages=self._recent_messages(prompt),
                stream_callback=stream_callback,
            )
            streamed = llm_output.streamed
            if llm_output.action_plan is not None:
                pending_interaction = self._create_file_action_pending(
                    llm_output.action_plan,
                    workflow_name=workflow.name,
                    step="file_actions",
                )
                content = _pending_file_action_message(
                    llm_output.action_plan,
                    pending_interaction,
                    self._file_action_executor().preview(llm_output.action_plan),
                )
                status = AgentTurnStatus.AWAITING_CONFIRMATION.value
            else:
                content = llm_output.content
                status = AgentTurnStatus.COMPLETED.value
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
            pending_interaction=pending_interaction,
            file_action_result=file_action_result,
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
        recent_messages: Sequence[Mapping[str, Any]],
        stream_callback: StreamCallback | None,
    ) -> LLMTurnOutput:
        if self.llm_client is None and not self.llm_config.configured:
            return LLMTurnOutput(_configuration_fallback(self.llm_config), False)

        client = self.llm_client or OpenAICompatibleClient(self.llm_config)
        request = LLMRequest(
            messages=[
                message.to_llm_dict()
                for message in _messages_for(
                    prompt,
                    context,
                    plan,
                    workflow_result,
                    recent_messages,
                )
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
        content = "".join(chunks)
        if not content:
            response = client.complete(request)
            content = response.content
        action_plan = parse_action_plan(content)
        if action_plan is None:
            content = _ground_unapplied_mutation_claims(content)
            if stream_callback is not None and content:
                for chunk in chunks or [content]:
                    stream_callback(chunk)
        else:
            content = action_plan.response

        self.audit_logger.record_event(
            "llm_response",
            {
                "model": request.model,
                "status": "completed",
                "streamed": streamed,
                "content_chars": len(content),
                "action_count": 0 if action_plan is None else len(action_plan.actions),
            },
            session_id=self.session_id,
        )
        return LLMTurnOutput(content, streamed, action_plan)

    def _handle_pending_response(
        self,
        pending: PendingInteraction,
        response: str,
    ) -> AgentTurnResult:
        decision = classify_pending_response(response)
        if decision is None:
            content = (
                "Existe uma acao pendente aguardando decisao. "
                "Responda `sim` para aplicar ou `nao` para cancelar.\n\n"
                f"{pending.prompt}"
            )
            self._record_action(
                "pending_interaction",
                "awaiting_response",
                target=pending.id,
                detail={"response": response},
            )
            return AgentTurnResult(
                status=AgentTurnStatus.AWAITING_CONFIRMATION.value,
                content=content,
                pending_interaction=pending,
            )

        if decision == "reject":
            resolved = self.state_manager.resolve_pending(
                pending.id,
                status=PendingInteractionStatus.CANCELLED,
                response=response,
            )
            content = "Acao pendente cancelada. Nenhuma alteracao foi aplicada."
            self._record_action(
                "pending_interaction",
                "cancelled",
                target=pending.id,
                detail={"response": response},
            )
            return AgentTurnResult(
                status=AgentTurnStatus.CANCELLED.value,
                content=content,
                pending_interaction=resolved or pending,
            )

        plan = AgentActionPlan.from_dict(pending.payload.get("action_plan", {}))
        self._enter_step("apply_pending_file_actions")
        apply_result = self._file_action_executor().apply(
            plan,
            approval_service=StaticApprovalService(
                approved=True,
                reason="usuario confirmou interacao pendente",
            ),
        )
        resolved = self.state_manager.resolve_pending(
            pending.id,
            status=(
                PendingInteractionStatus.COMPLETED
                if apply_result.applied
                else PendingInteractionStatus.REJECTED
            ),
            response=response,
        )
        self._record_action(
            "pending_interaction",
            "completed" if apply_result.applied else apply_result.status,
            target=pending.id,
            detail={
                "response": response,
                "results": [item.to_dict() for item in apply_result.results],
            },
        )
        return AgentTurnResult(
            status=(
                AgentTurnStatus.COMPLETED.value
                if apply_result.applied
                else AgentTurnStatus.FAILED.value
            ),
            content=apply_result.summary,
            steps_taken=self._steps_taken,
            pending_interaction=resolved or pending,
            file_action_result=apply_result,
        )

    def _create_file_action_pending(
        self,
        action_plan: AgentActionPlan,
        *,
        workflow_name: str,
        step: str,
    ) -> PendingInteraction:
        pending = self.state_manager.create_pending(
            type=PendingInteractionType.CONFIRMATION,
            prompt=action_plan.response,
            workflow=workflow_name,
            step=step,
            payload={"action_plan": action_plan.to_dict()},
            options=["sim", "nao", "cancelar"],
        )
        self._record_action(
            "pending_interaction",
            "created",
            target=pending.id,
            detail={
                "workflow": workflow_name,
                "step": step,
                "action_count": len(action_plan.actions),
            },
        )
        return pending

    def _file_action_executor(self) -> FileActionExecutor:
        return FileActionExecutor(self._tool_context())

    def _recent_messages(
        self,
        current_prompt: str,
        *,
        limit: int = 6,
    ) -> tuple[Mapping[str, Any], ...]:
        if not self.session_id:
            return ()
        try:
            session = self.session_store.load(self.session_id)
        except ApplicationError:
            return ()
        messages = list(session.messages[-limit:])
        if messages:
            last = messages[-1]
            if (
                last.get("role") == "user"
                and str(last.get("content", "")) == current_prompt
            ):
                messages = messages[:-1]
        redacted = redact_data(messages)
        return tuple(
            {
                "role": str(message.get("role", "")),
                "content": str(message.get("content", ""))[:1200],
            }
            for message in redacted
            if isinstance(message, Mapping)
        )

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
    recent_messages: Sequence[Mapping[str, Any]] = (),
) -> Sequence[AgentMessage]:
    return (
        AgentMessage.system(
            "Voce e o onbot-cli, uma CLI agentica para desenvolvimento local. "
            "Responda em portugues, respeite permissoes, nao invente execucoes "
            "e nunca exponha segredos deliberadamente. Para criar, editar, mover "
            "ou excluir arquivos, retorne somente um bloco <onbot-actions> com "
            "JSON no formato {\"response\": \"resumo\", \"actions\": [...]}. "
            "Use actions create_file, write_file, edit_file, move_file ou "
            "delete_file. Para escrita, envie sempre o conteudo completo do "
            "arquivo em content. Nunca afirme que a alteracao ja foi aplicada; "
            "o sistema pedira confirmacao e aplicara a acao real."
        ),
        AgentMessage.system(
            _context_payload(context, plan, workflow_result, recent_messages)
        ),
        AgentMessage.user(prompt),
    )


def _context_payload(
    context: ContextBundle,
    plan: Plan,
    workflow_result: WorkflowRunResult,
    recent_messages: Sequence[Mapping[str, Any]] = (),
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
        "recent_messages": [dict(item) for item in recent_messages],
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


def _pending_file_action_message(
    action_plan: AgentActionPlan,
    pending: PendingInteraction,
    preview: str,
) -> str:
    lines = [
        action_plan.response or "O modelo propos alteracoes em arquivos.",
        "",
        "Alteracoes pendentes de confirmacao:",
    ]
    for action in action_plan.actions:
        if action.type in {"create_file", "write_file", "edit_file"}:
            lines.append(f"- {action.type}: {action.path}")
        elif action.type == "delete_file":
            lines.append(f"- delete_file: {action.path}")
        elif action.type == "move_file":
            lines.append(f"- move_file: {action.source} -> {action.destination}")
    if preview:
        lines.extend(["", "Previa:", preview])
    lines.extend(
        [
            "",
            f"Pendencia: {pending.id}",
            "Responda `sim` para aplicar as alteracoes reais ou `nao` para cancelar.",
        ]
    )
    return "\n".join(lines)


def _ground_unapplied_mutation_claims(content: str) -> str:
    if not _claims_workspace_mutation(content):
        return content
    return (
        "Nenhuma alteracao foi aplicada pelo onbot-cli neste turno. "
        "A resposta abaixo deve ser tratada como proposta do modelo, nao como "
        "execucao concluida.\n\n"
        f"{content}"
    )


def _claims_workspace_mutation(content: str) -> bool:
    normalized = _normalize_claim_text(content)
    claim_markers = (
        "arquivo criado",
        "novo arquivo criado",
        "foi criado",
        "criei ",
        "criado:",
        "conteudo:",
        "implementei",
        "foi implementado",
        "alterei ",
        "modifiquei ",
        "escrevi ",
        "salvei ",
        "pagina esta pronta",
    )
    return any(marker in normalized for marker in claim_markers)


def _normalize_claim_text(content: str) -> str:
    decomposed = unicodedata.normalize("NFKD", content)
    return "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    ).lower()


def _max_steps_message(max_steps: int) -> str:
    return (
        "Execucao interrompida pelo limite de passos do agente "
        f"(`agent.max_steps={max_steps}`). Revise o objetivo ou aumente o limite "
        "na configuracao local para tarefas maiores."
    )
