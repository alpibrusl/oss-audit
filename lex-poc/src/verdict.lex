# Verdict layer — pure functional port of
# `oss_auditor/reporter/verdict.py::compute_verdict`.
#
# Three axes (idea / execution / relevance), each in {Low, Medium,
# High, NA}. Returns one of the 8 verdicts, plus `pass` (default)
# and `indeterminate` when fewer than 2 axes carry real data.

import "./models" as m


fn band_of(score :: Float) -> m.Band {
  if score >= 70.0 { High }
  else {
    if score >= 40.0 { Medium } else { Low }
  }
}


fn idea_score(r :: m.Report) -> Float {
  let pc := r.business.problem_clarity
  let di := r.business.differentiation
  let ic := r.business.intellectual_contribution
  if ic > 0.0 {
    (pc + di + ic) / 3.0
  } else {
    (pc + di) / 2.0
  }
}

fn execution_score(r :: m.Report) -> Float {
  match r.repo_type {
    Proposal       => (r.business.execution_vs_ambition + r.community.score) / 2.0,
    Implementation => r.technical.score,
  }
}

fn relevance_score(r :: m.Report) -> Float {
  (r.business.market_signals + r.community.score) / 2.0
}


fn is_available(s :: m.DataStatus) -> Bool {
  match s { Available => true, _ => false }
}

fn idea_has_data(r :: m.Report) -> Bool {
  is_available(r.business.data_status)
}

fn execution_has_data(r :: m.Report) -> Bool {
  match r.repo_type {
    Proposal       => is_available(r.business.data_status)
                      and is_available(r.community.data_status),
    Implementation => is_available(r.technical.data_status),
  }
}

fn relevance_has_data(r :: m.Report) -> Bool {
  is_available(r.community.data_status)
}

fn band_or_na(has_data :: Bool, score :: Float) -> m.Band {
  if has_data { band_of(score) } else { NA }
}

fn axes_with_data(r :: m.Report) -> Int {
  let i := if idea_has_data(r)      { 1 } else { 0 }
  let e := if execution_has_data(r) { 1 } else { 0 }
  let v := if relevance_has_data(r) { 1 } else { 0 }
  i + e + v
}


fn mk(code :: Str, label :: Str, one_liner :: Str, b :: m.Bands) -> m.Verdict {
  {
    code:           code,
    label:          label,
    one_liner:      one_liner,
    idea_band:      b.idea,
    execution_band: b.execution,
    relevance_band: b.relevance,
  }
}

fn pass_verdict(b :: m.Bands) -> m.Verdict {
  mk("pass", "Pass", "Not enough signal on any axis. Pass.", b)
}

fn verdict_for(b :: m.Bands) -> m.Verdict {
  match b {
    { idea: High, execution: High, relevance: High } =>
      mk("bet-on-it", "Bet on it",
         "Good idea, good execution, real demand. Adopt, contribute, or invest.", b),
    { idea: High, execution: High, relevance: Medium } =>
      mk("bet-on-it", "Bet on it",
         "Good idea, good execution, growing demand. Adopt or contribute.", b),
    { idea: High, execution: Low, relevance: High } =>
      mk("worth-helping", "Worth helping",
         "Good idea with weak execution and clear demand. Contribute, fork, or fund.", b),
    { idea: High, execution: Low, relevance: Medium } =>
      mk("worth-helping", "Worth helping",
         "Good idea, early execution. High risk but big upside.", b),
    { idea: High, execution: Medium, relevance: Medium } =>
      mk("promising-prototype", "Promising prototype",
         "Solid idea, execution halfway there. Revisit in 3 months.", b),
    { idea: High, execution: Medium, relevance: Low } =>
      mk("promising-prototype", "Promising prototype",
         "Good idea executing OK but no visible demand yet.", b),
    { idea: High, execution: High, relevance: Low } =>
      mk("ahead-of-its-time", "Ahead of its time",
         "Brilliant work without a market yet. Track it; don't bet today.", b),
    { idea: Low, execution: High, relevance: High } =>
      mk("solid-commodity", "Solid commodity",
         "Real problem, good execution, no differentiation. Adopt if needed; no upside.", b),
    { idea: Low, execution: High, relevance: Medium } =>
      mk("solid-commodity", "Solid commodity",
         "Good execution of a known problem. Useful, not novel.", b),
    { idea: Low, execution: High, relevance: Low } =>
      mk("skill-in-search", "Skill in search of a problem",
         "Strong builder solving an irrelevant problem. Talent reusable; project isn't.", b),
    { idea: Medium, execution: Low, relevance: Low } =>
      mk("incomplete-thesis", "Incomplete thesis",
         "Not enough signal. Come back when there's more code or traction.", b),
    { idea: Medium, execution: Medium, relevance: Medium } =>
      mk("promising-prototype", "Promising prototype",
         "Everything halfway. If you like the space, it's worth following.", b),
    _ => pass_verdict(b),
  }
}


fn compute_verdict(r :: m.Report) -> m.Verdict {
  let bands := {
    idea:      band_or_na(idea_has_data(r),      idea_score(r)),
    execution: band_or_na(execution_has_data(r), execution_score(r)),
    relevance: band_or_na(relevance_has_data(r), relevance_score(r)),
  }
  if axes_with_data(r) < 2 {
    mk("indeterminate", "Indeterminate",
       "Missing data on at least 2 of the 3 axes (idea / execution / relevance). Verdict suspended until there's more signal.",
       bands)
  } else {
    verdict_for(bands)
  }
}
