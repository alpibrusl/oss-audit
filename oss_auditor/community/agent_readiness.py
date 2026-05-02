"""Detecta señales de "agent-readiness": qué tan preparado está el repo
para ser descubierto y operado por agentes de IA.

En la era post-LLM, un proyecto solo-autor puede ser excelente; lo que
distingue a uno serio es si está diseñado para que humanos *y agentes*
lo encuentren, lo entiendan y lo extiendan sin fricción.

Categorías detectadas (2 pts cada una, máx 10):
  - Claude Code context (CLAUDE.md, .claude/)
  - Universal agent context (AGENTS.md)
  - Cursor / Copilot rules
  - ACLI / skill manifests (.cli/, SKILL.md)
  - MCP server manifest (mcp.json, .mcp/)
  - Examples runables (examples/ con scripts)

Filosofía: presencia + contenido no-trivial. Un CLAUDE.md vacío de 5
bytes no cuenta — pedimos un mínimo de bytes para evitar gaming.
"""
from __future__ import annotations

from pathlib import Path

MIN_BYTES = 200  # umbral mínimo para considerar un archivo "real"


def _has_real_file(p: Path) -> bool:
    return p.is_file() and p.stat().st_size >= MIN_BYTES


def _has_nonempty_dir(p: Path) -> bool:
    return p.is_dir() and any(p.iterdir())


def _category_claude(repo: Path) -> str | None:
    if _has_real_file(repo / "CLAUDE.md") or _has_nonempty_dir(repo / ".claude"):
        return "Claude Code context (CLAUDE.md/.claude)"
    return None


def _category_universal(repo: Path) -> str | None:
    if _has_real_file(repo / "AGENTS.md"):
        return "Universal agent context (AGENTS.md)"
    return None


def _category_editor_rules(repo: Path) -> str | None:
    if (repo / ".cursorrules").exists() or _has_nonempty_dir(repo / ".cursor" / "rules"):
        return "Cursor rules"
    if _has_real_file(repo / ".github" / "copilot-instructions.md"):
        return "Copilot instructions"
    return None


def _category_skill_manifest(repo: Path) -> str | None:
    if _has_nonempty_dir(repo / ".cli"):
        return "ACLI skill folder (.cli/)"
    if _has_real_file(repo / "SKILL.md"):
        return "Agent skill manifest (SKILL.md)"
    return None


def _category_mcp(repo: Path) -> str | None:
    for name in ("mcp.json", ".mcp.json"):
        if _has_real_file(repo / name):
            return f"MCP server manifest ({name})"
    if _has_nonempty_dir(repo / ".mcp"):
        return "MCP folder (.mcp/)"
    return None


def _category_examples(repo: Path) -> str | None:
    examples = repo / "examples"
    if not examples.is_dir():
        return None
    runnable_exts = {".py", ".js", ".ts", ".rs", ".go", ".sh"}
    has_runnable = any(
        f.is_file() and f.suffix in runnable_exts
        for f in examples.rglob("*")
    )
    if has_runnable:
        return "Runnable examples folder"
    return None


CATEGORIES = (
    _category_claude,
    _category_universal,
    _category_editor_rules,
    _category_skill_manifest,
    _category_mcp,
    _category_examples,
)


def score_agent_readiness(repo_path: Path) -> tuple[int, list[str]]:
    """Devuelve (score 0-10, lista de signals detectadas)."""
    signals: list[str] = []
    for detector in CATEGORIES:
        signal = detector(repo_path)
        if signal:
            signals.append(signal)
    score = min(len(signals) * 2, 10)
    return score, signals
