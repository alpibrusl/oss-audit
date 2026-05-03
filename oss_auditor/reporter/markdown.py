"""Markdown report generator."""
from __future__ import annotations

from ..models import AuditReport
from .lens import category_priority, get_lens

GRADE_EMOJI = {
    "platinum": "💎",
    "gold": "🥇",
    "silver": "🥈",
    "bronze": "🥉",
    "fail": "❌",
}


def render_markdown(report: AuditReport) -> str:
    r = report
    grade_emoji = GRADE_EMOJI.get(r.grade, "")
    lens = get_lens(r.lens)

    severity_priority = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

    def finding_sort_key(f) -> tuple[int, int]:
        return (severity_priority.get(f.severity, 5), category_priority(f.category, lens))

    lines: list[str] = []
    lines.append(f"# Audit: {r.repo.name}")
    lines.append("")
    lines.append(f"**Source:** `{r.repo.source}`  ")
    lines.append(f"**Audited:** {r.audited_at.strftime('%Y-%m-%d %H:%M UTC')}  ")
    lines.append(f"**Overall score:** **{r.overall_score}/100** {grade_emoji} _{r.grade.upper()}_")
    if lens.name != "general":
        lines.append(f"**Perspective:** `{lens.name}` — {lens.label}. _{lens.description}_  ")
    lines.append("")

    # --- Verdict ---
    v = r.verdict
    if v.code and v.code != "pass":
        lines.append(f"## ⚖️ Verdict: `{v.code}` — {v.label}")
    else:
        lines.append(f"## ⚖️ Verdict: `{v.code}`")
    lines.append("")
    if v.one_liner:
        lines.append(f"> {v.one_liner}")
        lines.append("")
    lines.append(f"**Idea:** `{v.idea_band}` &middot; "
                 f"**Execution:** `{v.execution_band}` &middot; "
                 f"**Relevance:** `{v.relevance_band}`")
    lines.append("")
    if v.actions:
        lines.append("| Audience | Action |")
        lines.append("|----------|--------|")
        for who in ("developer", "cto", "investor"):
            if v.actions.get(who):
                lines.append(f"| {who.capitalize()} | {v.actions[who]} |")
        lines.append("")

    # --- Audience views (LLM, evidence-based) ---
    b_views = (r.business.developer_view, r.business.cto_view, r.business.investor_view)
    if any(b_views):
        lines.append("## 👁️ Audience views")
        lines.append("")
        if r.business.developer_view:
            lines.append(f"**Developer.** {r.business.developer_view}")
            lines.append("")
        if r.business.cto_view:
            lines.append(f"**CTO / VP-Eng.** {r.business.cto_view}")
            lines.append("")
        if r.business.investor_view:
            lines.append(f"**Investor.** {r.business.investor_view}")
            lines.append("")

    # --- Counterfactuals: what would change the verdict ---
    if r.counterfactuals:
        lines.append("## 🔁 What would change my mind")
        lines.append("")
        for cf in r.counterfactuals:
            lines.append(f"- {cf}")
        lines.append("")

    # --- Executive summary ---
    lines.append("## Executive summary")
    lines.append("")
    if r.executive_summary:
        lines.append(r.executive_summary)
    elif r.business.summary:
        lines.append(r.business.summary)
    else:
        lines.append("_(no summary)_")
    lines.append("")

    # --- Snapshot ---
    lines.append("## Snapshot")
    lines.append("")
    lines.append("| Pillar | Score | Weight |")
    lines.append("|--------|------:|-------:|")
    lines.append(f"| 🔧 Technical | {r.technical.score:.1f} | {lens.weights['technical']*100:.0f}% |")
    lines.append(f"| 💡 Thesis & innovation | {r.business.score:.1f} | {lens.weights['business']*100:.0f}% |")
    third_label = "👥 Team / process" if r.mode == "private" else "👥 Community"
    lines.append(f"| {third_label} | {r.community.score:.1f} | {lens.weights['community']*100:.0f}% |")
    lines.append("")

    # Languages
    if r.repo.languages:
        lines.append("**Detected stack:** " +
                     ", ".join(f"{lang} {pct:.0f}%" for lang, pct in
                               sorted(r.repo.languages.items(), key=lambda x: -x[1])[:5]))
        lines.append(f"**Total LOC:** {r.repo.total_loc:,} across {r.repo.total_files} files")
        lines.append("")

    # Artifact type
    if r.repo.repo_type == "proposal":
        lines.append(f"**Artifact type:** `proposal` — {r.repo.repo_type_reason}")
        lines.append("> In proposal mode the artifact is the spec/idea, not the code. "
                     "The technical pillar is skipped and the weight is redistributed.")
        lines.append("")

    # --- Top recommendations ---
    if r.top_recommendations:
        lines.append("## Top recommendations")
        lines.append("")
        for i, rec in enumerate(r.top_recommendations, 1):
            lines.append(f"{i}. {rec}")
        lines.append("")

    # --- Technical pillar ---
    lines.append("## 🔧 Technical pillar")
    lines.append("")
    t = r.technical
    lines.append(f"**Score:** {t.score:.1f}/100")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Tests detected | {'Yes' if t.has_tests else 'No'} |")
    lines.append(f"| Test density | {t.test_density:.2f} (test_files / source_files) |")
    lines.append(f"| Fuzz tests | {'Yes' if t.has_fuzz_tests else 'No'} |")
    lines.append(f"| Property tests | {'Yes' if t.has_property_tests else 'No'} |")
    lines.append(f"| CI configured | {'Yes' if t.has_ci else 'No'} |")
    lines.append(f"| Secrets found | {t.secrets_found} |")
    lines.append(f"| Dependency vulnerabilities | {t.vulnerabilities} |")
    lines.append(f"| Lint issues | {t.lint_issues} |")
    lines.append(f"| Composability | {t.composability_score}/10 |")
    lines.append("")
    if t.composability_surfaces:
        lines.append("**Detected composability surfaces:**")
        for s in t.composability_surfaces:
            lines.append(f"- {s}")
        lines.append("")
    if t.tools_run:
        lines.append("**Tools run:** " + ", ".join(t.tools_run))
        lines.append("")
    if t.findings:
        lines.append("### Technical findings")
        lines.append("")
        for f in sorted(t.findings, key=finding_sort_key)[:10]:
            loc = f" ({f.location})" if f.location else ""
            lines.append(f"- **[{f.severity}]** {f.title}{loc}")
            if f.detail:
                lines.append(f"  - {f.detail}")
            if f.recommendation:
                lines.append(f"  - 💡 _{f.recommendation}_")
        lines.append("")

    # --- Thesis & innovation pillar ---
    lines.append("## 💡 Thesis & innovation pillar")
    lines.append("")
    b = r.business
    lines.append(f"**Score:** {b.score:.1f}/100")
    if b.backend or b.model:
        lines.append(f"**LLM backend:** `{b.backend or 'n/a'}` &middot; **Model:** `{b.model or 'n/a'}`")
    lines.append("")
    if b.summary:
        lines.append(f"> {b.summary}")
        lines.append("")
    if b.novelty_summary:
        lines.append(f"**Novelty:** {b.novelty_summary}")
        lines.append("")
    if b.nearest_prior_art:
        lines.append("**Nearest prior art:**")
        for p in b.nearest_prior_art:
            lines.append(f"- {p}")
        lines.append("")

    lines.append("### Sub-scores")
    lines.append("")
    lines.append("| Dimension | Score |")
    lines.append("|-----------|------:|")
    lines.append(f"| Problem clarity | {b.problem_clarity:.0f} |")
    lines.append(f"| Execution vs ambition | {b.execution_vs_ambition:.0f} |")
    lines.append(f"| Differentiation | {b.differentiation:.0f} |")
    lines.append(f"| Market signals | {b.market_signals:.0f} |")
    lines.append(f"| Viability / risks | {b.viability_risks:.0f} |")
    lines.append(f"| Intellectual contribution | {b.intellectual_contribution:.0f} |")
    lines.append("")

    if b.strengths:
        lines.append("### Strengths")
        for s in b.strengths:
            lines.append(f"- {s}")
        lines.append("")
    if b.weaknesses:
        lines.append("### Weaknesses / risks")
        for w in b.weaknesses:
            lines.append(f"- {w}")
        lines.append("")
    if b.opportunities:
        lines.append("### Opportunities")
        for o in b.opportunities:
            lines.append(f"- {o}")
        lines.append("")

    # --- Community / Team-health pillar ---
    private = r.mode == "private"
    pillar_title = "👥 Team / process pillar" if private else "👥 Community pillar"
    lines.append(f"## {pillar_title}")
    lines.append("")
    c = r.community
    lines.append(f"**Score:** {c.score:.1f}/100")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    if not private:
        lines.append(f"| ⭐ Stars | {c.stars} |")
        lines.append(f"| 🍴 Forks | {c.forks} |")
        lines.append(f"| 🐛 Open issues | {c.open_issues} |")
    lines.append(f"| 👤 Contributors | {c.contributors} |")
    lines.append(f"| Bus factor (top 1) | {c.bus_factor_top1_pct:.1f}% |")
    lines.append(f"| Bus factor (top 3) | {c.bus_factor_top3_pct:.1f}% |")
    lines.append(f"| Commits in last 90d | {c.commits_last_90d} |")
    lines.append(f"| Commits / author (90d) | {c.commits_per_author_90d:.1f} |")
    if c.last_commit_days_ago is not None:
        lines.append(f"| Last commit | {c.last_commit_days_ago} days ago |")
    if c.avg_issue_close_days is not None:
        lines.append(f"| Avg issue close time | {c.avg_issue_close_days:.1f} days |")
    if not private:
        lines.append(f"| Has releases | {'Yes' if c.has_releases else 'No'} |")
    lines.append(f"| Agent-readiness | {c.agent_readiness_score}/10 |")
    if c.is_solo_active:
        lines.append("| Solo-owner | active (not abandoned) |")
    lines.append("")
    if c.agent_readiness_signals:
        lines.append("**Detected agent-ready signals:**")
        for s in c.agent_readiness_signals:
            lines.append(f"- {s}")
        lines.append("")
    if c.findings:
        lines.append("### Community findings")
        for f in sorted(c.findings, key=finding_sort_key):
            lines.append(f"- **[{f.severity}]** {f.title}")
            if f.recommendation:
                lines.append(f"  - 💡 _{f.recommendation}_")
        lines.append("")

    lines.append("---")
    lines.append("_Generated by OSS Auditor v0.6.0_")
    return "\n".join(lines)
