"""Perspective-aware audit lenses.

Each lens remixes how the rubric weighs the three pillars and how
findings are surfaced, without changing the underlying signals.
Same evidence, framed for who's reading.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import AuditReport
    from .verdict import Verdict


# Default weights match scorer.WEIGHTS — kept in sync as the only source of truth.
DEFAULT_WEIGHTS = {"technical": 0.40, "business": 0.35, "community": 0.25}


@dataclass(frozen=True)
class Lens:
    name: str
    label: str
    description: str
    weights: dict[str, float]
    # Finding categories in priority order. Categories not in the list go last.
    finding_priorities: list[str] = field(default_factory=list)
    # If True, any technical `critical` finding downgrades a positive verdict
    # by one step and rewrites the actions to "fix criticals first".
    require_no_critical: bool = False


LENSES: dict[str, Lens] = {
    "general": Lens(
        name="general",
        label="General audience",
        description="Default rubric: balanced view across technical, thesis, and community.",
        weights=DEFAULT_WEIGHTS,
    ),
    "developer": Lens(
        name="developer",
        label="Developer / Engineer",
        description="Will I use this in production? Stack risk, tests, composability.",
        weights={"technical": 0.55, "business": 0.20, "community": 0.25},
        finding_priorities=[
            "testing", "process", "quality", "security",
            "dependencies", "legal", "community",
        ],
    ),
    "cto": Lens(
        name="cto",
        label="CTO / VP Engineering",
        description="Should I adopt or pilot? License, bus factor, hireable team, stack risk.",
        weights={"technical": 0.40, "business": 0.20, "community": 0.40},
        finding_priorities=[
            "legal", "security", "community", "dependencies",
            "process", "testing", "quality",
        ],
    ),
    "investor": Lens(
        name="investor",
        label="Investor / VC",
        description="Is it fundable? Differentiation, market signals, team velocity.",
        weights={"technical": 0.20, "business": 0.55, "community": 0.25},
        finding_priorities=[
            "community", "legal", "security", "process",
            "quality", "testing", "dependencies",
        ],
    ),
    "security": Lens(
        name="security",
        label="Security Engineer",
        description="Is it safe to depend on? Secrets, vulns, supply-chain hygiene.",
        weights={"technical": 0.65, "business": 0.10, "community": 0.25},
        finding_priorities=[
            "security", "dependencies", "process", "legal",
            "quality", "testing", "community",
        ],
        require_no_critical=True,
    ),
    "maintainer": Lens(
        name="maintainer",
        label="Open-source maintainer",
        description="Is this mergeable / contributable? Test density, docs, agent-readiness.",
        weights={"technical": 0.45, "business": 0.15, "community": 0.40},
        finding_priorities=[
            "testing", "process", "community", "quality",
            "legal", "security", "dependencies",
        ],
    ),
}


# When require_no_critical fires, the verdict is downgraded one step.
DOWNGRADE_MAP: dict[str, str] = {
    "bet-on-it":           "worth-helping",
    "worth-helping":       "promising-prototype",
    "ahead-of-its-time":   "incomplete-thesis",
    "promising-prototype": "incomplete-thesis",
    "solid-commodity":     "incomplete-thesis",
}


def get_lens(name: str | None) -> Lens:
    """Return the named lens, or `general` if name is None or unknown."""
    if name is None:
        return LENSES["general"]
    return LENSES.get(name, LENSES["general"])


def lens_names() -> list[str]:
    return list(LENSES.keys())


def category_priority(category: str, lens: Lens) -> int:
    """Lower value = higher priority. Unknown categories go last."""
    try:
        return lens.finding_priorities.index(category)
    except ValueError:
        return len(lens.finding_priorities)


def apply_lens_guard(
    verdict: "Verdict", report: "AuditReport", lens: Lens
) -> "Verdict":
    """Apply lens-specific verdict guards.

    Today only `require_no_critical` is implemented: if any technical
    finding is `critical`, downgrade the verdict by one step and
    rewrite actions to "fix criticals first".
    """
    if not lens.require_no_critical:
        return verdict
    has_critical = any(
        f.severity == "critical" for f in report.technical.findings
    )
    if not has_critical:
        return verdict
    new_code = DOWNGRADE_MAP.get(verdict.code)
    if new_code is None:
        return verdict
    return replace(
        verdict,
        code=new_code,
        label=f"{verdict.label} (security gate)",
        one_liner=(
            f"Security lens: critical findings present; downgraded from "
            f"`{verdict.code}`. Remediate the criticals first."
        ),
        actions={
            "developer": "STOP: critical findings. Do not adopt until fixed.",
            "cto": "Block adoption pending security review.",
            "investor": "Diligence required: critical findings need remediation.",
        },
    )
