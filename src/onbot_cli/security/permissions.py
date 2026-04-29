"""Modos de execucao e avaliacao de permissoes."""

from __future__ import annotations

import fnmatch
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from onbot_cli.errors import ApplicationError
from onbot_cli.storage.logs import AuditLogger
from onbot_cli.storage.models import PermissionDecisionRecord
from onbot_cli.storage.sessions import SessionStore


class ExecutionMode(StrEnum):
    """Modos de autonomia suportados pela sessao."""

    PLAN = "plan"
    DEFAULT = "default"
    ACCEPT_EDITS = "accept_edits"
    TRUSTED = "trusted"
    LOCKED = "locked"


class PermissionEffect(StrEnum):
    """Efeitos declarativos de uma regra de permissao."""

    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class PermissionAction(StrEnum):
    """Acoes normalizadas avaliadas pelo PermissionManager."""

    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    COMMAND = "command"
    GIT = "git"
    TOOL = "tool"
    HOOK = "hook"
    PATCH = "patch"


class PermissionManagerError(ApplicationError):
    """Erro de configuracao ou avaliacao de permissoes."""

    code = "permission_error"


@dataclass(frozen=True, slots=True)
class PermissionRule:
    """Regra declarativa `allow`, `ask` ou `deny`."""

    effect: PermissionEffect
    action: PermissionAction | str = "*"
    target: str = "*"
    reason: str | None = None

    @classmethod
    def from_config(
        cls,
        effect: PermissionEffect | str,
        value: Any,
    ) -> "PermissionRule":
        normalized_effect = PermissionEffect(str(effect))

        if isinstance(value, Mapping):
            action = str(value.get("action", value.get("type", "*")))
            target = str(value.get("target", value.get("pattern", "*")))
            reason_value = value.get("reason")
            reason = None if reason_value is None else str(reason_value)
            return cls(
                effect=normalized_effect,
                action=_coerce_action_or_wildcard(action),
                target=target or "*",
                reason=reason,
            )

        raw = str(value)
        if ":" in raw:
            action_text, target = raw.split(":", 1)
            return cls(
                effect=normalized_effect,
                action=_coerce_action_or_wildcard(action_text),
                target=target.strip() or "*",
            )

        return cls(
            effect=normalized_effect,
            action=_coerce_action_or_wildcard(raw),
            target="*",
        )

    def to_config(self) -> dict[str, str]:
        payload = {
            "action": str(self.action),
            "target": self.target,
        }
        if self.reason:
            payload["reason"] = self.reason
        return payload

    def matches(self, request: "PermissionRequest") -> bool:
        request_action = _coerce_action(request.action)
        rule_action = str(self.action)
        if rule_action != "*" and rule_action != request_action.value:
            return False

        return _target_matches(
            pattern=self.target,
            target=request.target,
            action=request_action,
        )


@dataclass(frozen=True, slots=True)
class PermissionRequest:
    """Pedido normalizado de autorizacao."""

    action: PermissionAction | str
    target: str
    risk: str = "SAFE"
    protected: bool = False
    mutates: bool = False
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class PermissionEvaluation:
    """Resultado da avaliacao antes de uma possivel aprovacao do usuario."""

    request: PermissionRequest
    decision: PermissionEffect
    mode: ExecutionMode
    reason: str
    matched_rule: PermissionRule | None = None

    @property
    def allowed(self) -> bool:
        return self.decision == PermissionEffect.ALLOW

    @property
    def denied(self) -> bool:
        return self.decision == PermissionEffect.DENY

    @property
    def requires_approval(self) -> bool:
        return self.decision == PermissionEffect.ASK


class PermissionManager:
    """Avalia regras e modos seguindo `deny > ask > allow > modo`."""

    def __init__(
        self,
        config: Mapping[str, Any] | MutableMapping[str, Any],
        *,
        audit_logger: AuditLogger | None = None,
        session_store: SessionStore | None = None,
        session_id: str | None = None,
    ) -> None:
        self.config = config
        self.audit_logger = audit_logger
        self.session_store = session_store
        self.session_id = session_id

    @property
    def mode(self) -> ExecutionMode:
        permissions = _permissions_section(self.config)
        raw_mode = str(permissions.get("mode", ExecutionMode.DEFAULT.value))
        try:
            return ExecutionMode(raw_mode)
        except ValueError as exc:
            raise PermissionManagerError(
                "Modo de execucao invalido.",
                hint=f"Modo configurado: {raw_mode}",
            ) from exc

    @property
    def supported_modes(self) -> tuple[str, ...]:
        return tuple(mode.value for mode in ExecutionMode)

    def set_mode(self, mode: ExecutionMode | str) -> ExecutionMode:
        normalized = ExecutionMode(str(mode))
        permissions = _mutable_permissions_section(self.config)
        previous = str(permissions.get("mode", ExecutionMode.DEFAULT.value))
        permissions["mode"] = normalized.value
        self._record_event(
            "mode_changed",
            {"previous": previous, "current": normalized.value},
        )
        return normalized

    def rules(self) -> tuple[PermissionRule, ...]:
        permissions = _permissions_section(self.config)
        loaded: list[PermissionRule] = []
        for effect in (
            PermissionEffect.DENY,
            PermissionEffect.ASK,
            PermissionEffect.ALLOW,
        ):
            for value in _list_value(permissions.get(effect.value)):
                loaded.append(PermissionRule.from_config(effect, value))
        return tuple(loaded)

    def add_rule(
        self,
        effect: PermissionEffect | str,
        action: PermissionAction | str,
        target: str = "*",
        *,
        reason: str | None = None,
    ) -> PermissionRule:
        normalized_effect = PermissionEffect(str(effect))
        rule = PermissionRule(
            effect=normalized_effect,
            action=_coerce_action_or_wildcard(str(action)),
            target=target or "*",
            reason=reason,
        )
        permissions = _mutable_permissions_section(self.config)
        values = permissions.setdefault(normalized_effect.value, [])
        if not isinstance(values, list):
            raise PermissionManagerError(
                "Lista de permissoes invalida.",
                hint=f"O campo permissions.{normalized_effect.value} precisa ser lista.",
            )
        values.append(rule.to_config())
        self._record_event(
            "permission_rule_added",
            {"effect": normalized_effect.value, "rule": rule.to_config()},
        )
        return rule

    def remove_rule(
        self,
        effect: PermissionEffect | str,
        position: int,
    ) -> PermissionRule:
        normalized_effect = PermissionEffect(str(effect))
        if position <= 0:
            raise PermissionManagerError(
                "Indice de regra invalido.",
                hint="Use um indice positivo exibido em /permissions.",
            )

        permissions = _mutable_permissions_section(self.config)
        values = permissions.get(normalized_effect.value, [])
        if not isinstance(values, list):
            raise PermissionManagerError(
                "Lista de permissoes invalida.",
                hint=f"O campo permissions.{normalized_effect.value} precisa ser lista.",
            )
        index = position - 1
        try:
            removed_value = values.pop(index)
        except IndexError as exc:
            raise PermissionManagerError(
                "Regra nao encontrada.",
                hint=f"Nao existe regra {position} em {normalized_effect.value}.",
            ) from exc

        rule = PermissionRule.from_config(normalized_effect, removed_value)
        self._record_event(
            "permission_rule_removed",
            {
                "effect": normalized_effect.value,
                "position": position,
                "rule": rule.to_config(),
            },
        )
        return rule

    def clear_rules(self, effect: PermissionEffect | str) -> int:
        normalized_effect = PermissionEffect(str(effect))
        permissions = _mutable_permissions_section(self.config)
        values = permissions.get(normalized_effect.value, [])
        if not isinstance(values, list):
            raise PermissionManagerError(
                "Lista de permissoes invalida.",
                hint=f"O campo permissions.{normalized_effect.value} precisa ser lista.",
            )
        count = len(values)
        permissions[normalized_effect.value] = []
        self._record_event(
            "permission_rules_cleared",
            {"effect": normalized_effect.value, "count": count},
        )
        return count

    def evaluate(self, request: PermissionRequest) -> PermissionEvaluation:
        action = _coerce_action(request.action)
        normalized_request = PermissionRequest(
            action=action,
            target=request.target,
            risk=request.risk,
            protected=request.protected,
            mutates=request.mutates,
            detail=request.detail,
        )
        mode = self.mode

        if str(request.risk).upper() == "BLOCKED":
            return PermissionEvaluation(
                request=normalized_request,
                decision=PermissionEffect.DENY,
                mode=mode,
                reason="risco bloqueado",
            )

        rules = self.rules()
        for effect in (
            PermissionEffect.DENY,
            PermissionEffect.ASK,
            PermissionEffect.ALLOW,
        ):
            for rule in rules:
                if rule.effect == effect and rule.matches(normalized_request):
                    return PermissionEvaluation(
                        request=normalized_request,
                        decision=effect,
                        mode=mode,
                        reason=rule.reason or f"regra {effect.value}",
                        matched_rule=rule,
                    )

        decision, reason = _mode_decision(mode, normalized_request)
        if (
            normalized_request.protected
            and decision == PermissionEffect.ALLOW
            and action in _PATH_SENSITIVE_ACTIONS
        ):
            decision = PermissionEffect.ASK
            reason = "path protegido"

        return PermissionEvaluation(
            request=normalized_request,
            decision=decision,
            mode=mode,
            reason=reason,
        )

    def authorize(
        self,
        request: PermissionRequest,
        *,
        approval_service: Any | None = None,
    ) -> PermissionEvaluation:
        evaluation = self.evaluate(request)
        final = evaluation
        if evaluation.requires_approval:
            if approval_service is None:
                final = PermissionEvaluation(
                    request=evaluation.request,
                    decision=PermissionEffect.DENY,
                    mode=evaluation.mode,
                    reason="aprovacao requerida e indisponivel",
                    matched_rule=evaluation.matched_rule,
                )
            else:
                approval = approval_service.request_approval(evaluation)
                final = PermissionEvaluation(
                    request=evaluation.request,
                    decision=(
                        PermissionEffect.ALLOW
                        if approval.approved
                        else PermissionEffect.DENY
                    ),
                    mode=evaluation.mode,
                    reason=approval.reason or evaluation.reason,
                    matched_rule=evaluation.matched_rule,
                )

        self.record_decision(final)
        return final

    def record_decision(self, evaluation: PermissionEvaluation) -> None:
        payload = {
            "action": str(evaluation.request.action),
            "target": evaluation.request.target,
            "decision": evaluation.decision.value,
            "mode": evaluation.mode.value,
            "reason": evaluation.reason,
            "risk": evaluation.request.risk,
            "protected": evaluation.request.protected,
        }
        self._record_event("permission_decision", payload)
        if self.session_store is not None and self.session_id:
            self.session_store.append_permission_decision(
                self.session_id,
                PermissionDecisionRecord(
                    action=str(evaluation.request.action),
                    decision=evaluation.decision.value,
                    target=evaluation.request.target,
                    mode=evaluation.mode.value,
                    reason=evaluation.reason,
                ),
            )

    def _record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.audit_logger is not None:
            self.audit_logger.record_event(
                event_type,
                payload,
                session_id=self.session_id,
            )


_PATH_SENSITIVE_ACTIONS = frozenset(
    {
        PermissionAction.FILE_READ,
        PermissionAction.FILE_WRITE,
        PermissionAction.PATCH,
    }
)


def _mode_decision(
    mode: ExecutionMode,
    request: PermissionRequest,
) -> tuple[PermissionEffect, str]:
    action = _coerce_action(request.action)
    risk = str(request.risk).upper()
    mutates = request.mutates

    if mode == ExecutionMode.LOCKED:
        return PermissionEffect.DENY, "modo locked exige regra allow explicita"

    if mode == ExecutionMode.PLAN:
        if action == PermissionAction.FILE_READ:
            return PermissionEffect.ALLOW, "modo plan permite leitura"
        if action == PermissionAction.GIT and not mutates:
            return PermissionEffect.ALLOW, "modo plan permite Git somente leitura"
        if action in {PermissionAction.COMMAND, PermissionAction.TOOL}:
            if risk == "SAFE" and not mutates:
                return PermissionEffect.ALLOW, "modo plan permite acao segura"
        return PermissionEffect.DENY, "modo plan bloqueia acoes mutaveis"

    if mode == ExecutionMode.DEFAULT:
        if action == PermissionAction.FILE_READ:
            return PermissionEffect.ALLOW, "modo default permite leitura"
        if action == PermissionAction.GIT and not mutates:
            return PermissionEffect.ALLOW, "modo default permite Git somente leitura"
        if action == PermissionAction.TOOL and risk == "SAFE" and not mutates:
            return PermissionEffect.ALLOW, "modo default permite tool segura"
        return PermissionEffect.ASK, "modo default exige aprovacao"

    if mode == ExecutionMode.ACCEPT_EDITS:
        if action in {
            PermissionAction.FILE_READ,
            PermissionAction.FILE_WRITE,
            PermissionAction.PATCH,
        }:
            return PermissionEffect.ALLOW, "modo accept_edits permite edicoes"
        if action == PermissionAction.GIT and not mutates:
            return (
                PermissionEffect.ALLOW,
                "modo accept_edits permite Git somente leitura",
            )
        if action == PermissionAction.TOOL and risk == "SAFE" and not mutates:
            return PermissionEffect.ALLOW, "modo accept_edits permite tool segura"
        return PermissionEffect.ASK, "modo accept_edits exige aprovacao"

    if mode == ExecutionMode.TRUSTED:
        return PermissionEffect.ALLOW, "modo trusted permite acao nao bloqueada"

    return PermissionEffect.DENY, "modo desconhecido"


def _permissions_section(config: Mapping[str, Any]) -> Mapping[str, Any]:
    value = config.get("permissions", {})
    return value if isinstance(value, Mapping) else {}


def _mutable_permissions_section(
    config: Mapping[str, Any] | MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    if not isinstance(config, MutableMapping):
        raise PermissionManagerError(
            "Configuracao imutavel.",
            hint="Nao foi possivel alterar permissoes nesta sessao.",
        )

    value = config.get("permissions")
    if value is None:
        config["permissions"] = {}
        value = config["permissions"]
    if not isinstance(value, MutableMapping):
        raise PermissionManagerError(
            "Secao de permissoes invalida.",
            hint="permissions precisa ser um objeto de configuracao.",
        )
    return value


def _coerce_action(value: PermissionAction | str) -> PermissionAction:
    if isinstance(value, PermissionAction):
        return value
    try:
        return PermissionAction(str(value))
    except ValueError as exc:
        raise PermissionManagerError(
            "Acao de permissao invalida.",
            hint=f"Acao informada: {value}",
        ) from exc


def _coerce_action_or_wildcard(value: PermissionAction | str) -> PermissionAction | str:
    text = str(value).strip()
    if text == "*":
        return "*"
    return _coerce_action(text)


def _list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value is None:
        return []
    return [value]


def _target_matches(
    *,
    pattern: str,
    target: str,
    action: PermissionAction,
) -> bool:
    normalized_pattern = _normalize_target(pattern)
    normalized_target = _normalize_target(target)
    if normalized_pattern in {"", "*"}:
        return True

    if normalized_pattern.endswith("/"):
        directory = normalized_pattern.rstrip("/")
        return normalized_target == directory or normalized_target.startswith(
            f"{directory}/"
        )

    if fnmatch.fnmatchcase(normalized_target, normalized_pattern):
        return True

    if action in {PermissionAction.COMMAND, PermissionAction.GIT}:
        return normalized_target.startswith(normalized_pattern)

    return False


def _normalize_target(value: str) -> str:
    return str(value).replace("\\", "/").strip().lower()
