"""End-to-end orchestrator: ingestion -> 3 pillars -> final report."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .business.analyzer import analyze_business
from .business.context_builder import build_business_context
from .community.github_metrics import audit_community
from .ingestion import ingest
from .models import AuditReport, VerdictPayload
from .reporter.scorer import compute_overall, top_recommendations
from .reporter.verdict import compute_counterfactuals, compute_verdict
from .technical.runner import audit_technical


def run_audit(source: str, skip_business: bool = False,
              skip_community: bool = False, skip_technical: bool = False,
              progress=None) -> AuditReport:
    """Full pipeline. Returns an AuditReport.

    `progress` can be a callable(label: str) for progress reporting.
    """
    def step(label: str):
        if progress:
            progress(label)

    step("📥 Ingesting repo...")
    workdir = Path(tempfile.mkdtemp(prefix="oss-audit-"))
    cleanup_needed = False
    try:
        meta, repo_path = ingest(source, workdir=workdir)
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
        else:
            report.business.data_status = "skipped"

        if not skip_community:
            step("👥 Community metrics (GitHub API + agent-readiness)...")
            report.community = audit_community(meta, repo_path)
            report.community.data_status = (
                "available" if report.community.score > 0 else "unavailable"
            )
        else:
            report.community.data_status = "skipped"

        step("📊 Computing score and recommendations...")
        overall, grade = compute_overall(report)
        report.overall_score = overall
        report.grade = grade
        report.top_recommendations = top_recommendations(report)
        if report.business.summary:
            report.executive_summary = report.business.summary

        step("⚖️  Verdict and counterfactuals...")
        v = compute_verdict(report)
        report.verdict = VerdictPayload(
            code=v.code, label=v.label, one_liner=v.one_liner,
            idea_band=v.idea_band, execution_band=v.execution_band,
            relevance_band=v.relevance_band, actions=v.actions,
        )
        # Combine programmatic counterfactuals + LLM (mind_changers)
        report.counterfactuals = compute_counterfactuals(report)
        if report.business.mind_changers:
            report.counterfactuals.extend(
                f"[evidence] {m}" for m in report.business.mind_changers
            )

        return report
    finally:
        if cleanup_needed and workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)
