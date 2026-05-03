# Cross-check entry point for the Python pipeline.
#
# Now that `lex run` decodes `{"$variant":"Name","args":[...]}`
# argument JSON correctly (#94), the Python side can ship a full
# Report with variant-tagged DataStatus / RepoType fields and the
# adapter just runs scorer + verdict and returns a flat
# {code, grade, score} record. Python parses that directly.

import "./models"  as m
import "./scorer"  as scorer
import "./verdict" as verdict


fn grade_label(g :: m.Grade) -> Str {
  match g {
    Platinum => "platinum",
    Gold     => "gold",
    Silver   => "silver",
    Bronze   => "bronze",
    Fail     => "fail",
  }
}


fn cross_check(r :: m.Report) -> { code :: Str, grade :: Str, score :: Float } {
  let v   := verdict.compute_verdict(r)
  let out := scorer.compute_overall(r)
  { code: v.code, grade: grade_label(out.grade), score: out.score }
}
