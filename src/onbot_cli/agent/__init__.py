"""Componentes agenticos iniciais."""

from onbot_cli.agent.context import ContextBundle, ContextManager, ContextSnippet
from onbot_cli.agent.controller import (
    AgentController,
    AgentControllerError,
    AgentStepLimitExceeded,
    AgentTurnResult,
)
from onbot_cli.agent.file_actions import (
    AgentActionPlan,
    AgentFileAction,
    FileActionApplyResult,
    FileActionExecutor,
    FileActionResult,
    parse_action_plan,
)
from onbot_cli.agent.messages import AgentMessage, AgentRole, AgentToolCall
from onbot_cli.agent.planner import Plan, Planner, PlanStep
from onbot_cli.agent.state import (
    AgentTurnStatus,
    ConversationStateManager,
    PendingInteraction,
    PendingInteractionStatus,
    PendingInteractionType,
    classify_pending_response,
    is_short_confirmation_without_pending,
)
from onbot_cli.agent.workflows import (
    Workflow,
    WorkflowEngine,
    WorkflowRunResult,
    WorkflowStep,
    WorkflowStepResult,
    default_workflows,
)

__all__ = [
    "AgentController",
    "AgentControllerError",
    "AgentActionPlan",
    "AgentFileAction",
    "AgentMessage",
    "AgentRole",
    "AgentStepLimitExceeded",
    "AgentToolCall",
    "AgentTurnStatus",
    "AgentTurnResult",
    "ConversationStateManager",
    "ContextBundle",
    "ContextManager",
    "ContextSnippet",
    "FileActionApplyResult",
    "FileActionExecutor",
    "FileActionResult",
    "Plan",
    "Planner",
    "PlanStep",
    "PendingInteraction",
    "PendingInteractionStatus",
    "PendingInteractionType",
    "Workflow",
    "WorkflowEngine",
    "WorkflowRunResult",
    "WorkflowStep",
    "WorkflowStepResult",
    "classify_pending_response",
    "default_workflows",
    "is_short_confirmation_without_pending",
    "parse_action_plan",
]
