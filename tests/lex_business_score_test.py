"""Cross-check Python's business overall-score formula against the lex pilot.

The actual sub-scores come from an LLM in production; this test
substitutes synthetic values so we can exercise the v0.5 weight
tuple without an API key.

Skipped silently if `lex` isn't on $PATH.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rubric.lex_cross_check import (  # noqa: E402
    compare_business_score, lex_business_score,
)


def py_overall(s: dict) -> float:
    """Python-side reimplementation of analyzer.py's overall calculation."""
    return round(
        s["problem_clarity"] * 0.20
        + s["execution_vs_ambition"] * 0.20
        + s["differentiation"] * 0.20
        + s["market_signals"] * 0.10
        + s["viability_risks"] * 0.15
        + s["intellectual_contribution"] * 0.15,
        1,
    )


CASES: list[dict] = [
    {"problem_clarity": 80, "execution_vs_ambition": 70, "differentiation": 60,
     "market_signals": 50, "viability_risks": 40, "intellectual_contribution": 30},
    {"problem_clarity": 100, "execution_vs_ambition": 100, "differentiation": 100,
     "market_signals": 100, "viability_risks": 100, "intellectual_contribution": 100},
    {"problem_clarity": 0, "execution_vs_ambition": 0, "differentiation": 0,
     "market_signals": 0, "viability_risks": 0, "intellectual_contribution": 0},
    # Skewed — high IC, low everything else (a "novel-but-rough" project)
    {"problem_clarity": 30, "execution_vs_ambition": 25, "differentiation": 70,
     "market_signals": 10, "viability_risks": 35, "intellectual_contribution": 95},
    # Realistic mid-tier project
    {"problem_clarity": 65, "execution_vs_ambition": 55, "differentiation": 50,
     "market_signals": 40, "viability_risks": 60, "intellectual_contribution": 45},
]


def main() -> int:
    if shutil.which("lex") is None:
        print("[lex-business] lex binary not on PATH — skipping")
        return 0
    failures: list[str] = []
    for s in CASES:
        expected = py_overall(s)
        got = lex_business_score(s)
        if got is None:
            failures.append(f"lex returned None for {s}")
            continue
        diffs = compare_business_score(expected, got)
        if diffs:
            failures.append(f"expected={expected} {diffs}")
        else:
            print(f"  OK   pc={s['problem_clarity']} ev={s['execution_vs_ambition']} "
                  f"di={s['differentiation']} ms={s['market_signals']} "
                  f"vr={s['viability_risks']} ic={s['intellectual_contribution']} "
                  f"-> {got}")
    if failures:
        print("\n[lex-business] FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n[lex-business] All cases agree ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
