"""Universal technical analysis — language-independent."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..models import Finding

# Common secret patterns (fallback when gitleaks isn't installed)
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
    """Detect whether CI is configured."""
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


def detect_tests(repo_path: Path) -> tuple[bool, int, int]:
    """Count test files and source-code files.

    Returns (has_tests, test_file_count, source_file_count).
    """
    test_files = 0
    source_files = 0
    code_exts = {".py", ".js", ".jsx", ".ts", ".tsx", ".rs", ".go",
                 ".java", ".kt", ".rb", ".php", ".cs", ".cpp", ".c", ".h",
                 ".swift"}
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        rel_root = Path(root).relative_to(repo_path)
        path_str = str(rel_root).lower()
        in_test_dir = any(p in path_str for p in ("test", "spec", "__tests__", "fuzz"))
        for f in files:
            fl = f.lower()
            ext = Path(f).suffix.lower()
            is_test = (in_test_dir or fl.startswith("test_")
                       or fl.endswith("_test.py") or fl.endswith(".test.js")
                       or fl.endswith(".spec.js") or fl.endswith(".test.ts")
                       or fl.endswith("_test.go") or fl.endswith("_test.rs"))
            if is_test:
                test_files += 1
            elif ext in code_exts:
                source_files += 1
    return test_files > 0, test_files, source_files


# Heuristics for detecting fuzz / property tests.
FUZZ_MARKERS = {
    "files_dirs": [
        ".github/workflows/fuzz.yml", ".github/workflows/fuzz.yaml",
        "fuzz/", "fuzz_targets/", ".fuzz/",
    ],
    "deps_substrings": [
        "cargo-fuzz", "afl", "libfuzzer", "honggfuzz", "atheris",
        "go-fuzz", "jazzer", "jqf-fuzz",
    ],
}

PROPERTY_MARKERS = {
    "deps_substrings": [
        "proptest", "quickcheck", "hypothesis", "fast-check",
        "scalacheck", "stream_data", "test.check",
    ],
}


def _read_manifests(repo_path: Path) -> str:
    """Concatenate manifest contents for a cheap grep."""
    blob = []
    for name in ("Cargo.toml", "Cargo.lock", "pyproject.toml",
                 "requirements.txt", "package.json", "package-lock.json",
                 "go.mod", "go.sum", "build.gradle", "pom.xml", "Gemfile"):
        p = repo_path / name
        if p.is_file():
            try:
                blob.append(p.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                pass
    return "\n".join(blob).lower()


def detect_fuzz_tests(repo_path: Path) -> bool:
    for entry in FUZZ_MARKERS["files_dirs"]:
        p = repo_path / entry.rstrip("/")
        if entry.endswith("/"):
            if p.is_dir():
                return True
        elif p.exists():
            return True
    blob = _read_manifests(repo_path)
    return any(s in blob for s in FUZZ_MARKERS["deps_substrings"])


def detect_property_tests(repo_path: Path) -> bool:
    blob = _read_manifests(repo_path)
    return any(s in blob for s in PROPERTY_MARKERS["deps_substrings"])


def scan_secrets(repo_path: Path) -> tuple[int, list[Finding]]:
    """Scan for secrets. Uses gitleaks if available, otherwise our own regex."""
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
        # gitleaks emits JSONLines or an array depending on version
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
                title=f"Secret detected: {item.get('Description', item.get('RuleID', 'unknown'))}",
                detail=f"Type: {item.get('RuleID', 'n/a')}",
                location=f"{item.get('File', '?')}:{item.get('StartLine', '?')}",
                recommendation="Rotate immediately and remove from the git history.",
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
                    content = fh.read(500_000)  # per-file cap
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
                            title=f"Possible secret: {label}",
                            detail="Pattern matched in the file.",
                            location=f"{fpath.relative_to(repo_path)}:{line_num}",
                            recommendation="Verify and rotate if it's real. Use environment variables.",
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
                # simple detection
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
    """Run all the universal checks."""
    has_ci, ci_files = detect_ci(repo_path)
    has_tests, test_files, source_files = detect_tests(repo_path)
    test_density = (test_files / source_files) if source_files else 0.0
    has_fuzz = detect_fuzz_tests(repo_path)
    has_property = detect_property_tests(repo_path)
    secrets_count, secret_findings = scan_secrets(repo_path)
    has_security_policy = detect_security_md(repo_path)
    license_type = detect_license(repo_path)

    return {
        "has_ci": has_ci,
        "ci_files": ci_files,
        "has_tests": has_tests,
        "test_file_count": test_files,
        "source_file_count": source_files,
        "test_density": round(test_density, 3),
        "has_fuzz_tests": has_fuzz,
        "has_property_tests": has_property,
        "secrets_count": secrets_count,
        "secret_findings": secret_findings,
        "has_security_policy": has_security_policy,
        "license": license_type,
    }
