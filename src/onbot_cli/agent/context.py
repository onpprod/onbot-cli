"""Selecao e cache de contexto estrutural para o agente."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from onbot_cli.security.paths import PathGuard, PathGuardError, PathOperation
from onbot_cli.storage.cache import ProjectSummaryCache
from onbot_cli.tools.filesystem import iter_workspace_paths, max_file_size_bytes
from onbot_cli.tools.summary import generate_project_summary
from onbot_cli.workspace import WorkspaceLayout


@dataclass(frozen=True, slots=True)
class ContextSnippet:
    """Trecho textual selecionado para o contexto do LLM."""

    path: str
    start_line: int
    end_line: int
    content: str
    score: int


@dataclass(frozen=True, slots=True)
class ContextBundle:
    """Resumo estrutural e snippets selecionados com limites aplicados."""

    summary: Mapping[str, Any]
    snippets: tuple[ContextSnippet, ...]
    total_chars: int
    truncated: bool = False


class ContextManager:
    """Controla contexto enviado ao agente e cacheia resumo estrutural."""

    def __init__(
        self,
        layout: WorkspaceLayout,
        config: Mapping[str, Any],
        *,
        path_guard: PathGuard | None = None,
    ) -> None:
        self.layout = layout
        self.config = config
        self.path_guard = path_guard or PathGuard(layout.root)
        self.cache = ProjectSummaryCache(layout)

    def structural_summary(self, *, refresh: bool = False) -> Mapping[str, Any]:
        cached = self.cache.read()
        if not refresh and cached.get("generated_at"):
            return cached

        summary = generate_project_summary(
            self.layout,
            self.config,
            path_guard=self.path_guard,
        )
        self.cache.write(summary)
        return self.cache.read()

    def build_context(
        self,
        query: str,
        *,
        paths: tuple[str, ...] | None = None,
        max_snippets: int = 8,
        max_file_chars: int = 1200,
        max_total_chars: int = 6000,
    ) -> ContextBundle:
        summary = self.structural_summary()
        candidates = self._candidate_files(paths)
        tokens = _tokens(query)
        snippets = self._ranked_snippets(
            candidates,
            tokens,
            max_file_chars=max_file_chars,
        )

        selected: list[ContextSnippet] = []
        total_chars = 0
        truncated = False
        for snippet in snippets:
            if len(selected) >= max_snippets:
                truncated = True
                break
            next_total = total_chars + len(snippet.content)
            if next_total > max_total_chars:
                truncated = True
                break
            selected.append(snippet)
            total_chars = next_total

        return ContextBundle(
            summary=summary,
            snippets=tuple(selected),
            total_chars=total_chars,
            truncated=truncated,
        )

    def _candidate_files(self, paths: tuple[str, ...] | None) -> list[Path]:
        if paths:
            resolved: list[Path] = []
            for path in paths:
                try:
                    guarded = self.path_guard.resolve(path, operation=PathOperation.READ)
                except PathGuardError:
                    continue
                if guarded.path.is_file() and not guarded.protected:
                    resolved.append(guarded.path)
            return resolved

        limit = max_file_size_bytes(self.config)
        candidates: list[Path] = []
        for path in iter_workspace_paths(
            self.layout.root,
            self.config,
            recursive=True,
            include_hidden=False,
            path_guard=self.path_guard,
        ):
            if not path.is_file():
                continue
            try:
                guarded = self.path_guard.resolve(path, operation=PathOperation.READ)
            except PathGuardError:
                continue
            if guarded.protected or path.stat().st_size > limit:
                continue
            candidates.append(path)
        return candidates

    def _ranked_snippets(
        self,
        candidates: list[Path],
        tokens: tuple[str, ...],
        *,
        max_file_chars: int,
    ) -> list[ContextSnippet]:
        snippets: list[ContextSnippet] = []
        for path in candidates:
            text = _read_text(path, limit=max_file_chars)
            if text is None:
                continue
            relative = path.relative_to(self.layout.root).as_posix()
            score = _score(relative, text, tokens)
            if score <= 0 and tokens:
                continue
            snippets.append(_snippet_for(relative, text, tokens, score))
        return sorted(snippets, key=lambda item: (-item.score, item.path))


def _tokens(query: str) -> tuple[str, ...]:
    return tuple(
        token.lower()
        for token in query.replace("_", " ").replace("-", " ").split()
        if len(token) >= 2
    )


def _read_text(path: Path, *, limit: int) -> str | None:
    data = path.read_bytes()[:limit]
    if b"\x00" in data:
        return None
    return data.decode("utf-8", errors="replace")


def _score(relative: str, text: str, tokens: tuple[str, ...]) -> int:
    if not tokens:
        return 1
    haystacks = [relative.lower(), text.lower()]
    counts = Counter()
    for token in tokens:
        counts[token] = haystacks[0].count(token) * 5 + haystacks[1].count(token)
    return sum(counts.values())


def _snippet_for(
    relative: str,
    text: str,
    tokens: tuple[str, ...],
    score: int,
) -> ContextSnippet:
    lines = text.splitlines()
    first_match = 0
    lowered = [line.lower() for line in lines]
    for index, line in enumerate(lowered):
        if any(token in line for token in tokens):
            first_match = index
            break

    start = max(first_match - 2, 0)
    end = min(first_match + 3, len(lines))
    return ContextSnippet(
        path=relative,
        start_line=start + 1,
        end_line=end,
        content="\n".join(lines[start:end]),
        score=score,
    )
