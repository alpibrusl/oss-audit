"""Score final y asignación de grado."""
from __future__ import annotations

from ..models import AuditReport


# Pesos por pilar
WEIGHTS = {"technical": 0.40, "business": 0.35, "community": 0.25}


def compute_overall(report: AuditReport) -> tuple[float, str]:
    """Calcula score total y grade.

    Renormaliza pesos solo sobre los pilares `intentionally_skipped`
    (--skip-* o `proposal` sin pilar técnico). Los pilares
    `data_unavailable` (se intentó analizar pero no hubo señal)
    conservan su peso y contribuyen 0, penalizando el total — la
    falta de datos es información, no un opt-out.

    Además, se cap-ea el grade por número de pilares con datos reales,
    para que un solo eje no llegue a platinum/gold/silver por
    renormalización.
    """
    pillars = [
        ("technical", report.technical.score, report.technical.data_status),
        ("business", report.business.score, report.business.data_status),
        ("community", report.community.score, report.community.data_status),
    ]
    available = [(k, s) for k, s, st in pillars if st == "available"]
    skipped_weight = sum(WEIGHTS[k] for k, _, st in pillars if st == "skipped")

    if not available:
        return 0.0, "fail"

    # Renormalizamos solo el peso de los `skipped`. Los `unavailable`
    # mantienen su peso y aportan 0.
    denom = 1.0 - skipped_weight
    overall = sum(score * WEIGHTS[k] for k, score in available) / denom
    overall = round(overall, 1)

    n_avail = len(available)
    if overall >= 90 and n_avail >= 3:
        grade = "platinum"
    elif overall >= 75 and n_avail >= 2:
        grade = "gold"
    elif overall >= 60 and n_avail >= 2:
        grade = "silver"
    elif overall >= 40:
        grade = "bronze"
    else:
        grade = "fail"

    # Con menos de 2 ejes con datos reales, el resultado es ruido de
    # calibración, no señal. Tope: bronze.
    if n_avail < 2 and grade in ("platinum", "gold", "silver"):
        grade = "bronze"

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
