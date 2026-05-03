"""Final score and grade assignment."""
from __future__ import annotations

from ..models import AuditReport


# Per-pillar weights
WEIGHTS = {"technical": 0.40, "business": 0.35, "community": 0.25}


def compute_overall(report: AuditReport) -> tuple[float, str]:
    """Compute total score and grade.

    Renormalize weights only over `intentionally_skipped` pillars
    (--skip-* or `proposal` without a technical pillar). Pillars
    marked `data_unavailable` (we tried to analyze but got no
    signal) keep their weight and contribute 0, penalizing the
    total — missing data is information, not an opt-out.

    The grade is also capped by the number of pillars with real
    data, so that a single axis can't reach platinum / gold / silver
    via renormalization.
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

    # Renormalize only the weight of `skipped` pillars. `unavailable`
    # ones keep their weight and contribute 0.
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

    # With fewer than 2 axes carrying real data the result is
    # calibration noise, not signal. Cap: bronze.
    if n_avail < 2 and grade in ("platinum", "gold", "silver"):
        grade = "bronze"

    return overall, grade


def top_recommendations(report: AuditReport, n: int = 5) -> list[str]:
    """Extract the top N cross-pillar recommendations."""
    recs: list[tuple[int, str]] = []  # (priority, text)

    severity_priority = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

    for f in report.technical.findings:
        if f.recommendation:
            pri = severity_priority.get(f.severity, 5)
            recs.append((pri, f"[Technical/{f.severity}] {f.title}: {f.recommendation}"))

    for f in report.community.findings:
        if f.recommendation:
            pri = severity_priority.get(f.severity, 5)
            recs.append((pri, f"[Community/{f.severity}] {f.title}: {f.recommendation}"))

    for w in report.business.weaknesses[:3]:
        recs.append((2, f"[Business] Address: {w}"))

    recs.sort(key=lambda x: x[0])
    return [r[1] for r in recs[:n]]
