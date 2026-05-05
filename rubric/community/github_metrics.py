"""Community metrics from the GitHub REST API.

No token: 60 req/h rate limit. With token: 5000/h.
If the repo isn't on GitHub or there's no network, we return a minimal report.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..models import CommunityReport, Finding, RepoMeta
from .agent_readiness import score_agent_readiness

GH_API = "https://api.github.com"


def _headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _get(client: httpx.Client, path: str, **params) -> tuple[int, list | dict | None]:
    try:
        r = client.get(f"{GH_API}{path}", params=params, headers=_headers(), timeout=15.0)
        if r.status_code == 200:
            return 200, r.json()
        return r.status_code, None
    except httpx.HTTPError:
        return 0, None


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except ValueError:
        return None


def audit_community(meta: RepoMeta, repo_path: Path | None = None) -> CommunityReport:
    """Audit community metrics. Only works for repos on GitHub.

    `repo_path` is used to detect agent-readiness (local signals:
    CLAUDE.md, AGENTS.md, .cli/, mcp.json, etc.). If not passed, it's skipped.
    """
    ar_score = 0
    ar_signals: list[str] = []
    if repo_path is not None:
        ar_score, ar_signals = score_agent_readiness(repo_path)

    if not meta.owner or not meta.name:
        return CommunityReport(
            score=float(ar_score),
            agent_readiness_score=ar_score,
            agent_readiness_signals=ar_signals,
            findings=[Finding(
                severity="info", category="community",
                title="Community metrics not available",
                detail="They can only be collected for repos hosted on GitHub.",
            )],
        )

    findings: list[Finding] = []

    with httpx.Client() as client:
        status, repo_data = _get(client, f"/repos/{meta.owner}/{meta.name}")
        if status != 200 or not isinstance(repo_data, dict):
            # Status 403 = rate-limited or auth required; both fixable
            # with GITHUB_TOKEN. Surface as `medium` severity with a
            # concrete remediation so the user sees it in the top
            # recommendations, not buried in info-level chatter.
            has_token = bool(os.environ.get("GITHUB_TOKEN"))
            if status == 403:
                title = "GitHub API rate-limited (HTTP 403)"
                if has_token:
                    detail = (
                        "Even with GITHUB_TOKEN set, the request was refused. "
                        "Possible causes: token lacks scope, IP-level limit, "
                        "or token expired."
                    )
                    rec = "Verify GITHUB_TOKEN has `public_repo` scope (or `repo` for private)."
                else:
                    detail = (
                        "Anonymous GitHub API requests are limited to 60/h "
                        "and frequently hit 403 sooner. The community pillar "
                        "couldn't fetch any data; the audit is effectively "
                        "running on technical signals only."
                    )
                    rec = "Set GITHUB_TOKEN=<your-PAT> to lift the rate limit (5000/h authenticated)."
                severity = "medium"
            else:
                title = f"GitHub API returned status {status}"
                detail = (
                    "Network or upstream issue reaching api.github.com. "
                    "The community pillar has no data for this audit."
                )
                rec = "Re-run when the API is reachable."
                severity = "info"
            return CommunityReport(
                score=float(ar_score),
                agent_readiness_score=ar_score,
                agent_readiness_signals=ar_signals,
                findings=[Finding(
                    severity=severity, category="community",
                    title=title, detail=detail, recommendation=rec,
                )],
            )

        stars = repo_data.get("stargazers_count", 0)
        forks = repo_data.get("forks_count", 0)
        open_issues = repo_data.get("open_issues_count", 0)
        pushed_at = repo_data.get("pushed_at")
        last_commit_days = _days_since(pushed_at)
        has_releases = False  # updated below

        # Contributors (top 25 by commits)
        _, contribs = _get(client, f"/repos/{meta.owner}/{meta.name}/contributors", per_page=25)
        contributors_count = 0
        bus_top1 = 0.0
        bus_top3 = 0.0
        if isinstance(contribs, list):
            contributors_count = len(contribs)
            total_commits = sum(c.get("contributions", 0) for c in contribs)
            if total_commits > 0:
                contribs_sorted = sorted(contribs, key=lambda c: -c.get("contributions", 0))
                bus_top1 = round(contribs_sorted[0].get("contributions", 0) / total_commits * 100, 1)
                top3 = sum(c.get("contributions", 0) for c in contribs_sorted[:3])
                bus_top3 = round(top3 / total_commits * 100, 1)

        # Commits in the last 90 days via stats/participation (52 weeks)
        commits_90d = 0
        _, parti = _get(client, f"/repos/{meta.owner}/{meta.name}/stats/participation")
        if isinstance(parti, dict):
            all_weeks = parti.get("all", [])
            if isinstance(all_weeks, list) and len(all_weeks) >= 13:
                commits_90d = sum(all_weeks[-13:])

        # Releases
        _, releases = _get(client, f"/repos/{meta.owner}/{meta.name}/releases", per_page=1)
        has_releases = isinstance(releases, list) and len(releases) > 0

        # Closed issues (sample for average close time)
        _, closed = _get(client, f"/repos/{meta.owner}/{meta.name}/issues",
                         state="closed", per_page=30)
        avg_close_days: float | None = None
        closed_count = 0
        if isinstance(closed, list):
            closed_real = [i for i in closed if "pull_request" not in i]
            closed_count = len(closed_real)
            durations = []
            for issue in closed_real:
                created = _days_since(issue.get("created_at"))
                closed_at = _days_since(issue.get("closed_at"))
                if created is not None and closed_at is not None:
                    durations.append(max(created - closed_at, 0))
            if durations:
                avg_close_days = round(sum(durations) / len(durations), 1)

    # ----- Scoring (v0.2: alive + adopted, no headcount tax) -----
    # Weights: stars 25 / velocity 30 / recency 15 / agent-readiness 10 /
    #          diversity 10 / releases 5 / close-time 5 = 100
    # Bus factor is no longer a score lever — it surfaces as a contextual finding.
    score = 0.0

    # Adoption (stars): 25
    if stars >= 1000:
        score += 25
    elif stars >= 100:
        score += 20
    elif stars >= 25:
        score += 15
    elif stars >= 5:
        score += 8
    else:
        score += max(stars, 0)

    # Velocity (commits in last 90d): 25
    if commits_90d >= 50:
        score += 25
    elif commits_90d >= 15:
        score += 18
    elif commits_90d >= 3:
        score += 10
    elif commits_90d == 0:
        findings.append(Finding(
            severity="medium", category="community",
            title="No commits in the last 90 days",
            detail="Inactive project; possible abandonment signal.",
        ))

    # Velocity-per-author (AI-era signal: solo+AI shipping a lot): 5
    # active_contributors ~ contributors_count (approximation; devs who
    # only show up once still count). 0 if no data.
    cpa_90d = commits_90d / max(contributors_count, 1) if contributors_count else 0.0
    if cpa_90d >= 30:
        score += 5
    elif cpa_90d >= 15:
        score += 3
    elif cpa_90d >= 5:
        score += 1

    # Recency: 15
    if last_commit_days is not None:
        if last_commit_days <= 14:
            score += 15
        elif last_commit_days <= 60:
            score += 9
        elif last_commit_days <= 180:
            score += 4

    # Agent-readiness: 10
    score += ar_score

    # Contributor diversity: 10
    if contributors_count >= 20:
        score += 10
    elif contributors_count >= 5:
        score += 6
    elif contributors_count >= 2:
        score += 3

    # Releases: 5
    if has_releases:
        score += 5

    # Issue close time: 5
    if avg_close_days is not None:
        if avg_close_days <= 7:
            score += 5
        elif avg_close_days <= 30:
            score += 3

    # ----- Bus factor: context, not score -----
    # Solo-author + recent activity = NOT abandoned, just continuity risk.
    # Solo-author + no activity = genuinely worrying.
    is_solo = bus_top1 >= 70
    is_active = commits_90d >= 5 or (last_commit_days is not None and last_commit_days <= 30)
    is_solo_active = is_solo and is_active

    if is_solo and not is_active:
        findings.append(Finding(
            severity="high", category="community",
            title=f"Abandonment risk: bus factor {bus_top1}% with no recent activity",
            detail="Single author and no recent commits — typical combination for abandoned projects.",
            recommendation="Verify the project's status before adopting it in production.",
        ))
    elif is_solo:
        findings.append(Finding(
            severity="info", category="community",
            title=f"Active solo-author project ({bus_top1}% top contributor)",
            detail="Common in the AI-agent era. Real continuity risk, but not a low-quality signal.",
            recommendation="Consider the continuity risk: what's your plan if the author leaves?",
        ))

    score = min(round(score, 1), 100.0)

    return CommunityReport(
        score=score,
        stars=stars,
        forks=forks,
        open_issues=open_issues,
        closed_issues=closed_count,
        contributors=contributors_count,
        bus_factor_top1_pct=bus_top1,
        bus_factor_top3_pct=bus_top3,
        commits_last_90d=commits_90d,
        avg_issue_close_days=avg_close_days,
        last_commit_days_ago=last_commit_days,
        has_releases=has_releases,
        agent_readiness_score=ar_score,
        agent_readiness_signals=ar_signals,
        is_solo_active=is_solo_active,
        commits_per_author_90d=round(cpa_90d, 1),
        findings=findings,
    )
