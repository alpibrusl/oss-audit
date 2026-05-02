"""Generador de reporte en markdown."""
from __future__ import annotations

from ..models import AuditReport

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

    lines: list[str] = []
    lines.append(f"# Auditoría: {r.repo.name}")
    lines.append("")
    lines.append(f"**Fuente:** `{r.repo.source}`  ")
    lines.append(f"**Auditado:** {r.audited_at.strftime('%Y-%m-%d %H:%M UTC')}  ")
    lines.append(f"**Score Global:** **{r.overall_score}/100** {grade_emoji} _{r.grade.upper()}_")
    lines.append("")

    # --- Resumen ejecutivo ---
    lines.append("## Resumen ejecutivo")
    lines.append("")
    if r.executive_summary:
        lines.append(r.executive_summary)
    elif r.business.summary:
        lines.append(r.business.summary)
    else:
        lines.append("_(sin resumen)_")
    lines.append("")

    # --- Snapshot ---
    lines.append("## Snapshot")
    lines.append("")
    lines.append("| Pilar | Score | Peso |")
    lines.append("|-------|------:|-----:|")
    lines.append(f"| 🔧 Técnico | {r.technical.score:.1f} | 40% |")
    lines.append(f"| 💼 Negocio | {r.business.score:.1f} | 35% |")
    lines.append(f"| 👥 Comunidad | {r.community.score:.1f} | 25% |")
    lines.append("")

    # Lenguajes
    if r.repo.languages:
        lines.append("**Stack detectado:** " +
                     ", ".join(f"{lang} {pct:.0f}%" for lang, pct in
                               sorted(r.repo.languages.items(), key=lambda x: -x[1])[:5]))
        lines.append(f"**LOC totales:** {r.repo.total_loc:,} en {r.repo.total_files} archivos")
        lines.append("")

    # --- Top recomendaciones ---
    if r.top_recommendations:
        lines.append("## Top recomendaciones")
        lines.append("")
        for i, rec in enumerate(r.top_recommendations, 1):
            lines.append(f"{i}. {rec}")
        lines.append("")

    # --- Pilar técnico ---
    lines.append("## 🔧 Pilar técnico")
    lines.append("")
    t = r.technical
    lines.append(f"**Score:** {t.score:.1f}/100")
    lines.append("")
    lines.append("| Métrica | Valor |")
    lines.append("|---------|-------|")
    lines.append(f"| Tests detectados | {'Sí' if t.has_tests else 'No'} |")
    lines.append(f"| CI configurado | {'Sí' if t.has_ci else 'No'} |")
    lines.append(f"| Secretos encontrados | {t.secrets_found} |")
    lines.append(f"| Vulnerabilidades en deps | {t.vulnerabilities} |")
    lines.append(f"| Lint issues | {t.lint_issues} |")
    lines.append("")
    if t.tools_run:
        lines.append("**Herramientas ejecutadas:** " + ", ".join(t.tools_run))
        lines.append("")
    if t.findings:
        lines.append("### Hallazgos técnicos")
        lines.append("")
        for f in t.findings[:10]:
            loc = f" ({f.location})" if f.location else ""
            lines.append(f"- **[{f.severity}]** {f.title}{loc}")
            if f.detail:
                lines.append(f"  - {f.detail}")
            if f.recommendation:
                lines.append(f"  - 💡 _{f.recommendation}_")
        lines.append("")

    # --- Pilar negocio ---
    lines.append("## 💼 Pilar de negocio")
    lines.append("")
    b = r.business
    lines.append(f"**Score:** {b.score:.1f}/100")
    lines.append("")
    if b.summary:
        lines.append(f"> {b.summary}")
        lines.append("")

    lines.append("### Sub-scores")
    lines.append("")
    lines.append("| Dimensión | Score |")
    lines.append("|-----------|------:|")
    lines.append(f"| Claridad del problema | {b.problem_clarity:.0f} |")
    lines.append(f"| Ejecución vs ambición | {b.execution_vs_ambition:.0f} |")
    lines.append(f"| Diferenciación | {b.differentiation:.0f} |")
    lines.append(f"| Señales de mercado | {b.market_signals:.0f} |")
    lines.append(f"| Viabilidad / riesgos | {b.viability_risks:.0f} |")
    lines.append("")

    if b.strengths:
        lines.append("### Fortalezas")
        for s in b.strengths:
            lines.append(f"- {s}")
        lines.append("")
    if b.weaknesses:
        lines.append("### Debilidades / riesgos")
        for w in b.weaknesses:
            lines.append(f"- {w}")
        lines.append("")
    if b.opportunities:
        lines.append("### Oportunidades")
        for o in b.opportunities:
            lines.append(f"- {o}")
        lines.append("")

    # --- Pilar comunidad ---
    lines.append("## 👥 Pilar de comunidad")
    lines.append("")
    c = r.community
    lines.append(f"**Score:** {c.score:.1f}/100")
    lines.append("")
    lines.append("| Métrica | Valor |")
    lines.append("|---------|-------|")
    lines.append(f"| ⭐ Stars | {c.stars} |")
    lines.append(f"| 🍴 Forks | {c.forks} |")
    lines.append(f"| 🐛 Issues abiertas | {c.open_issues} |")
    lines.append(f"| 👤 Contribuidores | {c.contributors} |")
    lines.append(f"| Bus factor (top 1) | {c.bus_factor_top1_pct:.1f}% |")
    lines.append(f"| Bus factor (top 3) | {c.bus_factor_top3_pct:.1f}% |")
    lines.append(f"| Commits últimos 90d | {c.commits_last_90d} |")
    if c.last_commit_days_ago is not None:
        lines.append(f"| Último commit | hace {c.last_commit_days_ago} días |")
    if c.avg_issue_close_days is not None:
        lines.append(f"| Tiempo medio cierre issues | {c.avg_issue_close_days:.1f} días |")
    lines.append(f"| Tiene releases | {'Sí' if c.has_releases else 'No'} |")
    lines.append(f"| Agent-readiness | {c.agent_readiness_score}/10 |")
    if c.is_solo_active:
        lines.append("| Modo solo-autor | activo (no abandonado) |")
    lines.append("")
    if c.agent_readiness_signals:
        lines.append("**Señales agent-ready detectadas:**")
        for s in c.agent_readiness_signals:
            lines.append(f"- {s}")
        lines.append("")
    if c.findings:
        lines.append("### Hallazgos de comunidad")
        for f in c.findings:
            lines.append(f"- **[{f.severity}]** {f.title}")
            if f.recommendation:
                lines.append(f"  - 💡 _{f.recommendation}_")
        lines.append("")

    lines.append("---")
    lines.append(f"_Generado por OSS Auditor v0.2.0_")
    return "\n".join(lines)
