"""Planejamento estruturado para acoes agenticas."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from onbot_cli.agent.context import ContextBundle


@dataclass(frozen=True, slots=True)
class PlanStep:
    """Passo pequeno e verificavel do plano."""

    id: str
    title: str
    description: str
    status: str = "pending"

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class Plan:
    """Plano produzido antes de acoes relevantes."""

    objective: str
    likely_areas: Sequence[str] = field(default_factory=tuple)
    steps: Sequence[PlanStep] = field(default_factory=tuple)
    risks: Sequence[str] = field(default_factory=tuple)
    validations: Sequence[str] = field(default_factory=tuple)
    completion_criteria: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "objetivo": self.objective,
            "areas_provaveis": list(self.likely_areas),
            "passos": [step.to_dict() for step in self.steps],
            "riscos": list(self.risks),
            "validacoes": list(self.validations),
            "criterio_de_conclusao": self.completion_criteria,
        }


class Planner:
    """Cria planos deterministicos a partir do objetivo e contexto local."""

    def create_plan(
        self,
        objective: str,
        *,
        context: ContextBundle | None = None,
        workflow_name: str | None = None,
    ) -> Plan:
        likely_areas = _likely_areas(context)
        steps = _steps_for(objective, workflow_name)
        validations = _validations(context)
        risks = _risks_for(objective, context)
        return Plan(
            objective=objective.strip(),
            likely_areas=likely_areas,
            steps=steps,
            risks=risks,
            validations=validations,
            completion_criteria=(
                "Responder ao usuario com o resultado, mudancas realizadas, "
                "validacoes executadas e riscos residuais."
            ),
        )


def _likely_areas(context: ContextBundle | None) -> tuple[str, ...]:
    if context is None:
        return ("workspace",)

    areas: list[str] = []
    for snippet in context.snippets:
        top_level = snippet.path.split("/", 1)[0]
        if top_level not in areas:
            areas.append(top_level)

    summary = context.summary
    for item in summary.get("config_files", []) if isinstance(summary, Mapping) else []:
        top_level = str(item).split("/", 1)[0]
        if top_level not in areas:
            areas.append(top_level)

    if not areas:
        areas.extend(["src", "tests", "docs"])
    return tuple(areas[:8])


def _steps_for(objective: str, workflow_name: str | None) -> tuple[PlanStep, ...]:
    workflow = workflow_name or _infer_workflow(objective)
    if workflow == "bugfix":
        titles = (
            ("understand", "Entender sintoma", "Coletar erro, comportamento esperado e evidencia."),
            ("locate", "Localizar causa", "Inspecionar codigo e contexto relacionado."),
            ("fix", "Corrigir minimo", "Aplicar a menor alteracao coerente."),
            ("regression", "Validar regressao", "Criar ou rodar validacao que cubra o problema."),
            ("explain", "Explicar solucao", "Resumir causa, correcao e risco residual."),
        )
    elif workflow == "refactor":
        titles = (
            ("baseline", "Estabelecer baseline", "Identificar comportamento atual e validacoes."),
            ("plan-small", "Dividir passos", "Planejar mudancas pequenas e reversiveis."),
            ("change", "Aplicar refatoracao", "Preservar comportamento observavel."),
            ("validate", "Validar frequentemente", "Rodar testes ou checagens relevantes."),
            ("review", "Revisar diff", "Conferir se nao houve mudanca funcional acidental."),
        )
    elif workflow == "documentation":
        titles = (
            ("audience", "Definir objetivo", "Identificar publico e lacunas de documentacao."),
            ("read", "Ler base", "Consultar requisitos, arquitetura e codigo relevante."),
            ("structure", "Planejar estrutura", "Organizar secoes e referencias."),
            ("write", "Redigir", "Atualizar documentacao de forma consistente."),
            ("validate", "Validar consistencia", "Conferir nomes, caminhos e escopo."),
        )
    elif workflow == "code_review":
        titles = (
            ("inspect", "Inspecionar diff", "Ler mudancas e contratos afetados."),
            ("risks", "Mapear riscos", "Priorizar bugs, regressao e falta de testes."),
            ("validate", "Sugerir validacoes", "Apontar testes ou checagens adequadas."),
            ("report", "Relatar achados", "Responder com achados ordenados por severidade."),
        )
    elif workflow == "prepare_commit":
        titles = (
            ("status", "Consultar status", "Usar Git quando estiver disponivel."),
            ("diff", "Revisar diff", "Agrupar mudancas relacionadas."),
            ("validate", "Rodar validacoes", "Executar checagens adequadas ao projeto."),
            ("message", "Preparar mensagem", "Gerar resumo e mensagem de commit."),
        )
    else:
        titles = (
            ("understand", "Entender pedido", "Confirmar objetivo e restricoes relevantes."),
            ("inspect", "Inspecionar projeto", "Ler estrutura, convencoes e arquivos provaveis."),
            ("plan", "Planejar tasks", "Definir passos pequenos e validaveis."),
            ("implement", "Implementar", "Aplicar mudancas usando primitivas seguras."),
            ("test", "Validar", "Rodar testes ou checagens cabiveis."),
            ("explain", "Explicar mudancas", "Resumir resultado e proximos passos."),
        )
    return tuple(
        PlanStep(id=item[0], title=item[1], description=item[2]) for item in titles
    )


def _validations(context: ContextBundle | None) -> tuple[str, ...]:
    commands = {}
    if context is not None and isinstance(context.summary, Mapping):
        value = context.summary.get("commands", {})
        if isinstance(value, Mapping):
            commands = dict(value)

    validations: list[str] = []
    for key in ("test", "lint", "build"):
        command = commands.get(key)
        if command:
            validations.append(str(command))
    if not validations:
        validations.append("poetry run pytest")
    return tuple(validations)


def _risks_for(objective: str, context: ContextBundle | None) -> tuple[str, ...]:
    risks = [
        "Contexto selecionado pode estar incompleto para mudancas amplas.",
        "Acoes mutaveis continuam sujeitas ao modo de permissao ativo.",
    ]
    lowered = objective.lower()
    if any(term in lowered for term in ("refator", "refactor")):
        risks.append("Refatoracao pode alterar comportamento se o baseline for fraco.")
    if context is not None and context.truncated:
        risks.append("Contexto foi truncado por limite de tamanho.")
    return tuple(risks)


def _infer_workflow(objective: str) -> str:
    lowered = objective.lower()
    if any(term in lowered for term in ("bug", "erro", "falha", "corrigir", "fix")):
        return "bugfix"
    if any(term in lowered for term in ("refator", "refactor")):
        return "refactor"
    if any(term in lowered for term in ("doc", "readme", "document")):
        return "documentation"
    if any(term in lowered for term in ("review", "revis", "diff")):
        return "code_review"
    if any(term in lowered for term in ("commit", "mensagem")):
        return "prepare_commit"
    return "feature"
