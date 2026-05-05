"""Detect "composability surface": how many ways the repo can combine
with other systems.

In the post-LLM era, projects that combine cleanly (CLI + library +
MCP + multi-crate workspace) have more leverage than monoliths. Each
surface adds 2 points, up to 10.

Categories:
- CLI (binary / entrypoint)
- Library / public API (lib.rs, exported __init__, package.json main)
- MCP server (mcp.json manifest or .mcp/)
- HTTP / REST server (FastAPI, axum, express, ...)
- Workspace / multi-crate / monorepo
"""
from __future__ import annotations

import json
from pathlib import Path


def _has_real_file(p: Path, min_bytes: int = 50) -> bool:
    try:
        return p.is_file() and p.stat().st_size >= min_bytes
    except OSError:
        return False


def _read(p: Path, limit: int = 30_000) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def _has_cli(repo: Path) -> str | None:
    # Python: pyproject.toml [project.scripts]
    pp = _read(repo / "pyproject.toml", 10_000)
    if "[project.scripts]" in pp or "entry_points" in pp:
        return "Python CLI (project.scripts / entry_points)"
    # Rust: Cargo.toml [[bin]] or src/main.rs
    cargo = _read(repo / "Cargo.toml", 10_000)
    if "[[bin]]" in cargo or _has_real_file(repo / "src" / "main.rs"):
        return "Rust binary ([[bin]] / src/main.rs)"
    # Node: package.json bin
    pkg = _read(repo / "package.json", 10_000)
    if pkg:
        try:
            data = json.loads(pkg)
            if data.get("bin"):
                return "Node CLI (package.json bin)"
        except json.JSONDecodeError:
            pass
    # Go: cmd/* entrypoints or main.go at root
    if _has_real_file(repo / "main.go") or (repo / "cmd").is_dir():
        return "Go entrypoint (main.go / cmd/)"
    return None


def _has_library(repo: Path) -> str | None:
    # Rust
    if _has_real_file(repo / "src" / "lib.rs"):
        return "Rust library (src/lib.rs)"
    # Python: __init__.py with __all__ or pyproject [project.name]
    init = repo / "src"
    if init.is_dir():
        for sub in init.iterdir():
            if sub.is_dir() and (sub / "__init__.py").exists():
                content = _read(sub / "__init__.py", 5_000)
                if "__all__" in content or "from ." in content:
                    return f"Python package ({sub.name}/__init__.py)"
    # Go: explicit pkg/ with multiple files
    if (repo / "pkg").is_dir():
        return "Go library (pkg/)"
    # Node: package.json main / module / exports
    pkg = _read(repo / "package.json", 10_000)
    if pkg:
        try:
            data = json.loads(pkg)
            if data.get("main") or data.get("module") or data.get("exports"):
                return "Node library (package.json main/exports)"
        except json.JSONDecodeError:
            pass
    return None


def _has_mcp(repo: Path) -> str | None:
    for name in ("mcp.json", ".mcp.json"):
        if _has_real_file(repo / name, 50):
            return f"MCP manifest ({name})"
    if (repo / ".mcp").is_dir():
        return "MCP folder (.mcp/)"
    # Check deps for MCP servers
    deps = (
        _read(repo / "pyproject.toml", 5_000)
        + _read(repo / "package.json", 5_000)
        + _read(repo / "Cargo.toml", 5_000)
    ).lower()
    if "modelcontextprotocol" in deps or "mcp-server" in deps:
        return "MCP server (dependency declared)"
    return None


def _has_http_server(repo: Path) -> str | None:
    deps = (
        _read(repo / "pyproject.toml", 8_000)
        + _read(repo / "requirements.txt", 8_000)
        + _read(repo / "package.json", 8_000)
        + _read(repo / "Cargo.toml", 8_000)
        + _read(repo / "go.mod", 8_000)
    ).lower()
    markers = [
        ("fastapi", "FastAPI HTTP server"),
        ("starlette", "Starlette HTTP server"),
        ("flask", "Flask HTTP server"),
        ("axum", "axum HTTP server (Rust)"),
        ("actix-web", "actix HTTP server (Rust)"),
        ("rocket", "Rocket HTTP server (Rust)"),
        ("\"express\"", "Express HTTP server (Node)"),
        ("fastify", "Fastify HTTP server (Node)"),
        ("gin-gonic", "gin HTTP server (Go)"),
        ("net/http", "Go HTTP server"),
    ]
    for substr, label in markers:
        if substr in deps:
            return label
    return None


def _has_workspace(repo: Path) -> str | None:
    cargo = _read(repo / "Cargo.toml", 5_000)
    if "[workspace]" in cargo:
        return "Cargo workspace (multi-crate)"
    # npm/pnpm workspace
    pkg = _read(repo / "package.json", 8_000)
    if "\"workspaces\"" in pkg:
        return "npm/yarn/pnpm workspace"
    if (repo / "pnpm-workspace.yaml").exists():
        return "pnpm workspace"
    # Multiple packages in monorepo layout
    crates_dir = repo / "crates"
    if crates_dir.is_dir() and len(list(crates_dir.iterdir())) >= 3:
        return f"Multi-crate monorepo (crates/ with {len(list(crates_dir.iterdir()))} children)"
    return None


DETECTORS = (
    _has_cli,
    _has_library,
    _has_mcp,
    _has_http_server,
    _has_workspace,
)


MONOREPO_SUBDIRS = ("crates", "packages", "sdks", "apps", "services", "modules")


def _candidate_roots(repo_path: Path) -> list[Path]:
    """Return roots to inspect: the repo + one level inside typical monorepos."""
    roots = [repo_path]
    for sub in MONOREPO_SUBDIRS:
        d = repo_path / sub
        if d.is_dir():
            for child in d.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    roots.append(child)
    return roots


def score_composability(repo_path: Path) -> tuple[int, list[str]]:
    """Return (score 0-10, list of detected surfaces).

    Inspects the root plus one level inside typical monorepo
    directories (crates/, sdks/, packages/, ...) so we don't miss
    signals in polyglot or multi-package projects.
    """
    surfaces: list[str] = []
    seen_categories: set[int] = set()
    roots = _candidate_roots(repo_path)
    for root in roots:
        for idx, detector in enumerate(DETECTORS):
            if idx in seen_categories:
                continue
            s = detector(root)
            if s:
                # For non-root roots, prefix with the relative path.
                if root != repo_path:
                    try:
                        rel = root.relative_to(repo_path)
                        s = f"{s} @ {rel}"
                    except ValueError:
                        pass
                surfaces.append(s)
                seen_categories.add(idx)
    return min(len(surfaces) * 2, 10), surfaces
