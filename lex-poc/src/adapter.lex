# Wire-friendly entry point for cross-checking from Python.
#
# `lex run` decodes JSON arguments into lex Values, but the
# `$variant`-tagged convention used inside the runtime doesn't
# trigger for CLI args today (see `crates/lex-runtime/src/builtins.rs::json_to_value`).
# Until that's wired, we accept primitives only and decode the
# variants here. The Python side ships a flat dict, the lex side
# rebuilds the Report and runs scorer + verdict.
#
# Output is a single pipe-delimited string: "<verdict_code>|<grade>|<score>"
# so the Python comparator doesn't have to deal with variant
# encoding on the way back either.

import "std.float" as float
import "std.str"   as str

import "./models"  as m
import "./scorer"  as scorer
import "./verdict" as verdict


type CrossInput = {
  repo_type   :: Str,
  tech_status :: Str,
  tech_score  :: Float,
  biz_status  :: Str,
  biz_score   :: Float,
  biz_pc      :: Float,
  biz_di      :: Float,
  biz_ic      :: Float,
  biz_ms      :: Float,
  biz_eva     :: Float,
  com_status  :: Str,
  com_score   :: Float,
}


fn parse_status(s :: Str) -> m.DataStatus {
  match s {
    "available"   => Available,
    "skipped"     => Skipped,
    "unavailable" => Unavailable,
    _             => Unavailable,
  }
}

fn parse_repo_type(s :: Str) -> m.RepoType {
  match s {
    "proposal"       => Proposal,
    "implementation" => Implementation,
    _                => Implementation,
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


fn cross_check(i :: CrossInput) -> Str {
  let r := {
    repo_type: parse_repo_type(i.repo_type),
    technical: {
      score:       i.tech_score,
      data_status: parse_status(i.tech_status),
    },
    business: {
      score:                     i.biz_score,
      data_status:               parse_status(i.biz_status),
      problem_clarity:           i.biz_pc,
      differentiation:           i.biz_di,
      intellectual_contribution: i.biz_ic,
      market_signals:            i.biz_ms,
      execution_vs_ambition:     i.biz_eva,
    },
    community: {
      score:       i.com_score,
      data_status: parse_status(i.com_status),
    },
  }
  let out := scorer.compute_overall(r)
  let v   := verdict.compute_verdict(r)
  str.join(
    [v.code, "|", grade_label(out.grade), "|", float.to_str(out.score)],
    "",
  )
}
