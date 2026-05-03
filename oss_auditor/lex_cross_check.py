"""Cross-check the Python pipeline against the lex POC implementation.

Two layers are checked:

1. **Rubric** (`lex_verdict` / `compare`): scoring + verdict from
   `lex-poc/src/adapter.lex::cross_check`. Disagreement surfaces
   ambiguity in the rubric itself — the v0.6 calibration signal.
2. **Universal detectors** (`lex_universal` / `compare_universal`):
   license classification and SECURITY.md presence from
   `lex-poc/src/universal.lex::cross_check_universal`. Validates the
   subprocess + JSON boundary for `[fs_walk, io]` code, not just
   pure rubric.

Both layers opt-in via `OSS_AUDITOR_LEX_CROSS_CHECK=1`. If the `lex`
binary isn't on `$PATH`, both silently no-op.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .models import AuditReport

LEX_BINARY = "lex"
LEX_POC_ROOT = Path(__file__).resolve().parent.parent / "lex-poc" / "src"
ADAPTER_PATH = LEX_POC_ROOT / "adapter.lex"
UNIVERSAL_PATH = LEX_POC_ROOT / "universal.lex"
TIMEOUT_SECONDS = 10


def _variant(name: str) -> dict:
    """Encode a unit variant per lex's CLI JSON convention (since #94)."""
    return {"$variant": name, "args": []}


_STATUS_VARIANTS = {
    "available":   _variant("Available"),
    "skipped":     _variant("Skipped"),
    "unavailable": _variant("Unavailable"),
}

_REPO_TYPE_VARIANTS = {
    "implementation": _variant("Implementation"),
    "proposal":       _variant("Proposal"),
}


def _report_to_lex_json(report: AuditReport) -> dict:
    """Build the Report record in the shape lex's compute_verdict expects."""
    return {
        "repo_type": _REPO_TYPE_VARIANTS[report.repo.repo_type],
        "technical": {
            "score":       float(report.technical.score),
            "data_status": _STATUS_VARIANTS[report.technical.data_status],
        },
        "business": {
            "score":                     float(report.business.score),
            "data_status":               _STATUS_VARIANTS[report.business.data_status],
            "problem_clarity":           float(report.business.problem_clarity),
            "differentiation":           float(report.business.differentiation),
            "intellectual_contribution": float(report.business.intellectual_contribution),
            "market_signals":            float(report.business.market_signals),
            "execution_vs_ambition":     float(report.business.execution_vs_ambition),
        },
        "community": {
            "score":       float(report.community.score),
            "data_status": _STATUS_VARIANTS[report.community.data_status],
        },
    }


def is_available() -> bool:
    """Return True if lex is installed and the adapter file is present."""
    return shutil.which(LEX_BINARY) is not None and ADAPTER_PATH.exists()


def lex_verdict(report: AuditReport) -> dict | None:
    """Return {'code', 'grade', 'score'} from the lex POC, or None on any failure."""
    if not is_available():
        return None
    payload = json.dumps(_report_to_lex_json(report))
    try:
        result = subprocess.run(
            [LEX_BINARY, "run", str(ADAPTER_PATH), "cross_check", payload],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or not {"code", "grade", "score"} <= parsed.keys():
        return None
    return {
        "code":  parsed["code"],
        "grade": parsed["grade"],
        "score": float(parsed["score"]),
    }


def compare(report: AuditReport, lex_result: dict) -> list[str]:
    """Return a list of human-readable disagreements between the two implementations."""
    diffs: list[str] = []
    if report.verdict.code != lex_result["code"]:
        diffs.append(
            f"verdict code: python={report.verdict.code!r} lex={lex_result['code']!r}"
        )
    if report.grade != lex_result["grade"]:
        diffs.append(f"grade: python={report.grade!r} lex={lex_result['grade']!r}")
    if abs(report.overall_score - lex_result["score"]) > 0.05:
        diffs.append(f"score: python={report.overall_score} lex={lex_result['score']}")
    return diffs


# ---------- universal-detector cross-check (pilot) ---------------

def lex_universal(repo_path: Path | str) -> dict | None:
    """Run lex's `cross_check_universal` over the repo. Returns
    {'license': str, 'has_security_md': bool} or None on any failure.
    """
    if shutil.which(LEX_BINARY) is None or not UNIVERSAL_PATH.exists():
        return None
    repo = str(Path(repo_path).resolve())
    try:
        result = subprocess.run(
            [
                LEX_BINARY, "run",
                "--allow-effects", "fs_walk,io",
                "--allow-fs-read", repo,
                str(UNIVERSAL_PATH), "cross_check_universal",
                json.dumps(repo),
            ],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or not {"license", "has_security_md"} <= parsed.keys():
        return None
    return {
        "license":         parsed["license"],
        "has_security_md": bool(parsed["has_security_md"]),
    }


def compare_universal(
    py_license: str | None, py_has_security_md: bool, lex_result: dict,
) -> list[str]:
    """Return human-readable disagreements between the Python detectors and lex.

    Notes:
    - Python returns `None` when no LICENSE file exists; lex returns `"None"`.
      Both paths normalize to the string `"None"` for comparison.
    """
    diffs: list[str] = []
    py_lic = py_license if py_license is not None else "None"
    if py_lic != lex_result["license"]:
        diffs.append(f"license: python={py_lic!r} lex={lex_result['license']!r}")
    if py_has_security_md != lex_result["has_security_md"]:
        diffs.append(
            f"has_security_md: python={py_has_security_md} lex={lex_result['has_security_md']}"
        )
    return diffs
