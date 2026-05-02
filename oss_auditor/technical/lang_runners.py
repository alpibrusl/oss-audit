"""Runners por lenguaje. Cada uno devuelve un dict normalizado.

Filosofía: si la herramienta no está instalada, devolvemos {"available": False}
en lugar de fallar. El score global penaliza la ausencia de señales pero
no rompe la auditoría completa.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 180) -> tuple[int, str, str]:
    """Ejecuta un comando y devuelve (returncode, stdout, stderr) con timeout."""
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -2, "", "command not found"


def has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


# ---------- Rust ----------

def run_rust(repo_path: Path) -> dict[str, Any]:
    """Análisis para proyectos Rust. Detecta Cargo.toml en raíz o workspace."""
    out: dict[str, Any] = {"language": "Rust", "tools": {}}
    if not (repo_path / "Cargo.toml").exists():
        out["skipped"] = "no Cargo.toml found"
        return out

    # cargo audit — vulnerabilidades en dependencias
    if has("cargo") and has("cargo-audit"):
        rc, stdout, stderr = _run(["cargo", "audit", "--json"], cwd=repo_path, timeout=120)
        try:
            data = json.loads(stdout) if stdout else {}
            vulns = data.get("vulnerabilities", {}).get("list", [])
            out["tools"]["cargo-audit"] = {
                "available": True,
                "vulnerabilities": len(vulns),
                "details": [{"package": v.get("package", {}).get("name"),
                             "advisory": v.get("advisory", {}).get("id"),
                             "title": v.get("advisory", {}).get("title")}
                            for v in vulns[:10]],
            }
        except json.JSONDecodeError:
            out["tools"]["cargo-audit"] = {"available": True, "error": "could not parse output",
                                           "raw_excerpt": stdout[:500]}
    else:
        out["tools"]["cargo-audit"] = {"available": False, "hint": "cargo install cargo-audit"}

    # cargo clippy — lints
    if has("cargo"):
        rc, stdout, stderr = _run(
            ["cargo", "clippy", "--workspace", "--all-targets", "--message-format=json",
             "--", "-W", "clippy::all"],
            cwd=repo_path, timeout=300,
        )
        warnings = 0
        errors = 0
        for line in stdout.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                if msg.get("reason") == "compiler-message":
                    level = msg.get("message", {}).get("level")
                    if level == "warning":
                        warnings += 1
                    elif level == "error":
                        errors += 1
            except json.JSONDecodeError:
                continue
        out["tools"]["clippy"] = {
            "available": True,
            "warnings": warnings,
            "errors": errors,
            "exit_code": rc,
        }
    else:
        out["tools"]["clippy"] = {"available": False}

    return out


# ---------- Python ----------

def run_python(repo_path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"language": "Python", "tools": {}}
    pyproject = repo_path / "pyproject.toml"
    requirements = repo_path / "requirements.txt"
    if not (pyproject.exists() or requirements.exists() or any(repo_path.glob("**/*.py"))):
        out["skipped"] = "no Python project markers"
        return out

    # ruff — lint rápido y comprehensivo
    if has("ruff"):
        rc, stdout, stderr = _run(["ruff", "check", str(repo_path), "--output-format=json"], timeout=120)
        try:
            issues = json.loads(stdout) if stdout.strip() else []
            out["tools"]["ruff"] = {
                "available": True,
                "issues": len(issues),
                "by_code": _count_by(issues, "code"),
            }
        except json.JSONDecodeError:
            out["tools"]["ruff"] = {"available": True, "error": "parse_failed"}
    else:
        out["tools"]["ruff"] = {"available": False, "hint": "pip install ruff"}

    # pip-audit — vulnerabilidades de deps
    if has("pip-audit") and (pyproject.exists() or requirements.exists()):
        args = ["pip-audit", "--format", "json"]
        if requirements.exists():
            args += ["-r", str(requirements)]
        rc, stdout, _ = _run(args, cwd=repo_path, timeout=180)
        try:
            data = json.loads(stdout) if stdout else {}
            deps = data.get("dependencies", []) if isinstance(data, dict) else data
            vuln_count = sum(len(d.get("vulns", [])) for d in deps if isinstance(d, dict))
            out["tools"]["pip-audit"] = {"available": True, "vulnerabilities": vuln_count}
        except json.JSONDecodeError:
            out["tools"]["pip-audit"] = {"available": True, "error": "parse_failed"}
    else:
        out["tools"]["pip-audit"] = {"available": False, "hint": "pip install pip-audit"}

    return out


# ---------- JavaScript / TypeScript ----------

def run_js(repo_path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"language": "JavaScript/TypeScript", "tools": {}}
    pkg = repo_path / "package.json"
    if not pkg.exists():
        out["skipped"] = "no package.json"
        return out

    if has("npm"):
        rc, stdout, _ = _run(["npm", "audit", "--json"], cwd=repo_path, timeout=120)
        try:
            data = json.loads(stdout) if stdout else {}
            metadata = data.get("metadata", {}).get("vulnerabilities", {})
            total = sum(metadata.get(k, 0) for k in ("critical", "high", "moderate", "low"))
            out["tools"]["npm-audit"] = {
                "available": True,
                "vulnerabilities": total,
                "by_severity": metadata,
            }
        except json.JSONDecodeError:
            out["tools"]["npm-audit"] = {"available": True, "error": "parse_failed"}
    else:
        out["tools"]["npm-audit"] = {"available": False}

    return out


# ---------- Go ----------

def run_go(repo_path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"language": "Go", "tools": {}}
    if not (repo_path / "go.mod").exists():
        out["skipped"] = "no go.mod"
        return out

    if has("govulncheck"):
        rc, stdout, _ = _run(["govulncheck", "-json", "./..."], cwd=repo_path, timeout=180)
        # govulncheck emite JSONL
        vuln_count = 0
        for line in stdout.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                if "finding" in msg:
                    vuln_count += 1
            except json.JSONDecodeError:
                continue
        out["tools"]["govulncheck"] = {"available": True, "vulnerabilities": vuln_count}
    else:
        out["tools"]["govulncheck"] = {"available": False}

    if has("go"):
        rc, _, _ = _run(["go", "vet", "./..."], cwd=repo_path, timeout=120)
        out["tools"]["go-vet"] = {"available": True, "passed": rc == 0}
    return out


def _count_by(items: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for it in items:
        k = it.get(key, "unknown") if isinstance(it, dict) else "unknown"
        counts[k] = counts.get(k, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1])[:10])


# ---------- Dispatcher ----------

LANG_RUNNERS = {
    "Rust": run_rust,
    "Python": run_python,
    "JavaScript": run_js,
    "TypeScript": run_js,
    "Go": run_go,
}


def run_for_languages(repo_path: Path, languages: dict[str, float]) -> dict[str, Any]:
    """Ejecuta runners para cada lenguaje presente con >5% de LOC."""
    results: dict[str, Any] = {}
    seen_runners: set[Any] = set()
    for lang, pct in languages.items():
        if pct < 5.0:
            continue
        runner = LANG_RUNNERS.get(lang)
        if runner is None or runner in seen_runners:
            continue
        seen_runners.add(runner)
        try:
            results[lang] = runner(repo_path)
        except Exception as e:  # noqa: BLE001 - never break the pipeline
            results[lang] = {"language": lang, "error": str(e)}
    return results
