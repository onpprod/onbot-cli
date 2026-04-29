"""Comandos internos minimos da etapa interativa."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from onbot_cli.commands.router import (
    CommandContext,
    CommandError,
    CommandResult,
    CommandRouter,
    CommandSpec,
)
from onbot_cli.security.permissions import (
    ExecutionMode,
    PermissionAction,
    PermissionEffect,
    PermissionManager,
    PermissionManagerError,
    PermissionRule,
)
from onbot_cli.tools import create_internal_tool_registry


SUPPORTED_MODES = tuple(mode.value for mode in ExecutionMode)
CUSTOM_COMMAND_EXTENSIONS = {".md", ".yaml", ".yml"}


def create_default_router() -> CommandRouter:
    """Cria o roteador com os comandos internos conhecidos."""

    return CommandRouter(_build_specs())


def _build_specs() -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            name="help",
            summary="Lista comandos internos e ajuda contextual.",
            usage="/help [comando]",
            handler=_help,
        ),
        CommandSpec(
            name="exit",
            summary="Encerra a sessao interativa.",
            usage="/exit",
            handler=_exit,
            aliases=("quit",),
        ),
        CommandSpec(
            name="clear",
            summary="Limpa a area visual do terminal.",
            usage="/clear",
            handler=_clear,
        ),
        CommandSpec(
            name="status",
            summary="Mostra workspace, sessao, modo e Git detectado.",
            usage="/status",
            handler=_status,
        ),
        CommandSpec(
            name="history",
            summary="Mostra entradas recentes persistidas localmente.",
            usage="/history [limite]",
            handler=_history,
        ),
        CommandSpec(
            name="config",
            summary="Exibe a configuracao ativa com segredos mascarados.",
            usage="/config [secao]",
            handler=_config,
        ),
        CommandSpec(
            name="tools",
            summary="Consulta o contrato inicial do catalogo de tools.",
            usage="/tools",
            handler=_tools,
        ),
        CommandSpec(
            name="permissions",
            summary="Consulta e altera regras de permissao da sessao.",
            usage="/permissions [add|remove|clear] ...",
            handler=_permissions,
        ),
        CommandSpec(
            name="mode",
            summary="Consulta ou altera o modo de execucao ativo.",
            usage="/mode [plan|default|accept_edits|trusted|locked]",
            handler=_mode,
        ),
        CommandSpec(
            name="git",
            summary="Consulta deteccao basica de repositorio Git.",
            usage="/git",
            handler=_git,
        ),
        CommandSpec(
            name="hooks",
            summary="Consulta configuracao inicial de hooks.",
            usage="/hooks",
            handler=_hooks,
        ),
        CommandSpec(
            name="commands",
            summary="Lista comandos customizados descobertos no workspace.",
            usage="/commands",
            handler=_commands,
        ),
    )


def _help(context: CommandContext, args: Sequence[str]) -> CommandResult:
    specs = _build_specs()
    if len(args) > 1:
        raise CommandError("Uso invalido.", hint="Use /help ou /help <comando>.")

    if args:
        name = args[0].lstrip("/").lower()
        spec = _spec_by_name(name, specs)
        if spec is None:
            raise CommandError(
                f"Comando desconhecido: /{name}",
                hint="Use /help para ver a lista completa.",
            )
        body = "\n".join(
            [
                spec.summary,
                "",
                f"Uso: {spec.usage}",
            ]
        )
        context.renderer.panel(spec.display_name, body)
        return CommandResult(name="help")

    context.renderer.commands(
        (spec.display_name, spec.summary, spec.usage) for spec in specs
    )
    return CommandResult(name="help")


def _exit(context: CommandContext, args: Sequence[str]) -> CommandResult:
    if args:
        raise CommandError("Uso invalido.", hint="Use /exit sem argumentos.")
    context.renderer.info("Sessao encerrando.")
    return CommandResult(name="exit", should_exit=True)


def _clear(context: CommandContext, args: Sequence[str]) -> CommandResult:
    if args:
        raise CommandError("Uso invalido.", hint="Use /clear sem argumentos.")
    context.renderer.console.clear()
    return CommandResult(name="clear")


def _status(context: CommandContext, args: Sequence[str]) -> CommandResult:
    if args:
        raise CommandError("Uso invalido.", hint="Use /status sem argumentos.")

    context.renderer.status(
        workspace=context.workspace.root,
        persistence_dir=context.layout.onbot_dir,
        session_id=context.session_id,
        mode=_active_mode(context.config),
        git_detected=_git_dir(context.layout.root).exists(),
    )
    return CommandResult(name="status")


def _history(context: CommandContext, args: Sequence[str]) -> CommandResult:
    if len(args) > 1:
        raise CommandError("Uso invalido.", hint="Use /history ou /history <limite>.")

    limit = 20
    if args:
        try:
            limit = int(args[0])
        except ValueError as exc:
            raise CommandError(
                "Limite invalido.",
                hint="Informe um numero inteiro positivo.",
            ) from exc
        if limit <= 0:
            raise CommandError(
                "Limite invalido.",
                hint="Informe um numero inteiro positivo.",
            )

    context.renderer.history(context.history.read(limit=limit))
    return CommandResult(name="history")


def _config(context: CommandContext, args: Sequence[str]) -> CommandResult:
    if len(args) > 1:
        raise CommandError("Uso invalido.", hint="Use /config ou /config <secao>.")

    section = args[0] if args else None
    if section is not None and section not in context.config:
        raise CommandError(
            f"Secao de configuracao desconhecida: {section}",
            hint=f"Secoes disponiveis: {', '.join(context.config.keys())}",
        )
    context.renderer.config(context.config, section=section)
    return CommandResult(name="config")


def _tools(context: CommandContext, args: Sequence[str]) -> CommandResult:
    if args:
        raise CommandError("Uso invalido.", hint="Use /tools sem argumentos.")

    registry = create_internal_tool_registry(context.config)
    rows = [
        (
            entry.name,
            entry.description,
            entry.origin,
            entry.risk_level,
            _schema_summary(entry.input_schema),
            "habilitada" if entry.enabled else "desabilitada",
        )
        for entry in registry.list_tools(include_disabled=True)
    ]
    context.renderer.table(
        "Tools",
        ("Nome", "Descricao", "Origem", "Risco", "Entradas", "Status"),
        rows,
    )
    return CommandResult(name="tools")


def _permissions(context: CommandContext, args: Sequence[str]) -> CommandResult:
    manager = _permission_manager(context)

    if args:
        subcommand = args[0].lower()
        if subcommand == "add":
            context.renderer.info(_permissions_add(manager, args))
            return CommandResult(name="permissions")
        if subcommand == "remove":
            context.renderer.info(_permissions_remove(manager, args))
            return CommandResult(name="permissions")
        if subcommand == "clear":
            context.renderer.info(_permissions_clear(manager, args))
            return CommandResult(name="permissions")
        raise CommandError(
            "Subcomando de permissoes desconhecido.",
            hint=(
                "Use /permissions, /permissions add <allow|ask|deny> "
                "<acao> [alvo], /permissions remove <efeito> <indice> "
                "ou /permissions clear <efeito>."
            ),
        )

    config = _section(context.config, "permissions")
    rows: list[tuple[str, str, str, str, str]] = [
        ("mode", "-", manager.mode.value, "-", "modo ativo"),
    ]
    for effect in (
        PermissionEffect.DENY,
        PermissionEffect.ASK,
        PermissionEffect.ALLOW,
    ):
        values = _list_value(config.get(effect.value))
        if not values:
            rows.append((effect.value, "-", "-", "-", "sem regras"))
            continue
        for index, value in enumerate(values, start=1):
            rule = PermissionRule.from_config(effect, value)
            rows.append(
                (
                    effect.value,
                    str(index),
                    str(rule.action),
                    rule.target,
                    rule.reason or "-",
                )
            )
    context.renderer.table(
        "Permissoes",
        ("Tipo", "Indice", "Acao", "Alvo", "Motivo"),
        rows,
    )
    context.renderer.table(
        "Paths protegidos",
        ("Padrao",),
        ((item,) for item in _list_value(config.get("protected_paths"))),
    )
    return CommandResult(name="permissions")


def _mode(context: CommandContext, args: Sequence[str]) -> CommandResult:
    manager = _permission_manager(context)

    if len(args) > 1:
        raise CommandError(
            "Uso invalido.",
            hint="Use /mode ou /mode <plan|default|accept_edits|trusted|locked>.",
        )

    if args:
        try:
            mode = manager.set_mode(args[0])
        except (ValueError, PermissionManagerError) as exc:
            raise CommandError(
                "Modo invalido.",
                hint=f"Modos suportados: {', '.join(SUPPORTED_MODES)}.",
            ) from exc
        context.renderer.info(f"Modo ativo alterado para: {mode.value}")
        return CommandResult(name="mode")

    rows = [
        ("ativo", manager.mode.value),
        ("suportados", ", ".join(SUPPORTED_MODES)),
        ("alteracao", "/mode <modo>"),
    ]
    context.renderer.table("Modo", ("Campo", "Valor"), rows)
    return CommandResult(name="mode")


def _git(context: CommandContext, args: Sequence[str]) -> CommandResult:
    if args:
        raise CommandError("Uso invalido.", hint="Use /git sem argumentos.")

    git_dir = _git_dir(context.layout.root)
    rows = [
        ("detectado", "sim" if git_dir.exists() else "nao"),
        ("diretorio", git_dir if git_dir.exists() else "-"),
        ("operacoes", "status/diff completos previstos para a etapa 07"),
    ]
    context.renderer.table("Git", ("Campo", "Valor"), rows)
    return CommandResult(name="git")


def _hooks(context: CommandContext, args: Sequence[str]) -> CommandResult:
    if args:
        raise CommandError("Uso invalido.", hint="Use /hooks sem argumentos.")

    config = _section(context.config, "hooks")
    rows = [
        ("enabled", str(config.get("enabled", True))),
        ("paths", ", ".join(_list_value(config.get("paths"))) or "-"),
        ("manager", "previsto para a etapa 07"),
    ]
    context.renderer.table("Hooks", ("Campo", "Valor"), rows)
    return CommandResult(name="hooks")


def _commands(context: CommandContext, args: Sequence[str]) -> CommandResult:
    if args:
        raise CommandError("Uso invalido.", hint="Use /commands sem argumentos.")

    custom_files = discover_custom_command_files(context.layout.commands_dir)
    if not custom_files:
        context.renderer.info("Nenhum comando customizado encontrado.")
        return CommandResult(name="commands")

    context.renderer.table(
        "Comandos customizados",
        ("Comando", "Arquivo"),
        (
            (f"/{path.stem}", path.relative_to(context.layout.root))
            for path in custom_files
        ),
    )
    return CommandResult(name="commands")


def discover_custom_command_names(commands_dir: Path) -> tuple[str, ...]:
    """Descobre nomes de comandos customizados por arquivos Markdown/YAML."""

    return tuple(f"/{path.stem}" for path in discover_custom_command_files(commands_dir))


def discover_custom_command_files(commands_dir: Path) -> tuple[Path, ...]:
    if not commands_dir.exists():
        return ()
    return tuple(
        sorted(
            path
            for path in commands_dir.iterdir()
            if path.is_file() and path.suffix.lower() in CUSTOM_COMMAND_EXTENSIONS
        )
    )


def _spec_by_name(
    name: str,
    specs: Sequence[CommandSpec],
) -> CommandSpec | None:
    for spec in specs:
        if spec.name == name or name in spec.aliases:
            return spec
    return None


def _active_mode(config: Mapping[str, Any]) -> str:
    permissions = _section(config, "permissions")
    return str(permissions.get("mode", "default"))


def _section(config: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = config.get(name, {})
    return value if isinstance(value, Mapping) else {}


def _list_value(value: Any) -> list[Any]:
    if isinstance(value, list | tuple):
        return list(value)
    if value is None:
        return []
    return [value]


def _schema_summary(schema: Mapping[str, Any]) -> str:
    properties = schema.get("properties", {})
    required = set(schema.get("required", ()))
    if not isinstance(properties, Mapping) or not properties:
        return "-"

    parts: list[str] = []
    for name, definition in properties.items():
        suffix = "*" if name in required else ""
        if isinstance(definition, Mapping):
            parts.append(f"{name}{suffix}:{definition.get('type', 'any')}")
        else:
            parts.append(f"{name}{suffix}:any")
    return ", ".join(parts)


def _git_dir(workspace: Path) -> Path:
    return workspace / ".git"


def _permission_manager(context: CommandContext) -> PermissionManager:
    return PermissionManager(
        context.config,
        audit_logger=context.audit_logger,
        session_store=context.session_store,
        session_id=context.session_id,
    )


def _permissions_add(
    manager: PermissionManager,
    args: Sequence[str],
) -> str:
    if len(args) < 3:
        raise CommandError(
            "Uso invalido.",
            hint=(
                "Use /permissions add <allow|ask|deny> <acao> [alvo]. "
                f"Acoes: {', '.join(action.value for action in PermissionAction)}."
            ),
        )

    effect = args[1].lower()
    action = args[2].lower()
    target = " ".join(args[3:]) if len(args) > 3 else "*"
    try:
        rule = manager.add_rule(effect, action, target)
    except (ValueError, PermissionManagerError) as exc:
        raise CommandError(
            "Regra de permissao invalida.",
            hint=(
                "Use efeito allow, ask ou deny e uma acao valida: "
                f"{', '.join(action.value for action in PermissionAction)}."
            ),
        ) from exc
    return f"Regra adicionada: {rule.effect.value} {rule.action} {rule.target}"


def _permissions_remove(
    manager: PermissionManager,
    args: Sequence[str],
) -> str:
    if len(args) != 3:
        raise CommandError(
            "Uso invalido.",
            hint="Use /permissions remove <allow|ask|deny> <indice>.",
        )

    try:
        position = int(args[2])
    except ValueError as exc:
        raise CommandError(
            "Indice invalido.",
            hint="Informe o indice numerico exibido em /permissions.",
        ) from exc

    try:
        rule = manager.remove_rule(args[1].lower(), position)
    except (ValueError, PermissionManagerError) as exc:
        raise CommandError(
            "Nao foi possivel remover a regra.",
            hint=str(getattr(exc, "hint", None) or exc),
        ) from exc
    return f"Regra removida: {rule.effect.value} {rule.action} {rule.target}"


def _permissions_clear(
    manager: PermissionManager,
    args: Sequence[str],
) -> str:
    if len(args) != 2:
        raise CommandError(
            "Uso invalido.",
            hint="Use /permissions clear <allow|ask|deny>.",
        )

    try:
        count = manager.clear_rules(args[1].lower())
    except (ValueError, PermissionManagerError) as exc:
        raise CommandError(
            "Nao foi possivel limpar regras.",
            hint=str(getattr(exc, "hint", None) or exc),
        ) from exc
    return f"Regras removidas: {count}"
