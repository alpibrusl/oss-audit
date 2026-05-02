"""Análisis técnico universal — independiente del lenguaje."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..models import Finding

# Patrones de secretos comunes (fallback si gitleaks no está instalado)
SECRET_PATTERNS = [
    (r"(?i)aws_secret_access_key\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?", "AWS Secret Key"),
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    (r"sk-[a-zA-Z0-9]{32,}", "OpenAI/Anthropic-style API key"),
    (r"sk-ant-[a-zA-Z0-9_\-]{40,}", "Anthropic API key"),
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token"),
    (r"gho_[a-zA-Z0-9]{36}", "GitHub OAuth Token"),
    (r"(?i)bearer\s+[a-z0-9_\-\.=]{30,}", "Bearer Token"),
    (r"(?i)private[_-]?key.*-----BEGIN", "Private Key"),
    (r"(?i)password\s*[:=]\s*['\"][^'\"]{8,}['\"]", "Hardcoded Password"),
]

SCAN_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".rs", ".go", ".java",
                   ".rb", ".php", ".cs", ".cpp", ".c", ".h", ".env", ".yml",
                   ".yaml", ".json", ".toml", ".sh", ".cfg", ".ini"}

IGNORE_DIRS = {".git", "node_modules", "target", "dist", "build",
               "__pycache__", ".venv", "venv", "vendor"}


def has_command(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def detect_ci(repo_path: Path) -> tuple[bool, list[str]]:
    """Detecta presencia de CI configurada."""
    ci_files = []
    if (repo_path / ".github" / "workflows").is_dir():
        wf = list((repo_path / ".github" / "workflows").glob("*.y*ml"))
        if wf:
            ci_files.extend([str(f.relative_to(repo_path)) for f in wf])
    for marker in [".gitlab-ci.yml", ".circleci/config.yml", ".travis.yml",
                   "azure-pipelines.yml", "Jenkinsfile"]:
        if (repo_path / marker).exists():
            ci_files.append(marker)
    return bool(ci_files), ci_files


def detect_tests(repo_path: Path) -> tuple[bool, int]:
    """Heurística para detectar tests: archivos/dirs con 'test' en el nombre."""
    test_files = 0
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        rel_root = Path(root).relative_to(repo_path)
        path_str = str(rel_root).lower()
        in_test_dir = any(p in path_str for p in ("test", "spec", "__tests__"))
        for f in files:
            fl = f.lower()
            if in_test_dir or fl.startswith("test_") or fl.endswith("_test.py") \
               or fl.endswith(".test.js") or fl.endswith(".spec.js") \
               or fl.endswith(".test.ts") or fl.endswith("_test.go") \
               or fl.endswith("_test.rs"):
                test_files += 1
    return test_files > 0, test_files


def scan_secrets(repo_path: Path) -> tuple[int, list[Finding]]:
    """Escanea secretos. Usa gitleaks si está disponible; si no, regex propio."""
    if has_command("gitleaks"):
        return _scan_secrets_gitleaks(repo_path)
    return _scan_secrets_regex(repo_path)


def _scan_secrets_gitleaks(repo_path: Path) -> tuple[int, list[Finding]]:
    try:
        result = subprocess.run(
            ["gitleaks", "detect", "--source", str(repo_path), "--report-format", "json",
             "--report-path", "/dev/stdout", "--no-banner", "--exit-code", "0"],
            capture_output=True, text=True, timeout=120,
        )
        # gitleaks emite JSONLines o un array según versión
        findings_raw = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line or line == "[]":
                continue
            try:
                if line.startswith("["):
                    findings_raw = json.loads(line)
                    break
                findings_raw.append(json.loads(line))
            except json.JSONDecodeError:
                pass

        findings = []
        for item in findings_raw[:50]:
            findings.append(Finding(
                severity="high",
                category="security",
                title=f"Secret detectado: {item.get('Description', item.get('RuleID', 'unknown'))}",
                detail=f"Tipo: {item.get('RuleID', 'n/a')}",
                location=f"{item.get('File', '?')}:{item.get('StartLine', '?')}",
                recommendation="Rotar inmediatamente y eliminar del historial git.",
            ))
        return len(findings_raw), findings
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        return _scan_secrets_regex(repo_path)


def _scan_secrets_regex(repo_path: Path) -> tuple[int, list[Finding]]:
    findings: list[Finding] = []
    count = 0
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for f in files:
            ext = Path(f).suffix.lower()
            if ext not in SCAN_EXTENSIONS and not f.startswith(".env"):
                continue
            fpath = Path(root) / f
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read(500_000)  # cap por archivo
            except OSError:
                continue
            for pattern, label in SECRET_PATTERNS:
                for m in re.finditer(pattern, content):
                    count += 1
                    if len(findings) < 20:
                        line_num = content[:m.start()].count("\n") + 1
                        findings.append(Finding(
                            severity="high",
                            category="security",
                            title=f"Posible secreto: {label}",
                            detail=f"Patrón coincidente en archivo.",
                            location=f"{fpath.relative_to(repo_path)}:{line_num}",
                            recommendation="Verificar y rotar si es real. Usar variables de entorno.",
                        ))
    return count, findings


def detect_security_md(repo_path: Path) -> bool:
    return any((repo_path / name).exists() for name in
               ["SECURITY.md", "security.md", ".github/SECURITY.md"])


def detect_license(repo_path: Path) -> str | None:
    for name in ["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"]:
        f = repo_path / name
        if f.exists():
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")[:500]
                # detección simple
                upper = content.upper()
                if "MIT LICENSE" in upper or "MIT " in upper[:200]:
                    return "MIT"
                if "APACHE LICENSE" in upper:
                    return "Apache-2.0"
                if "GPL" in upper:
                    return "GPL"
                if "EUPL" in upper:
                    return "EUPL-1.2"
                if "BSD" in upper:
                    return "BSD"
                return "Unknown"
            except OSError:
                pass
    return None


def universal_checks(repo_path: Path) -> dict[str, Any]:
    """Ejecuta todos los chequeos universales."""
    has_ci, ci_files = detect_ci(repo_path)
    has_tests, test_files = detect_tests(repo_path)
    secrets_count, secret_findings = scan_secrets(repo_path)
    has_security_policy = detect_security_md(repo_path)
    license_type = detect_license(repo_path)

    return {
        "has_ci": has_ci,
        "ci_files": ci_files,
        "has_tests": has_tests,
        "test_file_count": test_files,
        "secrets_count": secrets_count,
        "secret_findings": secret_findings,
        "has_security_policy": has_security_policy,
        "license": license_type,
    }
