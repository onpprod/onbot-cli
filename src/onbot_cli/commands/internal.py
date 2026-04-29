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


SUPPORTED_MODES = ("plan", "default", "accept_edits", "trusted", "locked")
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
            summary="Consulta regras e paths protegidos configurados.",
            usage="/permissions",
            handler=_permissions,
        ),
        CommandSpec(
            name="mode",
            summary="Consulta o modo de execucao ativo.",
            usage="/mode",
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

    config = _section(context.config, "tools")
    paths = _list_value(config.get("paths"))
    enabled = _list_value(config.get("enabled"))
    disabled = _list_value(config.get("disabled"))

    rows = [
        ("registry", "stub", "Tool Registry sera implementado na etapa 05."),
        ("paths", ", ".join(paths) or "-", "Diretorios configurados."),
        ("enabled", ", ".join(enabled) or "-", "Lista permitida por config."),
        ("disabled", ", ".join(disabled) or "-", "Lista bloqueada por config."),
    ]
    context.renderer.table("Tools", ("Item", "Valor", "Contrato"), rows)
    return CommandResult(name="tools")


def _permissions(context: CommandContext, args: Sequence[str]) -> CommandResult:
    if args:
        raise CommandError("Uso invalido.", hint="Use /permissions sem argumentos.")

    config = _section(context.config, "permissions")
    rows = [
        ("mode", str(config.get("mode", "default"))),
        ("allow", ", ".join(_list_value(config.get("allow"))) or "-"),
        ("ask", ", ".join(_list_value(config.get("ask"))) or "-"),
        ("deny", ", ".join(_list_value(config.get("deny"))) or "-"),
        (
            "protected_paths",
            ", ".join(_list_value(config.get("protected_paths"))) or "-",
        ),
    ]
    context.renderer.table("Permissoes", ("Campo", "Valor"), rows)
    return CommandResult(name="permissions")


def _mode(context: CommandContext, args: Sequence[str]) -> CommandResult:
    if args:
        raise CommandError(
            "Troca de modo ainda nao esta disponivel.",
            hint="A etapa 04 implementara alteracao de modo e regras ativas.",
        )

    rows = [
        ("ativo", _active_mode(context.config)),
        ("suportados", ", ".join(SUPPORTED_MODES)),
        ("alteracao", "prevista para a etapa 04"),
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


def _list_value(value: Any) -> list[str]:
    if isinstance(value, list | tuple):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def _git_dir(workspace: Path) -> Path:
    return workspace / ".git"
