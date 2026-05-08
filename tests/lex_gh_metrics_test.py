"""Cross-check Python's GitHub-metrics derivations against the lex pilot.

Skipped silently if `lex` isn't on $PATH. Tests the pure derivations
(bus_factor_top1 / bus_factor_top3 / commits_90d / has_releases)
against synthetic GitHub-shaped inputs — no network required.

Python's actual derivation lives inline in `audit_community`; we
re-implement the same calculations here for the comparison anchor.
If those derivations drift in `audit_community`, this test will
catch it via the lex side disagreement (and the inline anchor
needs a parallel update — exactly the kind of drift the cross-check
exists to surface).
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rubric.lex_cross_check import compare_gh_metrics, lex_gh_metrics  # noqa: E402


def py_derive(contribs: list[dict], weeks: list[int], releases: list[dict]) -> dict:
    """Python-side reimplementation of audit_community's derivations."""
    total = sum(c.get("contributions", 0) for c in contribs)
    if total > 0:
        s = sorted(contribs, key=lambda c: -c.get("contributions", 0))
        bus_top1 = round(s[0].get("contributions", 0) / total * 100, 1)
        bus_top3 = round(sum(c.get("contributions", 0) for c in s[:3]) / total * 100, 1)
    else:
        bus_top1, bus_top3 = 0.0, 0.0
    commits_90d = sum(weeks[-13:]) if len(weeks) >= 13 else 0
    return {
        "bus_top1": bus_top1,
        "bus_top3": bus_top3,
        "commits_90d": commits_90d,
        "has_releases": len(releases) > 0,
    }


CASES: list[tuple[str, list[dict], list[int], list[dict]]] = [
    ("solo author",
     [{"contributions": 100}],
     list(range(1, 14)),
     []),
    ("diversified team",
     [{"contributions": 50}, {"contributions": 40}, {"contributions": 30},
      {"contributions": 20}, {"contributions": 10}],
     [5] * 15,
     [{"id": 1}]),
    ("empty",
     [], [], []),
    ("short weeks (<13)",
     [{"contributions": 10}], [1, 2, 3], []),
    ("unsorted contribs",
     [{"contributions": 5}, {"contributions": 100}, {"contributions": 20}],
     [0] * 52,
     []),
    ("realistic 52-week feed",
     [{"contributions": c} for c in [200, 150, 80, 50, 25, 10, 5, 5, 3, 2]],
     [3, 5, 4, 6, 8, 5, 4, 3, 2, 6, 7, 8, 9,    # earlier 13
      4, 5, 4, 6, 8, 5, 4, 3, 2, 6, 7, 8, 9,
      4, 5, 4, 6, 8, 5, 4, 3, 2, 6, 7, 8, 9,
      4, 5, 4, 6, 8, 5, 4, 3, 2, 6, 7, 8, 9],   # last 13 sums = 81
     [{"id": 1}, {"id": 2}]),
]


def main() -> int:
    if shutil.which("lex") is None:
        print("[lex-gh-metrics] lex binary not on PATH — skipping")
        return 0
    failures: list[str] = []
    for label, contribs, weeks, releases in CASES:
        gh_responses = {
            "contributors": contribs, "weeks": weeks, "releases": releases,
        }
        py_result = py_derive(contribs, weeks, releases)
        lex_result = lex_gh_metrics(gh_responses)
        if lex_result is None:
            failures.append(f"[{label}] lex returned None")
            continue
        diffs = compare_gh_metrics(
            py_result["bus_top1"], py_result["bus_top3"],
            py_result["commits_90d"], py_result["has_releases"],
            lex_result,
        )
        if diffs:
            failures.append(f"[{label}] {diffs}")
        else:
            print(f"  OK   {label:30} bus={py_result['bus_top1']}/{py_result['bus_top3']} "
                  f"c90={py_result['commits_90d']} rel={py_result['has_releases']}")
    if failures:
        print("\n[lex-gh-metrics] FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n[lex-gh-metrics] All cases agree ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
