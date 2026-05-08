"""Local-only signals for the community / team-health pillar.

Used when `--mode private`. Reads ONLY the local clone — no network,
no GITHUB_TOKEN. Derives signals from:

  - `git log` for contributor patterns, recency, bus factor.
  - Repo-level files for process maturity (CODEOWNERS, CONTRIBUTING,
    PR templates, ADRs, runbooks).
  - The same agent-readiness detector used in public mode (works
    purely on the local filesystem).

The resulting `CommunityReport` reuses the public-mode shape — fields
that don't apply locally (stars, forks, public issue counts) stay at
zero. The audit report's `mode` field lets the markdown renderer drop
those rows when displaying.
"""
from __future__ import annotations

import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from ..models import CommunityReport, Finding, RepoMeta
from .agent_readiness import score_agent_readiness


def _is_shallow_clone(repo_path: Path) -> bool:
    """Return True if the repo is a shallow clone (`.git/shallow` exists)."""
    return (repo_path / ".git" / "shallow").is_file()


def _git_log(repo_path: Path, since: str | None = None, limit: int = 5000) -> list[dict]:
    """Run git log and parse out (sha, author_email, ts) per commit. No-merge."""
    args = ["git", "log", f"-n{limit}", "--pretty=format:%H|%ae|%at", "--no-merges"]
    if since is not None:
        args.append(f"--since={since}")
    try:
        result = subprocess.run(
            args, cwd=repo_path, capture_output=True, text=True, timeout=30, check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    if result.returncode != 0:
        return []
    out: list[dict] = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        try:
            ts = int(parts[2])
        except ValueError:
            continue
        out.append({"sha": parts[0], "author": parts[1], "ts": ts})
    return out


def _has_any(repo_path: Path, candidates: list[str]) -> bool:
    return any((repo_path / c).exists() for c in candidates)


def _has_any_dir(repo_path: Path, candidates: list[str]) -> bool:
    return any((repo_path / c).is_dir() for c in candidates)


def audit_community_internal(meta: RepoMeta, repo_path: Path) -> CommunityReport:
    """Local-only community / team-health metrics. No network."""
    findings: list[Finding] = []

    # Agent-readiness still works locally (CLAUDE.md, AGENTS.md, etc.)
    ar_score, ar_signals = score_agent_readiness(repo_path)

    # ----- git log signals -----
    if _is_shallow_clone(repo_path):
        # Heuristic: a depth-1 clone collapses every git-log signal to
        # "1 contributor, 100% bus factor" regardless of the actual
        # repo. Surface that explicitly so the report reflects "we
        # don't know" instead of "the audited repo is solo-author".
        findings.append(Finding(
            severity="info", category="community",
            title="Shallow clone — community signals from git log unreliable",
            detail=(
                "The local clone is shallow (only the most recent commit is "
                "present). Re-clone with `git fetch --unshallow` (or run "
                "rubric on a full local checkout) to get accurate "
                "contributor / recency / bus-factor signals."
            ),
            recommendation="Audit a full clone for accurate private-mode signals.",
        ))

    commits_90d = _git_log(repo_path, since="90.days")
    commits_all = _git_log(repo_path)

    contributors_total = len({c["author"] for c in commits_all})
    n_commits_90d = len(commits_90d)
    contributors_90d = len({c["author"] for c in commits_90d}) if commits_90d else 0

    bus_top1_pct = 0.0
    bus_top3_pct = 0.0
    if commits_all:
        author_counts = Counter(c["author"] for c in commits_all)
        total = sum(author_counts.values())
        if total > 0:
            top = author_counts.most_common(3)
            bus_top1_pct = round(top[0][1] / total * 100, 1)
            bus_top3_pct = round(sum(c for _, c in top) / total * 100, 1)

    last_commit_days: int | None = None
    if commits_all:
        latest_ts = max(c["ts"] for c in commits_all)
        last_commit_days = (
            datetime.now(timezone.utc)
            - datetime.fromtimestamp(latest_ts, tz=timezone.utc)
        ).days

    # ----- process / team-health files -----
    has_codeowners = _has_any(repo_path, [
        "CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS",
    ])
    has_contributing = _has_any(repo_path, [
        "CONTRIBUTING.md", ".github/CONTRIBUTING.md",
    ])
    has_pr_template = _has_any(repo_path, [
        ".github/PULL_REQUEST_TEMPLATE.md", ".github/pull_request_template.md",
        "docs/PULL_REQUEST_TEMPLATE.md",
    ])
    has_adrs = _has_any_dir(repo_path, [
        "docs/adr", "docs/decisions", "adrs", "doc/adr",
    ])
    has_runbooks = _has_any_dir(repo_path, [
        "runbooks", "docs/runbooks", "docs/operations", "ops",
    ])

    # ----- Scoring (private-mode rebalance) -----
    # Internal-mode pillar weights (out of 100):
    #   velocity 25 / recency 15 / contributor diversity 15 /
    #   process docs (CODEOWNERS / CONTRIBUTING / PR-template / ADRs / runbooks) 25 /
    #   agent-readiness 10 / process review-routing 10
    score = 0.0

    # Velocity (commits in last 90d): 25
    if n_commits_90d >= 50:
        score += 25
    elif n_commits_90d >= 15:
        score += 18
    elif n_commits_90d >= 3:
        score += 10
    elif n_commits_90d == 0:
        findings.append(Finding(
            severity="medium", category="community",
            title="No commits in the last 90 days",
            detail="Inactive repo; possible abandonment signal.",
        ))

    # Recency: 15
    if last_commit_days is not None:
        if last_commit_days <= 14:
            score += 15
        elif last_commit_days <= 60:
            score += 9
        elif last_commit_days <= 180:
            score += 4

    # Contributor diversity: 15
    if contributors_total >= 10:
        score += 15
    elif contributors_total >= 4:
        score += 10
    elif contributors_total >= 2:
        score += 5

    # Process documentation: 25 (5 each)
    if has_codeowners:
        score += 5
    if has_contributing:
        score += 5
    if has_pr_template:
        score += 5
    if has_adrs:
        score += 5
    if has_runbooks:
        score += 5

    # Agent-readiness: 10
    score += ar_score

    # ----- Bus factor as context (not score lever) -----
    is_solo = bus_top1_pct >= 70.0
    is_active = n_commits_90d >= 5 or (
        last_commit_days is not None and last_commit_days <= 30
    )
    is_solo_active = is_solo and is_active

    if is_solo and not is_active:
        findings.append(Finding(
            severity="high", category="community",
            title=f"Abandonment risk: bus factor {bus_top1_pct}% with no recent activity",
            detail="Single primary author and no recent commits.",
            recommendation="Verify the repo is actively owned; consider archiving / sunsetting.",
        ))
    elif is_solo:
        findings.append(Finding(
            severity="info", category="community",
            title=f"Solo-owner internal repo ({bus_top1_pct}% top author)",
            detail="Single primary contributor on a private codebase.",
            recommendation="Document succession plan; ensure at least one peer reviewer.",
        ))

    if not has_codeowners:
        findings.append(Finding(
            severity="low", category="process",
            title="No CODEOWNERS file",
            detail="Code-review routing isn't documented.",
            recommendation="Add CODEOWNERS so review responsibilities are explicit.",
        ))
    if not (has_adrs or has_runbooks):
        findings.append(Finding(
            severity="info", category="process",
            title="No ADRs or runbooks detected",
            detail="No `docs/adr/` or `runbooks/` folder found.",
            recommendation="ADRs document WHY decisions were made; runbooks document HOW to operate the service. Both pay off in a year.",
        ))

    score = min(round(score, 1), 100.0)
    cpa_90d = n_commits_90d / max(contributors_90d, 1) if contributors_90d else 0.0

    # Stash the per-axis inputs so the lex cross-check can validate
    # the score without rewalking git log + process docs. Mirrors
    # the lex `CommunityInternalSignals` record exactly.
    signals = {
        "n_commits_90d":         int(n_commits_90d),
        "contributors_total":    int(contributors_total),
        "last_commit_days":      last_commit_days,  # int | None
        "has_codeowners":        bool(has_codeowners),
        "has_contributing":      bool(has_contributing),
        "has_pr_template":       bool(has_pr_template),
        "has_adrs":              bool(has_adrs),
        "has_runbooks":          bool(has_runbooks),
        "agent_readiness_score": int(ar_score),
    }

    return CommunityReport(
        score=score,
        stars=0,  # not applicable in private mode
        forks=0,
        open_issues=0,
        closed_issues=0,
        contributors=contributors_total,
        bus_factor_top1_pct=bus_top1_pct,
        bus_factor_top3_pct=bus_top3_pct,
        commits_last_90d=n_commits_90d,
        last_commit_days_ago=last_commit_days,
        has_releases=False,  # local mode can't tell without git tag inspection
        agent_readiness_score=ar_score,
        agent_readiness_signals=ar_signals,
        is_solo_active=is_solo_active,
        commits_per_author_90d=round(cpa_90d, 1),
        findings=findings,
        raw={"signals": signals, "mode": "private"},
    )
