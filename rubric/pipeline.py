"""End-to-end orchestrator: ingestion -> 3 pillars -> final report."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from .business.analyzer import analyze_business
from .business.context_builder import build_business_context
from .community.github_metrics import audit_community
from .community.internal_metrics import audit_community_internal
from .ingestion import ingest
from .models import AuditReport, VerdictPayload
from .reporter.lens import LENSES, apply_lens_guard, get_lens
from .reporter.scorer import compute_overall, top_recommendations
from .reporter.verdict import compute_counterfactuals, compute_verdict
from .technical.runner import audit_technical


def run_audit(source: str, skip_business: bool = False,
              skip_community: bool = False, skip_technical: bool = False,
              perspective: str | None = None, mode: str = "public",
              progress=None) -> AuditReport:
    """Full pipeline. Returns an AuditReport.

    `progress` can be a callable(label: str) for progress reporting.
    """
    def step(label: str):
        if progress:
            progress(label)

    step("📥 Ingesting repo...")
    workdir = Path(tempfile.mkdtemp(prefix="rubric-"))
    cleanup_needed = False
    try:
        meta, repo_path = ingest(source, workdir=workdir, deep_clone=(mode == "private"))
        cleanup_needed = meta.is_remote

        report = AuditReport(repo=meta)

        is_proposal = meta.repo_type == "proposal"
        if is_proposal:
            step(f"📜 Detected type: proposal — {meta.repo_type_reason}")

        if not skip_technical and not is_proposal:
            step(f"🔧 Technical analysis ({meta.primary_language or 'multi-lang'})...")
            report.technical = audit_technical(meta, repo_path)
            report.technical.data_status = (
                "available" if report.technical.score > 0 else "unavailable"
            )
        else:
            report.technical.data_status = "skipped"
            if is_proposal:
                step("🔧 Technical pillar skipped for `proposal` (not the artifact).")

        if not skip_business:
            step("💼 Building business context...")
            ctx = build_business_context(meta, repo_path)
            step(f"💼 Business analysis with Claude ({ctx.get('_token_estimate', 0):,} tokens)...")
            report.business = analyze_business(ctx)
            report.business.data_status = (
                "available" if report.business.score > 0 else "unavailable"
            )
            # Surface the backend-failure case at the top of the run.
            # analyze_business() catches exceptions and stuffs the
            # message into BusinessReport.summary; we re-emit it so
            # the user sees it without inspecting the JSON.
            if (
                report.business.data_status == "unavailable"
                and report.business.summary.startswith("Error calling backend")
            ):
                step("⚠️  business pillar failed: " + report.business.summary[:120])
        else:
            report.business.data_status = "skipped"

        if not skip_community:
            if mode == "private":
                step("👥 Team-health metrics (local git log + process docs)...")
                report.community = audit_community_internal(meta, repo_path)
            else:
                step("👥 Community metrics (GitHub API + agent-readiness)...")
                report.community = audit_community(meta, repo_path)
            report.community.data_status = (
                "available" if report.community.score > 0 else "unavailable"
            )
            # Surface the rate-limit case visibly. The community pillar
            # already attaches a `medium`-severity finding when 403 is
            # hit; re-emit at the top so users don't have to dig.
            for f in report.community.findings:
                if f.title.startswith("GitHub API rate-limited"):
                    step("⚠️  " + f.title + " — " + (f.recommendation or "set GITHUB_TOKEN"))
                    break
        else:
            report.community.data_status = "skipped"

        lens = get_lens(perspective)
        report.lens = lens.name
        report.mode = mode if mode in {"public", "private"} else "public"

        # First pass: BASE rubric (general lens, no guards). These values
        # are what the lex cross-check compares against — drift between
        # them is calibration signal, not lens artifacts.
        step("📊 Computing score and recommendations...")
        base_overall, base_grade = compute_overall(report, lens=LENSES["general"])
        report.overall_score = base_overall
        report.grade = base_grade
        report.top_recommendations = top_recommendations(report, lens=lens)
        if report.business.summary:
            report.executive_summary = report.business.summary

        step("⚖️  Verdict and counterfactuals...")
        base_verdict = compute_verdict(report)
        report.verdict = VerdictPayload(
            code=base_verdict.code, label=base_verdict.label, one_liner=base_verdict.one_liner,
            idea_band=base_verdict.idea_band, execution_band=base_verdict.execution_band,
            relevance_band=base_verdict.relevance_band, actions=base_verdict.actions,
        )
        report.counterfactuals = compute_counterfactuals(report)
        if report.business.mind_changers:
            report.counterfactuals.extend(
                f"[evidence] {m}" for m in report.business.mind_changers
            )

        # Optional cross-check: run the rubric AND the universal detectors
        # through the lex POC implementation. Compares against BASE values
        # (before lens), so disagreements are real drift, not lens
        # artifacts.
        if os.environ.get("RUBRIC_LEX_CROSS_CHECK") == "1":
            from .lex_cross_check import (
                compare, compare_community_score, compare_ingest,
                compare_ingest_io, compare_tech_score, compare_universal,
                lex_community_score, lex_ingest, lex_ingest_io,
                lex_tech_score, lex_universal, lex_verdict,
            )
            lex_r = lex_verdict(report)
            if lex_r is not None:
                diffs = compare(report, lex_r)
                if diffs:
                    step("⚠️  lex/python rubric disagree: " + "; ".join(diffs))
                else:
                    step("✓ lex cross-check (rubric): agree")
            # Pure-ingestion cross-check — URL parsing only. Cheap
            # subprocess (no fs / no proc effects), exercises the
            # GitHub + gist regex paths against the same source the
            # Python ingest just resolved.
            lex_i = lex_ingest(meta.source, meta.total_loc, 0, False)
            if lex_i is not None:
                idiffs = compare_ingest(meta.source, lex_i)
                if idiffs:
                    step("⚠️  lex/python ingest disagree: " + "; ".join(idiffs))
                else:
                    step("✓ lex cross-check (ingest): agree")
            # I/O ingestion cross-check — language detection +
            # doc-chars + classify decision. Walks the same tree
            # Python just walked; expensive enough that we only do
            # it when the cross-check env var is set.
            lex_iio = lex_ingest_io(repo_path, has_traction=False)
            if lex_iio is not None:
                iiodiffs = compare_ingest_io(
                    py_total_files=meta.total_files,
                    py_total_loc=meta.total_loc,
                    py_per_lang=meta.languages,
                    py_repo_type=meta.repo_type,
                    lex_result=lex_iio,
                )
                if iiodiffs:
                    step("⚠️  lex/python ingest-io disagree: " + "; ".join(iiodiffs))
                else:
                    step("✓ lex cross-check (ingest-io): agree")
            # Technical-score cross-check — pure scoring algorithm
            # over the signals runner.py just computed. Catches
            # threshold / weight drift between the two scorers.
            if not skip_technical and not is_proposal:
                signals = report.technical.raw.get("signals")
                if signals is not None:
                    lex_ts = lex_tech_score(signals)
                    if lex_ts is not None:
                        tsdiffs = compare_tech_score(report.technical.score, lex_ts)
                        if tsdiffs:
                            step("⚠️  lex/python tech-score disagree: " + "; ".join(tsdiffs))
                        else:
                            step("✓ lex cross-check (tech-score): agree")
            # Community-score cross-check — same pattern as tech.
            # Skipped silently when the API failed (no `signals`
            # stashed) or when the pillar was skipped entirely.
            if not skip_community:
                comm_signals = report.community.raw.get("signals")
                comm_mode    = report.community.raw.get("mode")
                if comm_signals is not None and comm_mode in {"public", "private"}:
                    lex_cs = lex_community_score(comm_signals, comm_mode)
                    if lex_cs is not None:
                        csdiffs = compare_community_score(report.community.score, lex_cs)
                        if csdiffs:
                            step("⚠️  lex/python community-score disagree: " + "; ".join(csdiffs))
                        else:
                            step(f"✓ lex cross-check (community-score, {comm_mode}): agree")
            # Universal detectors pilot — license + SECURITY.md (cross-check),
            # plus manifest_license + ci_security_tools (lex-only signals
            # absorbed into the technical pillar's findings).
            if not skip_technical and not is_proposal:
                lex_u = lex_universal(repo_path)
                if lex_u is not None:
                    universal_raw = report.technical.raw.get("universal", {})
                    py_lic = universal_raw.get("license")
                    py_secmd = bool(universal_raw.get("has_security_policy"))
                    udiffs = compare_universal(py_lic, py_secmd, lex_u)
                    if udiffs:
                        step("⚠️  lex/python universal disagree: " + "; ".join(udiffs))
                    else:
                        step("✓ lex cross-check (universal): agree")
                    # Lex-only signals — Python doesn't compute these yet,
                    # so they're additive findings rather than cross-check
                    # diffs. Stash on technical.raw for transparency and
                    # surface as findings.
                    from .models import Finding
                    manifest_lic = lex_u.get("manifest_license", "None")
                    ci_tools = lex_u.get("ci_security_tools", [])
                    report.technical.raw.setdefault("lex_signals", {})[
                        "manifest_license"
                    ] = manifest_lic
                    report.technical.raw["lex_signals"]["ci_security_tools"] = ci_tools

                    # Manifest-license vs LICENSE-file disagreement is a
                    # real legal/process bug (saying "MIT" in Cargo.toml
                    # while the LICENSE file is Apache, or vice versa).
                    if manifest_lic != "None" and py_lic and py_lic != "Unknown":
                        if manifest_lic != py_lic:
                            report.technical.findings.append(Finding(
                                severity="medium", category="legal",
                                title="Manifest license disagrees with LICENSE file",
                                detail=(
                                    f"LICENSE file classified as `{py_lic}`; "
                                    f"manifest declares `{manifest_lic}`. "
                                    "These should match."
                                ),
                                recommendation="Reconcile the manifest's license field with the LICENSE file.",
                            ))
                    # No security tools detected in CI is a `low` finding —
                    # not always wrong (small projects don't need cargo
                    # audit in CI), but worth flagging.
                    if not ci_tools:
                        report.technical.findings.append(Finding(
                            severity="low", category="security",
                            title="No security tools detected in CI workflows",
                            detail=(
                                "Workflows under `.github/workflows/` don't "
                                "mention any of: cargo audit, pip-audit, "
                                "npm audit, govulncheck, gitleaks, trivy, "
                                "snyk, codeql, bandit, semgrep, dependabot."
                            ),
                            recommendation="Add a dependency / secret scan to CI.",
                        ))

        # Second pass: apply the user's chosen lens.
        if lens.name != "general":
            step(f"🔍 Applying perspective: {lens.name} ({lens.label})...")
            lens_overall, lens_grade = compute_overall(report, lens=lens)
            report.overall_score = lens_overall
            report.grade = lens_grade
            guarded = apply_lens_guard(base_verdict, report, lens)
            report.verdict = VerdictPayload(
                code=guarded.code, label=guarded.label, one_liner=guarded.one_liner,
                idea_band=guarded.idea_band, execution_band=guarded.execution_band,
                relevance_band=guarded.relevance_band, actions=guarded.actions,
            )

        return report
    finally:
        if cleanup_needed and workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)
