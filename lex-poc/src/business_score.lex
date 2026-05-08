# Business pillar overall-score formula — pure port of the
# weighted aggregation in
# `rubric/business/analyzer.py::analyze_business` (lines 320-331).
#
# The LLM-driven sub-scores are produced by Claude (or whatever
# backend is plugged in); this just turns six 0-100 sub-scores
# into a single 0-100 overall via the v0.5 weight tuple. Calibration-
# sensitive: weight changes here affect every business-pillar audit.
#
# v0.5 formula (sums to 1.00):
#   problem_clarity            0.20
#   execution_vs_ambition      0.20
#   differentiation            0.20
#   market_signals             0.10
#   viability_risks            0.15
#   intellectual_contribution  0.15
#
# Exposed:
#   score_business(signals)             -> Float
#   cross_check_business_score(signals) -> { score :: Float }

import "std.float" as float
import "std.int"   as int


type BusinessSignals = {
  problem_clarity            :: Float,
  execution_vs_ambition      :: Float,
  differentiation            :: Float,
  market_signals             :: Float,
  viability_risks            :: Float,
  intellectual_contribution  :: Float,
}


fn _round1(x :: Float) -> Float {
  let scaled := x * 10.0
  let bumped := if scaled >= 0.0 { scaled + 0.5 } else { scaled - 0.5 }
  let i := float.to_int(bumped)
  int.to_float(i) / 10.0
}


fn score_business(s :: BusinessSignals) -> Float {
  _round1(
    s.problem_clarity            * 0.20
  + s.execution_vs_ambition      * 0.20
  + s.differentiation            * 0.20
  + s.market_signals             * 0.10
  + s.viability_risks            * 0.15
  + s.intellectual_contribution  * 0.15
  )
}


fn cross_check_business_score(
  s :: BusinessSignals,
) -> { score :: Float } {
  { score: score_business(s) }
}
