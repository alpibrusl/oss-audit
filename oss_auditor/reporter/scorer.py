"""Score final y asignación de grado."""
from __future__ import annotations

from ..models import AuditReport


# Pesos por pilar
WEIGHTS = {"technical": 0.40, "business": 0.35, "community": 0.25}


def compute_overall(report: AuditReport) -> tuple[float, str]:
    """Calcula score total y grade."""
    overall = (
        report.technical.score * WEIGHTS["technical"]
        + report.business.score * WEIGHTS["business"]
        + report.community.score * WEIGHTS["community"]
    )
    overall = round(overall, 1)

    if overall >= 90:
        grade = "platinum"
    elif overall >= 75:
        grade = "gold"
    elif overall >= 60:
        grade = "silver"
    elif overall >= 40:
        grade = "bronze"
    else:
        grade = "fail"

    return overall, grade


def top_recommendations(report: AuditReport, n: int = 5) -> list[str]:
    """Extrae las top N recomendaciones cross-pillar."""
    recs: list[tuple[int, str]] = []  # (priority, text)

    severity_priority = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

    for f in report.technical.findings:
        if f.recommendation:
            pri = severity_priority.get(f.severity, 5)
            recs.append((pri, f"[Técnico/{f.severity}] {f.title}: {f.recommendation}"))

    for f in report.community.findings:
        if f.recommendation:
            pri = severity_priority.get(f.severity, 5)
            recs.append((pri, f"[Comunidad/{f.severity}] {f.title}: {f.recommendation}"))

    for w in report.business.weaknesses[:3]:
        recs.append((2, f"[Negocio] Atender: {w}"))

    recs.sort(key=lambda x: x[0])
    return [r[1] for r in recs[:n]]
