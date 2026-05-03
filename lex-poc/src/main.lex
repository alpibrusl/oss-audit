# Demo runner: feeds four canonical scenarios through the
# scoring + verdict library and prints the result on one line each.
# Mirrors the Python sanity matrix that validated PR #10.

import "std.io"    as io
import "std.str"   as str
import "std.float" as float

import "./oss_audit" as core


fn band_label(b :: core.Band) -> Str {
  match b {
    High   => "high",
    Medium => "medium",
    Low    => "low",
    NA     => "n/a",
  }
}

fn grade_label(g :: core.Grade) -> Str {
  match g {
    Platinum => "platinum",
    Gold     => "gold",
    Silver   => "silver",
    Bronze   => "bronze",
    Fail     => "fail",
  }
}


fn make_report(
  tech_score :: Float, tech :: core.DataStatus,
  biz_score  :: Float, biz  :: core.DataStatus,
  com_score  :: Float, com  :: core.DataStatus,
) -> core.Report {
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


fn line(name :: Str, r :: core.Report) -> Str {
  let out := core.compute_overall(r)
  let v   := core.compute_verdict(r)
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
