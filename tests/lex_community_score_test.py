"""Cross-check Python's community pillar scoring against the lex pilot.

Skipped silently if `lex` isn't on $PATH. Exercises a handful of
representative input shapes (healthy / dead / solo-but-active) for
both public-mode and private-mode scorers.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rubric.lex_cross_check import (  # noqa: E402
    compare_community_score, lex_community_score,
)


# (Python expected score, signals, mode). Optional ints/floats are
# raw Python — the bridge wraps them in the lex Option encoding.
CASES: list[tuple[float, dict, str]] = [
    # Public, healthy: stars=250 → 20, vel=18, cpa=5→1, rec=15, ar=7,
    # div=6, releases=5, close=10≤30→3 → 75.0
    (75.0, {
        "stars": 250, "commits_90d": 40, "contributors_count": 8,
        "last_commit_days": 5, "agent_readiness_score": 7,
        "has_releases": True, "avg_issue_close_days": 10.0,
    }, "public"),
    # Public, dead: stars=2 → 2 (clamped), nothing else.
    (2.0, {
        "stars": 2, "commits_90d": 0, "contributors_count": 1,
        "last_commit_days": 400, "agent_readiness_score": 0,
        "has_releases": False, "avg_issue_close_days": None,
    }, "public"),
    # Public, all axes maxed: stars=5000→25, vel=600→25, cpa=30→5,
    # rec=2→15, ar=10, div=20→10, releases=5, close=2→5 → 100.0
    (100.0, {
        "stars": 5000, "commits_90d": 600, "contributors_count": 20,
        "last_commit_days": 2, "agent_readiness_score": 10,
        "has_releases": True, "avg_issue_close_days": 2.0,
    }, "public"),
    # Private, healthy team: vel=18, rec=15, div=10, docs=20, ar=5 → 68
    (68.0, {
        "n_commits_90d": 40, "contributors_total": 6,
        "last_commit_days": 5,
        "has_codeowners": True, "has_contributing": True,
        "has_pr_template": True, "has_adrs": True, "has_runbooks": False,
        "agent_readiness_score": 5,
    }, "private"),
    # Private, solo no docs: vel=10, rec=15, div=0, docs=0, ar=2 → 27
    (27.0, {
        "n_commits_90d": 5, "contributors_total": 1,
        "last_commit_days": 7,
        "has_codeowners": False, "has_contributing": False,
        "has_pr_template": False, "has_adrs": False, "has_runbooks": False,
        "agent_readiness_score": 2,
    }, "private"),
]


def main() -> int:
    if shutil.which("lex") is None:
        print("[lex-community] lex binary not on PATH — skipping")
        return 0
    failures: list[str] = []
    for expected, signals, mode in CASES:
        result = lex_community_score(signals, mode)
        if result is None:
            failures.append(f"[{mode}] lex returned None for {signals}")
            continue
        diffs = compare_community_score(expected, result)
        if diffs:
            failures.append(f"[{mode}] expected={expected} {diffs}")
        else:
            print(f"  OK   [{mode}] expected={expected} lex={result}")
    if failures:
        print("\n[lex-community] FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n[lex-community] All cases agree ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
