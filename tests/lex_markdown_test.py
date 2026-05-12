"""Cross-check Python's markdown scaffold against the lex pilot.

The lex side ports only the "above-the-fold" scaffold (title + meta
+ verdict block). We extract the same scaffold from Python's full
render and compare byte-for-byte.

Skipped silently if `lex` isn't on $PATH. NOT on the audit hot path —
markdown is presentation, not calibration; we don't double-render
every audit just for a cosmetic check.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rubric.lex_cross_check import LEX_BINARY, LEX_POC_ROOT  # noqa: E402
from rubric.models import (  # noqa: E402
    AuditReport, BusinessReport, CommunityReport, RepoMeta,
    TechnicalReport, VerdictPayload,
)
from rubric.reporter.markdown import render_markdown  # noqa: E402

MD_PATH = LEX_POC_ROOT / "markdown_scaffold.lex"


def lex_render(md_input: dict) -> str | None:
    """Call lex's `cross_check_markdown` and return the rendered scaffold."""
    try:
        result = subprocess.run(
            [
                LEX_BINARY, "run", str(MD_PATH),
                "cross_check_markdown", json.dumps(md_input),
            ],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return parsed.get("rendered")


def py_scaffold(report: AuditReport) -> str:
    """Extract Python's scaffold portion: everything before the first
    `## `-heading that isn't the Verdict one. Lex emits a trailing
    blank after the verdict block (matching Python's
    `lines.append("")`), so we keep trailing blanks here.
    """
    full = render_markdown(report)
    lines = full.split("\n")
    out: list[str] = []
    saw_verdict = False
    for line in lines:
        if line.startswith("## "):
            if "⚖️ Verdict" in line:
                saw_verdict = True
                out.append(line)
                continue
            if saw_verdict:
                break
        out.append(line)
    return "\n".join(out)


def make_report(
    *, lens: str = "general", with_actions: bool = True,
    with_one_liner: bool = True,
) -> tuple[AuditReport, dict]:
    """Build a deterministic AuditReport + matching lex MdInput dict."""
    r = AuditReport(repo=RepoMeta(
        source="https://github.com/foo/bar",
        is_remote=True, owner="foo", name="bar", local_path="/tmp/bar",
    ))
    r.audited_at = datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
    r.overall_score = 84.0
    r.grade = "bronze"
    r.lens = lens
    r.technical = TechnicalReport(score=84.0, data_status="available")
    r.business = BusinessReport(score=0.0, data_status="skipped")
    r.community = CommunityReport(score=0.0, data_status="skipped")
    r.verdict = VerdictPayload(
        code="worth-helping",
        label="Worth helping along",
        one_liner=("Solid technical core, weak market signal — coachable." if with_one_liner else ""),
        idea_band="medium",
        execution_band="high",
        relevance_band="medium",
        actions=(
            {"developer": "Try it out and file feedback.",
             "cto": "Pilot in a side project.",
             "investor": "Watch for traction milestones."}
            if with_actions else {}
        ),
    )

    audited_str = r.audited_at.strftime("%Y-%m-%d %H:%M UTC")
    from rubric.reporter.lens import LENSES
    L = LENSES[lens]
    md_input = {
        "repo_name":      r.repo.name or "",
        "repo_source":    r.repo.source,
        "audited_at":     audited_str,
        "overall_score":  float(r.overall_score),
        "grade":          r.grade,
        "lens_name":      L.name,
        "lens_label":     L.label,
        "lens_desc":      L.description,
        "verdict_code":   r.verdict.code,
        "verdict_label":  r.verdict.label,
        "verdict_one":    r.verdict.one_liner,
        "idea_band":      r.verdict.idea_band,
        "execution_band": r.verdict.execution_band,
        "relevance_band": r.verdict.relevance_band,
        "action_dev":     r.verdict.actions.get("developer", "") or "",
        "action_cto":     r.verdict.actions.get("cto", "") or "",
        "action_inv":     r.verdict.actions.get("investor", "") or "",
    }
    return r, md_input


CASES = [
    ("general lens, full actions + one-liner",
     dict(lens="general", with_actions=True, with_one_liner=True)),
    ("security lens, full actions + one-liner",
     dict(lens="security", with_actions=True, with_one_liner=True)),
    ("general lens, no actions",
     dict(lens="general", with_actions=False, with_one_liner=True)),
    ("general lens, no one-liner",
     dict(lens="general", with_actions=True, with_one_liner=False)),
]


def main() -> int:
    if shutil.which("lex") is None:
        print("[lex-markdown] lex binary not on PATH — skipping")
        return 0
    failures: list[str] = []
    for label, kwargs in CASES:
        report, md_input = make_report(**kwargs)
        py = py_scaffold(report)
        lex_out = lex_render(md_input)
        if lex_out is None:
            failures.append(f"[{label}] lex returned None")
            continue
        if py != lex_out:
            failures.append(f"[{label}] DIFF\n--- python ---\n{py}\n--- lex ---\n{lex_out}\n--- end ---")
        else:
            print(f"  OK   {label}")
    if failures:
        print("\n[lex-markdown] FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n[lex-markdown] All cases agree byte-for-byte ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
