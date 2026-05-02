"""Ingesta del repo: clona desde URL o usa path local, detecta lenguajes."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from .models import RepoMeta

# Mapeo de extensión -> lenguaje (subset relevante para análisis técnico)
EXTENSION_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".cc": "C++",
    ".c": "C",
    ".h": "C",
    ".swift": "Swift",
}

IGNORE_DIRS = {
    ".git", "node_modules", "target", "dist", "build", "__pycache__",
    ".venv", "venv", ".tox", ".pytest_cache", ".mypy_cache", ".cargo",
    "vendor", ".idea", ".vscode", "out",
}


def parse_github_url(url: str) -> tuple[str, str] | None:
    """Extrae (owner, repo) de una URL de GitHub. Devuelve None si no es GitHub."""
    patterns = [
        r"github\.com[:/]([^/]+)/([^/.]+?)(?:\.git)?/?$",
        r"github\.com[:/]([^/]+)/([^/]+?)/?$",
    ]
    for pat in patterns:
        m = re.search(pat, url.strip())
        if m:
            return m.group(1), m.group(2).rstrip("/")
    return None


def parse_gist_url(url: str) -> tuple[str, str] | None:
    """Extrae (owner, gist_id) de una URL de gist. Devuelve None si no es gist."""
    m = re.search(r"gist\.github\.com[:/]([^/]+)/([0-9a-f]+)", url.strip())
    if m:
        return m.group(1), m.group(2)
    return None


def classify_repo_type(
    repo_path: Path, total_loc: int, has_remote_traction: bool = False
) -> tuple[str, str]:
    """Decide si el artefacto es `implementation` o `proposal`.

    Heurística:
    - Gist (lo decide el caller via is_gist) → siempre `proposal`.
    - LOC < 500 + (README + docs) > 5K chars + algún signal de tracción
      (caller pasa has_remote_traction) → `proposal`.
    - Else → `implementation`.

    Devuelve (tipo, razón humana).
    """
    if total_loc >= 500:
        return "implementation", f"{total_loc} LOC indica artefacto de código"

    doc_chars = 0
    for name in ("README.md", "README.rst", "README", "SPEC.md", "RFC.md", "PROPOSAL.md"):
        p = repo_path / name
        if p.is_file():
            try:
                doc_chars += p.stat().st_size
            except OSError:
                pass
    docs_dir = repo_path / "docs"
    if docs_dir.is_dir():
        for f in docs_dir.glob("*.md"):
            try:
                doc_chars += f.stat().st_size
            except OSError:
                pass

    if doc_chars >= 5_000 and (has_remote_traction or total_loc < 50):
        return (
            "proposal",
            f"{total_loc} LOC + {doc_chars:,} chars de docs sugieren artefacto-spec",
        )
    return "implementation", "código presente, no parece spec puro"


def clone_repo(url: str, dest: Path) -> Path:
    """Clona un repo (shallow) en dest. Devuelve path al directorio."""
    target = dest / "repo"
    if target.exists():
        shutil.rmtree(target)
    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(target)],
        check=True,
        capture_output=True,
        text=True,
    )
    return target


def count_lines(path: Path) -> int:
    """Cuenta líneas no vacías de un archivo. Tolerante a errores de codificación."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for line in f if line.strip())
    except (OSError, UnicodeDecodeError):
        return 0


def detect_languages(repo_path: Path) -> tuple[dict[str, float], int, int]:
    """Detecta lenguajes por LOC. Devuelve (% por lenguaje, total_files, total_loc)."""
    loc_per_lang: Counter[str] = Counter()
    total_files = 0

    for root, dirs, files in os.walk(repo_path):
        # filtrar directorios in-place
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        for fname in files:
            ext = Path(fname).suffix.lower()
            if ext in EXTENSION_MAP:
                lang = EXTENSION_MAP[ext]
                fpath = Path(root) / fname
                lines = count_lines(fpath)
                if lines > 0:
                    loc_per_lang[lang] += lines
                    total_files += 1

    total_loc = sum(loc_per_lang.values())
    if total_loc == 0:
        return {}, 0, 0

    pct = {lang: round(loc / total_loc * 100, 2) for lang, loc in loc_per_lang.items()}
    return pct, total_files, total_loc


def ingest(source: str, workdir: Path | None = None) -> tuple[RepoMeta, Path]:
    """Punto de entrada: detecta si es URL o path local y prepara el repo.

    Devuelve (RepoMeta, path al repo en disco).
    Si es remoto, clona en un temp dir que el caller debe limpiar.
    """
    source = source.strip()
    is_url = source.startswith(("http://", "https://", "git@"))
    is_gist = bool(parse_gist_url(source)) if is_url else False

    if is_url:
        if is_gist:
            owner_gist = parse_gist_url(source)
            owner, name = owner_gist  # gist_id como name
            clone_url = f"https://gist.github.com/{name}.git"
        else:
            owner_repo = parse_github_url(source)
            owner, name = owner_repo if owner_repo else (None, source.rstrip("/").split("/")[-1])
            clone_url = source
        tmpdir = Path(workdir or tempfile.mkdtemp(prefix="oss-audit-"))
        repo_path = clone_repo(clone_url, tmpdir)
    else:
        repo_path = Path(source).expanduser().resolve()
        if not repo_path.exists():
            raise FileNotFoundError(f"Path no existe: {repo_path}")
        owner, name = None, repo_path.name

    languages, total_files, total_loc = detect_languages(repo_path)
    primary = max(languages, key=languages.get) if languages else None

    if is_gist:
        repo_type, reason = "proposal", "URL de gist → artefacto-spec"
    else:
        # Sin métricas de GitHub aún; el caller (pipeline) puede reclasificar
        # cuando tenga stars/forks. Heurística inicial conservadora.
        repo_type, reason = classify_repo_type(repo_path, total_loc, has_remote_traction=False)

    meta = RepoMeta(
        source=source,
        is_remote=is_url,
        is_gist=is_gist,
        owner=owner,
        name=name,
        local_path=str(repo_path),
        languages=languages,
        primary_language=primary,
        total_files=total_files,
        total_loc=total_loc,
        repo_type=repo_type,
        repo_type_reason=reason,
    )
    return meta, repo_path
