# Demo runner + assertion suite for the rubric port.
#
# Two functions:
#   main         — the original print-each-scenario demo (unchanged shape).
#   run_tests    — `std.test`-based suite that asserts each scenario's
#                  verdict code, grade, and overall score against the
#                  Python reference. Returns 0 on success, exit-style
#                  failure count otherwise.
#
# Both walk the same four canonical scenarios that validated PR #10
# (skipped vs unavailable + indeterminate verdict).

import "std.io"    as io
import "std.str"   as str
import "std.list"  as list
import "std.float" as float
import "std.test"  as test

import "./models"  as m
import "./scorer"  as scorer
import "./verdict" as verdict


fn band_label(b :: m.Band) -> Str {
  match b {
    High   => "high",
    Medium => "medium",
    Low    => "low",
    NA     => "n/a",
  }
}

fn grade_label(g :: m.Grade) -> Str {
  match g {
    Platinum => "platinum",
    Gold     => "gold",
    Silver   => "silver",
    Bronze   => "bronze",
    Fail     => "fail",
  }
}


fn make_report(
  tech_score :: Float, tech :: m.DataStatus,
  biz_score  :: Float, biz  :: m.DataStatus,
  com_score  :: Float, com  :: m.DataStatus,
) -> m.Report {
  {
    repo_type: Implementation,
    technical: { score: tech_score, data_status: tech },
    business: {
      score:                     biz_score,
      data_status:               biz,
      problem_clarity:           80.0,
      differentiation:           80.0,
      intellectual_contribution: 80.0,
      market_signals:            80.0,
      execution_vs_ambition:     80.0,
    },
    community: { score: com_score, data_status: com },
  }
}


fn line(name :: Str, r :: m.Report) -> Str {
  let out := scorer.compute_overall(r)
  let v   := verdict.compute_verdict(r)
  str.join(
    [
      name, " | score=", float.to_str(out.score),
      " grade=", grade_label(out.grade),
      " verdict=", v.code,
      " bands=(idea=", band_label(v.idea_band),
      ", exec=", band_label(v.execution_band),
      ", rel=", band_label(v.relevance_band), ")",
    ],
    "",
  )
}


# ---- assertion suite (std.test) ---------------------------------
#
# Each test is a `Result[Unit, Str]`. Suites are List[Result] folded
# at the end — std.test v1 doesn't have closures-as-values yet so
# tests are eagerly computed (per the std.test PR commit notes).

fn check_case(
  r :: m.Report, expected_code :: Str, expected_grade :: Str, expected_score :: Float,
) -> Result[Unit, Str] {
  let out := scorer.compute_overall(r)
  let v   := verdict.compute_verdict(r)
  match test.assert_eq(v.code, expected_code) {
    Err(e) => Err(str.concat("verdict: ", e)),
    Ok(_)  => match test.assert_eq(grade_label(out.grade), expected_grade) {
      Err(e) => Err(str.concat("grade: ", e)),
      # Last call returns the Result directly — no Unit construction needed.
      Ok(_)  => test.assert_eq(out.score, expected_score),
    },
  }
}

fn report_case(name :: Str, v :: Result[Unit, Str]) -> [io] Int {
  match v {
    Ok(_)    => {
      io.print(str.concat("✓ ", name))
      0
    },
    Err(msg) => {
      io.print(str.concat(str.concat("✗ ", name), str.concat(": ", msg)))
      1
    },
  }
}

fn run_tests() -> [io] Int {
  # Each case is (name, eagerly-computed verdict). Tuple list since
  # `list.zip` isn't in std.list yet.
  let cases := [
    ("only-technical", check_case(
      make_report(90.0, Available, 0.0, Skipped, 0.0, Skipped),
      "indeterminate", "bronze", 90.0,
    )),
    ("tech+business", check_case(
      make_report(90.0, Available, 85.0, Available, 0.0, Skipped),
      "pass", "gold", 87.7,
    )),
    ("full-3-axes", check_case(
      make_report(90.0, Available, 85.0, Available, 80.0, Available),
      "bet-on-it", "gold", 85.8,
    )),
    ("biz-unavailable", check_case(
      make_report(90.0, Available, 0.0, Unavailable, 80.0, Available),
      "pass", "bronze", 56.0,
    )),
  ]
  list.fold(
    cases,
    0,
    fn (acc :: Int, p :: (Str, Result[Unit, Str])) -> [io] Int {
      match p {
        (name, v) => acc + report_case(name, v),
      }
    },
  )
}


fn main() -> [io] Nil {
  # Polars-style: technical alone, others skipped → bronze, indeterminate.
  io.print(line(
    "only-technical",
    make_report(90.0, Available, 0.0, Skipped, 0.0, Skipped),
  ))
  # Tech + business, community skipped: 2 axes available.
  io.print(line(
    "tech+business",
    make_report(90.0, Available, 85.0, Available, 0.0, Skipped),
  ))
  # All three available, all hot → bet-on-it / gold.
  io.print(line(
    "full-3-axes",
    make_report(90.0, Available, 85.0, Available, 80.0, Available),
  ))
  # Business attempted but unavailable: penalty applies, not renormalized.
  io.print(line(
    "biz-unavailable",
    make_report(90.0, Available, 0.0, Unavailable, 80.0, Available),
  ))
}
