"""Construye un contexto rico del proyecto para análisis de negocio.

Filosofía: no nos limitamos al README. Construimos un dossier que incluye:
  - README + docs principales
  - CHANGELOG (revela trayectoria y madurez)
  - Estructura del proyecto (revela alcance real)
  - Manifest files (deps revelan stack y ambición)
  - Muestras de código de entry points y APIs públicas
  - Issues y PRs recientes (qué pide la gente)
  - Commits recientes (qué se está construyendo)
  - Examples/ (qué casos de uso resuelve realmente)

El LLM recibe evidencia, no marketing.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import tiktoken

from ..models import RepoMeta

# Archivos de documentación de alta señal
DOC_FILES = [
    "README.md", "README.rst", "README.txt", "README",
    "CHANGELOG.md", "CHANGELOG.rst", "HISTORY.md",
    "ARCHITECTURE.md", "ROADMAP.md", "VISION.md",
    "CONTRIBUTING.md", "GOVERNANCE.md",
]

MANIFEST_FILES = [
    "pyproject.toml", "setup.py", "requirements.txt",
    "package.json", "Cargo.toml", "go.mod", "pom.xml",
    "build.gradle", "Gemfile", "composer.json",
]

CODE_EXTENSIONS = {".py", ".rs", ".js", ".ts", ".go", ".java", ".rb"}

IGNORE_DIRS = {".git", "node_modules", "target", "dist", "build",
               "__pycache__", ".venv", "venv", "vendor", ".idea"}

# Token budget (Claude Opus context limit es ~200k pero queremos eficiencia)
MAX_CONTEXT_TOKENS = 60_000


def _read_text(path: Path, max_chars: int = 50_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except OSError:
        return ""


def _count_tokens(text: str) -> int:
    """Estimación rápida con tiktoken (cl100k_base ≈ Claude tokenizer)."""
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


def gather_docs(repo_path: Path) -> dict[str, str]:
    """Recoge archivos de documentación principales."""
    docs = {}
    for name in DOC_FILES:
        p = repo_path / name
        if p.exists() and p.is_file():
            content = _read_text(p, max_chars=30_000)
            if content.strip():
                docs[name] = content
    # docs/ folder (top-level files only)
    docs_dir = repo_path / "docs"
    if docs_dir.is_dir():
        for f in sorted(docs_dir.glob("*.md"))[:5]:
            docs[f"docs/{f.name}"] = _read_text(f, max_chars=15_000)
    return docs


def gather_manifests(repo_path: Path) -> dict[str, str]:
    """Recoge archivos de manifest (deps, build config)."""
    manifests = {}
    for name in MANIFEST_FILES:
        p = repo_path / name
        if p.exists():
            manifests[name] = _read_text(p, max_chars=15_000)
    return manifests


def project_structure(repo_path: Path, max_depth: int = 3, max_entries: int = 200) -> str:
    """Genera un árbol del proyecto (depth-limited)."""
    lines: list[str] = []
    repo_path = repo_path.resolve()

    def walk(current: Path, depth: int, prefix: str = ""):
        if depth > max_depth or len(lines) >= max_entries:
            return
        try:
            entries = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return
        entries = [e for e in entries if e.name not in IGNORE_DIRS and not e.name.startswith(".")]
        for e in entries:
            if len(lines) >= max_entries:
                lines.append(f"{prefix}... (truncated)")
                return
            marker = "📁 " if e.is_dir() else "   "
            lines.append(f"{prefix}{marker}{e.name}")
            if e.is_dir():
                walk(e, depth + 1, prefix + "  ")

    lines.append(f"📁 {repo_path.name}/")
    walk(repo_path, 1, "  ")
    return "\n".join(lines)


def gather_code_samples(repo_path: Path, primary_lang: str | None,
                        max_files: int = 6, max_chars_per_file: int = 8_000) -> dict[str, str]:
    """Recoge muestras de código representativas: entry points, APIs públicas, examples."""
    samples: dict[str, str] = {}

    # 1. Buscar entry points obvios
    candidates: list[Path] = []

    # Convención por lenguaje
    entry_patterns = {
        "Rust": ["src/main.rs", "src/lib.rs"],
        "Python": ["main.py", "app.py", "src/__init__.py"],
        "JavaScript": ["index.js", "src/index.js", "src/main.js"],
        "TypeScript": ["src/index.ts", "src/main.ts"],
        "Go": ["main.go", "cmd/main.go"],
    }
    for entry in entry_patterns.get(primary_lang or "", []):
        p = repo_path / entry
        if p.exists():
            candidates.append(p)

    # 2. Examples folder es oro: muestra casos de uso reales
    examples_dir = repo_path / "examples"
    if examples_dir.is_dir():
        for f in list(examples_dir.iterdir())[:3]:
            if f.is_file() and f.suffix in CODE_EXTENSIONS or (f.is_file() and f.suffix in {".lex"}):
                candidates.append(f)

    # 3. Si es un workspace Rust, incluir Cargo.toml de crates
    crates_dir = repo_path / "crates"
    if crates_dir.is_dir():
        for crate in sorted(crates_dir.iterdir())[:5]:
            tom = crate / "Cargo.toml"
            if tom.exists():
                candidates.append(tom)

    for p in candidates[:max_files]:
        try:
            rel = p.relative_to(repo_path)
        except ValueError:
            continue
        content = _read_text(p, max_chars=max_chars_per_file)
        if content.strip():
            samples[str(rel)] = content

    return samples


def fetch_recent_issues(meta: RepoMeta, n: int = 10) -> list[dict[str, Any]]:
    """Trae las N issues más recientes (abiertas y cerradas) desde GitHub."""
    if not meta.owner or not meta.name:
        return []
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = httpx.get(
            f"https://api.github.com/repos/{meta.owner}/{meta.name}/issues",
            params={"state": "all", "per_page": n, "sort": "updated"},
            headers=headers,
            timeout=10.0,
        )
        if r.status_code != 200:
            return []
        issues = [i for i in r.json() if "pull_request" not in i]
        return [{
            "number": i.get("number"),
            "title": i.get("title", "")[:200],
            "state": i.get("state"),
            "comments": i.get("comments", 0),
            "body_excerpt": (i.get("body") or "")[:500],
        } for i in issues[:n]]
    except (httpx.HTTPError, ValueError):
        return []


def fetch_recent_commits(meta: RepoMeta, n: int = 15) -> list[dict[str, Any]]:
    """Trae N commits recientes para revelar qué se está construyendo."""
    if not meta.owner or not meta.name:
        return []
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = httpx.get(
            f"https://api.github.com/repos/{meta.owner}/{meta.name}/commits",
            params={"per_page": n},
            headers=headers,
            timeout=10.0,
        )
        if r.status_code != 200:
            return []
        return [{
            "sha": c.get("sha", "")[:7],
            "message": (c.get("commit", {}).get("message") or "").split("\n")[0][:200],
            "date": c.get("commit", {}).get("author", {}).get("date"),
        } for c in r.json()[:n]]
    except (httpx.HTTPError, ValueError):
        return []


def build_business_context(meta: RepoMeta, repo_path: Path) -> dict[str, Any]:
    """Punto de entrada: ensambla todo el dossier para análisis de negocio."""
    docs = gather_docs(repo_path)
    manifests = gather_manifests(repo_path)
    structure = project_structure(repo_path)
    code_samples = gather_code_samples(repo_path, meta.primary_language)
    issues = fetch_recent_issues(meta)
    commits = fetch_recent_commits(meta)

    context = {
        "meta": {
            "name": meta.name,
            "owner": meta.owner,
            "primary_language": meta.primary_language,
            "languages": meta.languages,
            "total_loc": meta.total_loc,
            "total_files": meta.total_files,
        },
        "docs": docs,
        "manifests": manifests,
        "structure": structure,
        "code_samples": code_samples,
        "recent_issues": issues,
        "recent_commits": commits,
    }

    # Estimación de tokens (informativo)
    blob = str(context)
    context["_token_estimate"] = _count_tokens(blob)
    return context
