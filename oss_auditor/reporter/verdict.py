"""Verdict layer: the "what do I do with this info" of the report.

Three axes derived from the pillars:
- idea = (problem_clarity + differentiation + intellectual_contribution) / 3
- execution = report.technical.score
- relevance = (business.market_signals + community.score) / 2

Each axis falls into {low, medium, high} (thresholds 40 and 70) and
the combination picks one of 8 verdicts. Each verdict ships concrete
actions for developer / CTO / investor.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models import AuditReport


@dataclass
class Verdict:
    code: str
    label: str
    one_liner: str
    idea_band: str
    execution_band: str
    relevance_band: str
    actions: dict[str, str] = field(default_factory=dict)


def _band(score: float) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _idea_score(report: AuditReport) -> float:
    b = report.business
    parts = [b.problem_clarity, b.differentiation]
    if b.intellectual_contribution > 0:
        parts.append(b.intellectual_contribution)
    return sum(parts) / len(parts) if parts else 0.0


def _execution_score(report: AuditReport) -> float:
    if report.repo.repo_type == "proposal":
        # In proposal mode there is no code execution. "Execution"
        # here means: spec clarity + author commits (maintenance).
        return (report.business.execution_vs_ambition + report.community.score) / 2
    return report.technical.score


def _relevance_score(report: AuditReport) -> float:
    return (report.business.market_signals + report.community.score) / 2


VERDICTS: dict[tuple[str, str, str], tuple[str, str, str]] = {
    # (idea, execution, relevance) -> (code, label, one_liner)
    ("high", "high", "high"): (
        "bet-on-it", "Bet on it",
        "Good idea, good execution, real demand. Adopt, contribute, or invest."),
    ("high", "high", "medium"): (
        "bet-on-it", "Bet on it",
        "Good idea, good execution, growing demand. Adopt or contribute."),
    ("high", "low", "high"): (
        "worth-helping", "Worth helping",
        "Good idea with weak execution and clear demand. Contribute, fork, "
        "or fund the team to close the gap."),
    ("high", "low", "medium"): (
        "worth-helping", "Worth helping",
        "Good idea, early execution. High risk but big upside."),
    ("high", "medium", "medium"): (
        "promising-prototype", "Promising prototype",
        "Solid idea, execution halfway there. Revisit in 3 months."),
    ("high", "medium", "low"): (
        "promising-prototype", "Promising prototype",
        "Good idea executing OK but no visible demand yet."),
    ("high", "high", "low"): (
        "ahead-of-its-time", "Ahead of its time",
        "Brilliant work without a market yet. Track it closely; don't bet today."),
    ("low", "high", "high"): (
        "solid-commodity", "Solid commodity",
        "Solves a real problem with good execution but no "
        "differentiation. Adopt if you need it; don't expect upside."),
    ("low", "high", "medium"): (
        "solid-commodity", "Solid commodity",
        "Good execution of a known problem. Useful, not novel."),
    ("low", "high", "low"): (
        "skill-in-search", "Skill in search of a problem",
        "Strong builder solving an irrelevant problem. The talent "
        "may be reusable; the project isn't."),
    ("medium", "low", "low"): (
        "incomplete-thesis", "Incomplete thesis",
        "Not enough signal. Come back when there's more code or traction."),
    ("medium", "medium", "medium"): (
        "promising-prototype", "Promising prototype",
        "Everything halfway. If you like the space, it's worth following."),
}


_DEFAULT = (
    "pass", "Pass",
    "Not enough signal on any axis. Pass.",
)

_INDETERMINATE = (
    "indeterminate", "Indeterminate",
    "Missing data on at least 2 of the 3 axes (idea / execution / "
    "relevance). Verdict suspended until there's more signal.",
)


ACTIONS_TEMPLATE: dict[str, dict[str, str]] = {
    "bet-on-it": {
        "developer": "Adopt in production if the use case fits. Consider contributing.",
        "cto": "Adopt or pilot seriously. Hireable team. Low stack risk.",
        "investor": "Fundable. Stage to match observable maturity. Main risk: sustained execution.",
    },
    "worth-helping": {
        "developer": "Worth forking or sending PRs. Don't use in prod yet.",
        "cto": "Pilot if the problem is strategic. Consider hiring the maintainer.",
        "investor": "Possible talent-first investment; the team > the current project. Acquihire is plausible.",
    },
    "promising-prototype": {
        "developer": "Watch. Star it, revisit in 3 months.",
        "cto": "Don't adopt yet. Consider for a future roadmap.",
        "investor": "Pre-seed signal. Track the progress; don't commit yet.",
    },
    "ahead-of-its-time": {
        "developer": "Learn from the technology. Too niche for production.",
        "cto": "Track. Useful if the market shifts toward this model.",
        "investor": "Timing risk. Not fundable today unless deep-tech with a long thesis.",
    },
    "solid-commodity": {
        "developer": "Adopt if you need the functionality. No technical upside.",
        "cto": "Very low stack risk. Good for filling a tactical gap.",
        "investor": "Not fundable as differentiated. Possible operational acquisition target.",
    },
    "skill-in-search": {
        "developer": "Skip the project. The author may be interesting to follow.",
        "cto": "Consider the maintainer for your team, not the project.",
        "investor": "Talent acquihire. The project itself isn't the investment.",
    },
    "incomplete-thesis": {
        "developer": "Too early. No action.",
        "cto": "Don't adopt. Not enough information to decide.",
        "investor": "Pre-pre-seed. No articulated thesis yet.",
    },
    "pass": {
        "developer": "Skip.",
        "cto": "Pass.",
        "investor": "Pass.",
    },
    "indeterminate": {
        "developer": "Insufficient data. Re-audit with all pillars enabled.",
        "cto": "No basis to decide on adoption. Requires a complete analysis.",
        "investor": "No articulable thesis. Close the data gaps before evaluating.",
    },
}


def _axes_with_data(report: AuditReport) -> dict[str, bool]:
    """Which verdict axes have real data behind them?

    - idea: requires the business pillar (problem_clarity,
      differentiation, intellectual_contribution).
    - execution: technical (implementation) or business+community
      (proposal).
    - relevance: requires community (the primary demand signal).
    """
    biz_ok = report.business.data_status == "available"
    tech_ok = report.technical.data_status == "available"
    com_ok = report.community.data_status == "available"
    is_proposal = report.repo.repo_type == "proposal"
    return {
        "idea": biz_ok,
        "execution": (biz_ok and com_ok) if is_proposal else tech_ok,
        "relevance": com_ok,
    }


def compute_verdict(report: AuditReport) -> Verdict:
    idea = _idea_score(report)
    execution = _execution_score(report)
    relevance = _relevance_score(report)

    axes = _axes_with_data(report)
    bands = {
        "idea": _band(idea) if axes["idea"] else "n/a",
        "execution": _band(execution) if axes["execution"] else "n/a",
        "relevance": _band(relevance) if axes["relevance"] else "n/a",
    }

    if sum(axes.values()) < 2:
        code, label, one_liner = _INDETERMINATE
    else:
        key = (bands["idea"], bands["execution"], bands["relevance"])
        code, label, one_liner = VERDICTS.get(key, _DEFAULT)

    return Verdict(
        code=code,
        label=label,
        one_liner=one_liner,
        idea_band=bands["idea"],
        execution_band=bands["execution"],
        relevance_band=bands["relevance"],
        actions=dict(ACTIONS_TEMPLATE.get(code, ACTIONS_TEMPLATE["pass"])),
    )


def compute_counterfactuals(report: AuditReport) -> list[str]:
    """Which hypothetical changes would move the verdict? Programmatic, cheap.

    We only simulate +30 on the weakest pillar and report whether
    the band moves up.
    """
    out: list[str] = []
    current = compute_verdict(report)

    pillars = [
        ("technical", report.technical.score, "the technical pillar"),
        ("business", report.business.score, "the thesis & innovation pillar"),
        ("community", report.community.score, "the community pillar"),
    ]
    weakest = min(pillars, key=lambda p: p[1])
    if weakest[1] >= 70:
        return out  # nothing dramatic to improve

    target = min(weakest[1] + 30, 100)
    # Build a hypothetical report. The boosted pillar also flips to
    # `available` — a higher score with no data behind it isn't
    # reportable as a counterfactual.
    cloned = report.model_copy(deep=True)
    if weakest[0] == "technical":
        cloned.technical.score = target
        cloned.technical.data_status = "available"
    elif weakest[0] == "business":
        cloned.business.score = target
        cloned.business.problem_clarity = max(cloned.business.problem_clarity, 70)
        cloned.business.differentiation = max(cloned.business.differentiation, 70)
        cloned.business.data_status = "available"
    else:
        cloned.community.score = target
        cloned.community.data_status = "available"

    new_verdict = compute_verdict(cloned)
    if new_verdict.code != current.code:
        out.append(
            f"If {weakest[2]} went from {weakest[1]:.0f} to {target:.0f}, "
            f"the verdict would change from `{current.code}` to `{new_verdict.code}`."
        )
    return out
