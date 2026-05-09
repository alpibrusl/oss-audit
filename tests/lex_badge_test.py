"""Cross-check Python's badge outputs against the lex pilot.

Skipped silently if `lex` isn't on $PATH. Exercises the
shields.io URL, endpoint payload color/message, and markdown
snippet across all 5 grades + a few label/score shapes.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rubric.lex_cross_check import compare_badge, lex_badge  # noqa: E402
from rubric.models import AuditReport, RepoMeta  # noqa: E402
from rubric.reporter.badge import (  # noqa: E402
    GRADE_COLOR, to_markdown, to_shields_url,
)


def py_outputs(score: float, grade: str, label: str, link: str) -> dict:
    r = AuditReport(repo=RepoMeta(
        source=link, is_remote=True, name="bar", local_path="/tmp",
    ))
    r.overall_score = score
    r.grade = grade
    return {
        "url": to_shields_url(r, label),
        "message": f"{score:.1f}/100 {grade}",
        "color": GRADE_COLOR.get(grade, "lightgrey"),
        "markdown": to_markdown(r, link, label),
    }


CASES: list[tuple[float, str, str, str]] = [
    (92.5, "gold",     "rubric",   "https://github.com/foo/bar"),
    (65.0, "silver",   "rubric",   "https://github.com/foo/bar"),
    (40.0, "bronze",   "rubric",   "https://github.com/foo/bar"),
    (100.0, "platinum", "rubric",  "https://github.com/foo/bar"),
    (0.0, "fail",      "rubric",   "https://github.com/foo/bar"),
    # Label with a space (exercises the ' ' → '_' substitution)
    (78.2, "gold",     "my audit", "https://github.com/foo/bar"),
    # Unknown grade falls back to lightgrey
    (50.0, "indeterminate", "rubric", "https://github.com/foo/bar"),
]


def main() -> int:
    if shutil.which("lex") is None:
        print("[lex-badge] lex binary not on PATH — skipping")
        return 0
    failures: list[str] = []
    for score, grade, label, link in CASES:
        py = py_outputs(score, grade, label, link)
        lex_result = lex_badge(score, grade, label, link)
        if lex_result is None:
            failures.append(f"[{grade}] lex returned None")
            continue
        diffs = compare_badge(
            py["url"], py["message"], py["color"], py["markdown"],
            lex_result,
        )
        if diffs:
            failures.append(f"[{grade} {score} '{label}'] {diffs}")
        else:
            print(f"  OK   {grade:14} {score:5}  {label!r}")
    if failures:
        print("\n[lex-badge] FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n[lex-badge] All cases agree ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
