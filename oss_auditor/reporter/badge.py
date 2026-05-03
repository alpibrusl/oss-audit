"""Shields.io badge generation for audits.

Two formats:
- Static URL: `https://img.shields.io/badge/oss--audit-92.5/100-brightgreen`
- Endpoint JSON: for dynamic hosting (raw.githubusercontent.com, gist, etc.).
"""
from __future__ import annotations

from urllib.parse import quote

from ..models import AuditReport

GRADE_COLOR = {
    "platinum": "blueviolet",
    "gold": "brightgreen",
    "silver": "green",
    "bronze": "yellow",
    "fail": "red",
}


def _shields_escape(s: str) -> str:
    """Escape a string for shields.io's 'badge/<label>-<message>-<color>' format.

    Shields.io rules: '-' -> '--', '_' -> '__', ' ' -> '_', then URL-encode.
    """
    s = s.replace("-", "--").replace("_", "__").replace(" ", "_")
    return quote(s, safe="")


def to_shields_url(report: AuditReport, label: str = "oss-audit") -> str:
    """Return the static shields.io URL for the badge."""
    color = GRADE_COLOR.get(report.grade, "lightgrey")
    message = f"{report.overall_score:.1f}/100 {report.grade}"
    return (
        f"https://img.shields.io/badge/"
        f"{_shields_escape(label)}-{_shields_escape(message)}-{color}"
    )


def to_endpoint_payload(report: AuditReport, label: str = "oss-audit") -> dict:
    """Return a JSON payload compatible with shields.io endpoint badges.

    Typical hosting: commit this JSON into the repo and reference it via
    `https://img.shields.io/endpoint?url=<raw_url>`.
    """
    return {
        "schemaVersion": 1,
        "label": label,
        "message": f"{report.overall_score:.1f}/100 {report.grade}",
        "color": GRADE_COLOR.get(report.grade, "lightgrey"),
        "cacheSeconds": 3600,
    }


def to_markdown(report: AuditReport, link_url: str | None = None,
                label: str = "oss-audit") -> str:
    """Return a Markdown snippet ready to paste into a README."""
    badge_url = to_shields_url(report, label)
    target = link_url or report.repo.source
    return f"[![OSS Audit]({badge_url})]({target})"
