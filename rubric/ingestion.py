"""Repo ingestion: clone from URL or use local path, detect languages."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from .models import RepoMeta

# Extension -> language map (subset relevant to the technical analysis)
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
    """Extract (owner, repo) from a GitHub URL. Returns None if not GitHub."""
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
    """Extract (owner, gist_id) from a gist URL. Returns None if not a gist."""
    m = re.search(r"gist\.github\.com[:/]([^/]+)/([0-9a-f]+)", url.strip())
    if m:
        return m.group(1), m.group(2)
    return None


def classify_repo_type(
    repo_path: Path, total_loc: int, has_remote_traction: bool = False
) -> tuple[str, str]:
    """Decide whether the artifact is `implementation` or `proposal`.

    Heuristic:
    - Gist (the caller decides via is_gist) -> always `proposal`.
    - LOC < 500 + (README + docs) > 5K chars + some traction signal
      (caller passes has_remote_traction) -> `proposal`.
    - Else -> `implementation`.

    Returns (type, human-readable reason).
    """
    if total_loc >= 500:
        return "implementation", f"{total_loc} LOC indicates a code artifact"

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
            f"{total_loc} LOC + {doc_chars:,} chars of docs suggest a spec artifact",
        )
    return "implementation", "code present, doesn't look like a pure spec"


def clone_repo(url: str, dest: Path, depth: int | None = 1) -> Path:
    """Clone a repo into dest. Returns the directory path.

    `depth=1` is the default (shallow clone — fast). Pass `depth=None`
    for a full clone, or a larger int for a partial-but-deeper clone.
    Private-mode audits need historical commits for the git-log-based
    community pillar; pipeline.py passes `depth=500` in that case.
    """
    target = dest / "repo"
    if target.exists():
        shutil.rmtree(target)
    args = ["git", "clone"]
    if depth is not None:
        args += ["--depth", str(depth)]
    args += [url, str(target)]
    subprocess.run(args, check=True, capture_output=True, text=True)
    return target


def count_lines(path: Path) -> int:
    """Count non-empty lines of a file. Tolerant of encoding errors."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for line in f if line.strip())
    except (OSError, UnicodeDecodeError):
        return 0


def detect_languages(repo_path: Path) -> tuple[dict[str, float], int, int]:
    """Detect languages by LOC. Returns (% per language, total_files, total_loc)."""
    loc_per_lang: Counter[str] = Counter()
    total_files = 0

    for root, dirs, files in os.walk(repo_path):
        # filter directories in-place
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


def ingest(
    source: str, workdir: Path | None = None, deep_clone: bool = False,
) -> tuple[RepoMeta, Path]:
    """Entry point: detect URL vs local path and prepare the repo.

    Returns (RepoMeta, on-disk path to the repo).
    For a remote source, clones into a temp dir that the caller must clean up.
    `deep_clone=True` requests enough git history for git-log-based
    analysis (private-mode community pillar). Default shallow clone is
    plenty for everything else.
    """
    source = source.strip()
    is_url = source.startswith(("http://", "https://", "git@"))
    is_gist = bool(parse_gist_url(source)) if is_url else False

    if is_url:
        if is_gist:
            owner_gist = parse_gist_url(source)
            owner, name = owner_gist  # gist_id used as name
            clone_url = f"https://gist.github.com/{name}.git"
        else:
            owner_repo = parse_github_url(source)
            owner, name = owner_repo if owner_repo else (None, source.rstrip("/").split("/")[-1])
            clone_url = source
        tmpdir = Path(workdir or tempfile.mkdtemp(prefix="rubric-"))
        # Private-mode community signals come from git log; need history.
        clone_depth = 500 if deep_clone else 1
        repo_path = clone_repo(clone_url, tmpdir, depth=clone_depth)
    else:
        repo_path = Path(source).expanduser().resolve()
        if not repo_path.exists():
            raise FileNotFoundError(f"Path does not exist: {repo_path}")
        owner, name = None, repo_path.name

    languages, total_files, total_loc = detect_languages(repo_path)
    primary = max(languages, key=languages.get) if languages else None

    if is_gist:
        repo_type, reason = "proposal", "gist URL -> spec artifact"
    else:
        # No GitHub metrics yet; the caller (pipeline) can reclassify
        # once stars/forks are known. Conservative initial heuristic.
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
