"""Métricas de comunidad desde la API REST de GitHub.

Sin token: ratelimit de 60 req/h. Con token: 5000/h.
Si el repo no es de GitHub o no hay red, se devuelve un report mínimo.
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
    """Audita métricas de comunidad. Solo funciona con repos en GitHub.

    `repo_path` se usa para detectar agent-readiness (señales locales:
    CLAUDE.md, AGENTS.md, .cli/, mcp.json, etc.). Si no se pasa, se omite.
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
                title="Métricas de comunidad no disponibles",
                detail="Solo se pueden recolectar para repos de GitHub.",
            )],
        )

    findings: list[Finding] = []

    with httpx.Client() as client:
        status, repo_data = _get(client, f"/repos/{meta.owner}/{meta.name}")
        if status != 200 or not isinstance(repo_data, dict):
            return CommunityReport(
                score=float(ar_score),
                agent_readiness_score=ar_score,
                agent_readiness_signals=ar_signals,
                findings=[Finding(
                    severity="info", category="community",
                    title=f"GitHub API devolvió status {status}",
                    detail="Sin token, ratelimit es 60 req/h. Define GITHUB_TOKEN para más.",
                )],
            )

        stars = repo_data.get("stargazers_count", 0)
        forks = repo_data.get("forks_count", 0)
        open_issues = repo_data.get("open_issues_count", 0)
        pushed_at = repo_data.get("pushed_at")
        last_commit_days = _days_since(pushed_at)
        has_releases = False  # se actualizará abajo

        # Contributors (top 25 por commits)
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

        # Commits últimos 90 días via stats/participation (52 semanas)
        commits_90d = 0
        _, parti = _get(client, f"/repos/{meta.owner}/{meta.name}/stats/participation")
        if isinstance(parti, dict):
            all_weeks = parti.get("all", [])
            if isinstance(all_weeks, list) and len(all_weeks) >= 13:
                commits_90d = sum(all_weeks[-13:])

        # Releases
        _, releases = _get(client, f"/repos/{meta.owner}/{meta.name}/releases", per_page=1)
        has_releases = isinstance(releases, list) and len(releases) > 0

        # Issues cerrados (sample para tiempo medio de cierre)
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
    # Pesos: stars 25 / velocity 30 / recency 15 / agent-readiness 10 /
    #        diversity 10 / releases 5 / close-time 5 = 100
    # Bus factor ya NO es un score lever — sale como finding contextual.
    score = 0.0

    # Adopción (stars): 25
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

    # Velocity (commits últimos 90d): 30
    if commits_90d >= 50:
        score += 30
    elif commits_90d >= 15:
        score += 22
    elif commits_90d >= 3:
        score += 12
    elif commits_90d == 0:
        findings.append(Finding(
            severity="medium", category="community",
            title="Sin commits en los últimos 90 días",
            detail="Proyecto inactivo; señal de posible abandono.",
        ))

    # Recencia: 15
    if last_commit_days is not None:
        if last_commit_days <= 14:
            score += 15
        elif last_commit_days <= 60:
            score += 9
        elif last_commit_days <= 180:
            score += 4

    # Agent-readiness: 10
    score += ar_score

    # Diversidad de contribuidores: 10
    if contributors_count >= 20:
        score += 10
    elif contributors_count >= 5:
        score += 6
    elif contributors_count >= 2:
        score += 3

    # Releases: 5
    if has_releases:
        score += 5

    # Tiempo de cierre de issues: 5
    if avg_close_days is not None:
        if avg_close_days <= 7:
            score += 5
        elif avg_close_days <= 30:
            score += 3

    # ----- Bus factor: contexto, no score -----
    # Solo-autor + actividad reciente = NO abandonado, solo riesgo de continuidad.
    # Solo-autor + sin actividad = sí preocupante.
    is_solo = bus_top1 >= 70
    is_active = commits_90d >= 5 or (last_commit_days is not None and last_commit_days <= 30)
    is_solo_active = is_solo and is_active

    if is_solo and not is_active:
        findings.append(Finding(
            severity="high", category="community",
            title=f"Riesgo de abandono: bus factor {bus_top1}% sin actividad reciente",
            detail="Autor único y sin commits recientes — combinación típica de proyectos abandonados.",
            recommendation="Verificar el estado del proyecto antes de adoptarlo en producción.",
        ))
    elif is_solo:
        findings.append(Finding(
            severity="info", category="community",
            title=f"Proyecto solo-autor activo ({bus_top1}% top contributor)",
            detail="Común en la era de agentes IA. Riesgo de continuidad real, pero no señal de baja calidad.",
            recommendation="Considerar el riesgo de continuidad: ¿cuál sería tu plan si el autor se va?",
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
        findings=findings,
    )
