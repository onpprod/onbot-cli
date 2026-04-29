"""Workflows agenticos compostos por etapas reutilizaveis."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    """Etapa basica reutilizavel dentro de um workflow."""

    id: str
    title: str
    description: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class Workflow:
    """Definicao de workflow minimo acionavel internamente."""

    name: str
    description: str
    intent_keywords: Sequence[str]
    steps: Sequence[WorkflowStep]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "intent_keywords": list(self.intent_keywords),
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass(frozen=True, slots=True)
class WorkflowStepResult:
    """Progresso registrado para uma etapa executada."""

    step_id: str
    title: str
    status: str = "completed"
    output: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "title": self.title,
            "status": self.status,
            "output": dict(self.output),
        }


@dataclass(frozen=True, slots=True)
class WorkflowRunResult:
    """Resultado de uma execucao linear de workflow."""

    workflow: Workflow
    step_results: Sequence[WorkflowStepResult]
    status: str = "completed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow.name,
            "status": self.status,
            "steps": [item.to_dict() for item in self.step_results],
        }


ProgressCallback = Callable[[WorkflowStep, str], None]


class WorkflowEngine:
    """Seleciona e executa workflows definidos por etapas basicas."""

    def __init__(self, workflows: Sequence[Workflow] | None = None) -> None:
        self._workflows: dict[str, Workflow] = {}
        for workflow in workflows or default_workflows():
            self.register(workflow)

    def register(self, workflow: Workflow) -> Workflow:
        self._workflows[workflow.name] = workflow
        return workflow

    def get(self, name: str) -> Workflow:
        return self._workflows[name]

    def list_workflows(self) -> tuple[Workflow, ...]:
        return tuple(sorted(self._workflows.values(), key=lambda item: item.name))

    def select(self, prompt: str) -> Workflow:
        lowered = prompt.lower()
        scored: list[tuple[int, Workflow]] = []
        for workflow in self._workflows.values():
            score = sum(1 for keyword in workflow.intent_keywords if keyword in lowered)
            scored.append((score, workflow))
        scored.sort(key=lambda item: (-item[0], item[1].name))
        if scored and scored[0][0] > 0:
            return scored[0][1]
        return self._workflows["feature"]

    def execute(
        self,
        workflow: Workflow | str,
        *,
        objective: str,
        progress_callback: ProgressCallback | None = None,
    ) -> WorkflowRunResult:
        selected = self.get(workflow) if isinstance(workflow, str) else workflow
        results: list[WorkflowStepResult] = []
        for step in selected.steps:
            if progress_callback is not None:
                progress_callback(step, "running")
            output = {
                "objective": objective,
                "instruction": step.description,
            }
            result = WorkflowStepResult(
                step_id=step.id,
                title=step.title,
                status="completed",
                output=output,
            )
            results.append(result)
            if progress_callback is not None:
                progress_callback(step, result.status)
        return WorkflowRunResult(workflow=selected, step_results=tuple(results))


def default_workflows() -> tuple[Workflow, ...]:
    """Workflows minimos da etapa 06."""

    return (
        Workflow(
            name="feature",
            description="Entender, inspecionar, planejar, implementar, testar, revisar e explicar.",
            intent_keywords=("feature", "implementar", "criar", "adicionar", "novo"),
            steps=(
                _step("understand", "Entender objetivo", "Interpretar o pedido do usuario."),
                _step("inspect", "Inspecionar projeto", "Ler estrutura e convencoes relevantes."),
                _step("plan", "Planejar tasks", "Dividir trabalho em passos verificaveis."),
                _step("implement", "Implementar feature", "Aplicar mudancas necessarias."),
                _step("test", "Testar", "Criar ou rodar validacoes adequadas."),
                _step("review", "Revisar", "Revisar diff e impactos."),
                _step("explain", "Explicar", "Explicar mudancas e validacoes."),
            ),
        ),
        Workflow(
            name="bugfix",
            description="Reproduzir ou localizar, investigar, corrigir, testar regressao e explicar.",
            intent_keywords=("bug", "erro", "falha", "corrigir", "fix", "regressao"),
            steps=(
                _step("collect", "Coletar sintoma", "Entender erro e comportamento esperado."),
                _step("locate", "Localizar evidencia", "Reproduzir ou localizar codigo afetado."),
                _step("investigate", "Investigar causa", "Identificar causa raiz provavel."),
                _step("fix", "Corrigir", "Aplicar correcao minima."),
                _step("regression", "Testar regressao", "Validar que o erro nao retorna."),
                _step("explain", "Explicar", "Explicar causa e solucao."),
            ),
        ),
        Workflow(
            name="refactor",
            description="Baseline, passos pequenos, validacoes frequentes e revisao de diff.",
            intent_keywords=("refator", "refactor", "reorganizar", "simplificar"),
            steps=(
                _step("scope", "Definir escopo", "Fixar objetivo tecnico da refatoracao."),
                _step("baseline", "Rodar baseline", "Identificar validacoes existentes."),
                _step("small-steps", "Planejar passos", "Dividir mudancas preservando comportamento."),
                _step("apply", "Aplicar mudancas", "Executar refatoracao em incrementos."),
                _step("validate", "Validar", "Rodar testes frequentemente."),
                _step("review", "Revisar diff", "Checar alteracoes funcionais acidentais."),
            ),
        ),
        Workflow(
            name="documentation",
            description="Ler base, planejar estrutura, redigir, validar consistencia e explicar.",
            intent_keywords=("doc", "docs", "readme", "documentacao", "documentar"),
            steps=(
                _step("audience", "Identificar publico", "Definir objetivo da documentacao."),
                _step("read", "Ler base", "Inspecionar requisitos, arquitetura e codigo relevante."),
                _step("structure", "Planejar estrutura", "Organizar secoes e referencias."),
                _step("write", "Redigir", "Criar ou atualizar o documento."),
                _step("consistency", "Validar consistencia", "Conferir aderencia ao codigo."),
                _step("explain", "Explicar", "Resumir mudancas documentais."),
            ),
        ),
        Workflow(
            name="code_review",
            description="Inspecionar diff/codigo, apontar riscos e sugerir validacoes.",
            intent_keywords=("review", "revisao", "revisar", "diff", "code review"),
            steps=(
                _step("inspect", "Inspecionar", "Ler diff ou codigo informado."),
                _step("risks", "Apontar riscos", "Priorizar bugs e regressao."),
                _step("validations", "Sugerir validacoes", "Indicar testes ou checagens."),
                _step("report", "Relatar", "Responder com achados por severidade."),
            ),
        ),
        Workflow(
            name="prepare_commit",
            description="Preparar mensagem e resumo usando status/diff quando Git estiver disponivel.",
            intent_keywords=("commit", "mensagem de commit", "preparar commit"),
            steps=(
                _step("status", "Consultar status", "Obter status Git quando disponivel."),
                _step("diff", "Consultar diff", "Revisar mudancas agrupaveis."),
                _step("validate", "Rodar validacoes", "Executar checagens adequadas."),
                _step("message", "Preparar mensagem", "Gerar mensagem e resumo."),
            ),
        ),
    )


def _step(id: str, title: str, description: str) -> WorkflowStep:
    return WorkflowStep(id=id, title=title, description=description)
