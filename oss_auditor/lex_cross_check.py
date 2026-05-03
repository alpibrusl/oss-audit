"""Cross-check the Python verdict against the lex POC implementation.

Both implementations of the rubric should agree on every audit. A
disagreement surfaces ambiguity in the rubric itself — that's the
v0.6 calibration signal.

The lex implementation lives in `lex-poc/src/`. We invoke it via
`lex run lex-poc/src/adapter.lex cross_check <json>` when the
binary is on `$PATH`; otherwise we silently skip. Opt in by setting
`OSS_AUDITOR_LEX_CROSS_CHECK=1`.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .models import AuditReport

LEX_BINARY = "lex"
ADAPTER_PATH = Path(__file__).resolve().parent.parent / "lex-poc" / "src" / "adapter.lex"
TIMEOUT_SECONDS = 10


def _to_input(report: AuditReport) -> dict:
    """Pack an AuditReport into the flat primitives the lex adapter expects."""
    return {
        "repo_type":   report.repo.repo_type,
        "tech_status": report.technical.data_status,
        "tech_score":  float(report.technical.score),
        "biz_status":  report.business.data_status,
        "biz_score":   float(report.business.score),
        "biz_pc":      float(report.business.problem_clarity),
        "biz_di":      float(report.business.differentiation),
        "biz_ic":      float(report.business.intellectual_contribution),
        "biz_ms":      float(report.business.market_signals),
        "biz_eva":     float(report.business.execution_vs_ambition),
        "com_status":  report.community.data_status,
        "com_score":   float(report.community.score),
    }


def is_available() -> bool:
    """Return True if lex is installed and the adapter file is present."""
    return shutil.which(LEX_BINARY) is not None and ADAPTER_PATH.exists()


def lex_verdict(report: AuditReport) -> dict | None:
    """Return {'code', 'grade', 'score'} from the lex POC, or None on any failure."""
    if not is_available():
        return None
    payload = json.dumps(_to_input(report))
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
    raw = result.stdout.strip().strip('"')
    parts = raw.split("|")
    if len(parts) != 3:
        return None
    code, grade, score_s = parts
    try:
        score = float(score_s)
    except ValueError:
        return None
    return {"code": code, "grade": grade, "score": score}


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
