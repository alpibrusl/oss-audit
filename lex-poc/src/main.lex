// Demo entry point: runs three canonical scenarios through
// `compute_overall` + `compute_verdict` and prints the results.
//
// Mirrors the sanity matrix from the Python smoke check that
// validated PR #10 (skipped vs unavailable + indeterminate
// verdict). No network, no I/O beyond stdout.

import "std.io" as io
import "std.str" as str

import "./models" as m
import "./scorer" as scorer
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


fn make_business(score :: Float, status :: m.DataStatus) -> m.Business {
  Business({
    score,
    data_status:               status,
    problem_clarity:           80.0,
    differentiation:           80.0,
    intellectual_contribution: 80.0,
    market_signals:            80.0,
    execution_vs_ambition:     80.0,
  })
}

fn make_report(
  tech_score :: Float, tech :: m.DataStatus,
  biz_score  :: Float, biz  :: m.DataStatus,
  com_score  :: Float, com  :: m.DataStatus,
) -> m.Report {
  Report({
    repo_type: Implementation,
    technical: Technical({ score: tech_score, data_status: tech }),
    business:  make_business(biz_score, biz),
    community: Community({ score: com_score, data_status: com }),
  })
}


fn print_case(name :: Str, r :: m.Report) -> [io] Nil {
  let out := scorer.compute_overall(r)
  let v   := verdict.compute_verdict(r)
  match out {
    Outcome({ score, grade }) =>
      match v {
        Verdict({ code, idea_band, execution_band, relevance_band }) =>
          io.print(str.concat([
            name, " | score=", str.from_float(score),
            " grade=", grade_label(grade),
            " verdict=", code,
            " bands=(idea=", band_label(idea_band),
            ", exec=", band_label(execution_band),
            ", rel=", band_label(relevance_band), ")",
          ])),
      },
  }
}


fn main() -> [io] Nil {
  // Polars-style: technical alone, others skipped. PR #10 fix says
  // this should produce score=90.0, bronze, indeterminate.
  print_case(
    "only-technical",
    make_report(90.0, Available, 0.0, Skipped, 0.0, Skipped),
  )

  // Tech + business, community skipped: 2 axes, gold-eligible.
  print_case(
    "tech+business",
    make_report(90.0, Available, 85.0, Available, 0.0, Skipped),
  )

  // All three available, all hot: bet-on-it.
  print_case(
    "full-3-axes",
    make_report(90.0, Available, 85.0, Available, 80.0, Available),
  )

  // Business attempted but unavailable: penalty applies, not renormalized.
  print_case(
    "biz-unavailable",
    make_report(90.0, Available, 0.0, Unavailable, 80.0, Available),
  )
}
