// Verdict layer — pure functional port of
// `oss_auditor/reporter/verdict.py::compute_verdict`.
//
// Three axes (idea / execution / relevance), each in {Low, Medium,
// High, NA}. Returns one of the 8 verdicts, plus `pass` (default)
// and `indeterminate` when fewer than 2 axes carry real data.

import "./models" as m


// --- band thresholds --------------------------------------------

fn band_of(score :: Float) -> m.Band {
  if score >= 70.0 { High }
  else if score >= 40.0 { Medium }
  else { Low }
}


// --- destructure helpers ----------------------------------------

fn repo_type(r :: m.Report) -> m.RepoType {
  match r { Report({ repo_type }) => repo_type }
}

fn biz(r :: m.Report) -> m.Business {
  match r { Report({ business }) => business }
}

fn tech_status(r :: m.Report) -> m.DataStatus {
  match r { Report({ technical: Technical({ data_status }) }) => data_status }
}

fn biz_status(r :: m.Report) -> m.DataStatus {
  match r { Report({ business: Business({ data_status }) }) => data_status }
}

fn com_status(r :: m.Report) -> m.DataStatus {
  match r { Report({ community: Community({ data_status }) }) => data_status }
}

fn is_available(s :: m.DataStatus) -> Bool {
  match s { Available => true, _ => false }
}


// --- per-axis raw score (only meaningful if axis has data) ------

fn idea_score(r :: m.Report) -> Float {
  match biz(r) {
    Business({ problem_clarity, differentiation, intellectual_contribution }) =>
      if intellectual_contribution > 0.0 {
        (problem_clarity + differentiation + intellectual_contribution) / 3.0
      } else {
        (problem_clarity + differentiation) / 2.0
      },
  }
}

fn execution_score(r :: m.Report) -> Float {
  match repo_type(r) {
    Proposal =>
      // In proposal mode, "execution" is spec clarity + maintenance cadence.
      (match biz(r) { Business({ execution_vs_ambition }) => execution_vs_ambition }
       + match r { Report({ community: Community({ score }) }) => score }) / 2.0,
    Implementation =>
      match r { Report({ technical: Technical({ score }) }) => score },
  }
}

fn relevance_score(r :: m.Report) -> Float {
  let ms := match biz(r) { Business({ market_signals }) => market_signals }
  let cs := match r { Report({ community: Community({ score }) }) => score }
  (ms + cs) / 2.0
}


// --- per-axis "has real data behind it?" ------------------------

fn idea_has_data(r :: m.Report) -> Bool {
  is_available(biz_status(r))
}

fn execution_has_data(r :: m.Report) -> Bool {
  match repo_type(r) {
    Proposal       => is_available(biz_status(r)) && is_available(com_status(r)),
    Implementation => is_available(tech_status(r)),
  }
}

fn relevance_has_data(r :: m.Report) -> Bool {
  is_available(com_status(r))
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


// --- verdict matrix ---------------------------------------------

fn mk(code :: Str, label :: Str, one_liner :: Str, b :: m.Bands) -> m.Verdict {
  match b {
    Bands({ idea, execution, relevance }) =>
      Verdict({
        code, label, one_liner,
        idea_band: idea, execution_band: execution, relevance_band: relevance,
      }),
  }
}

fn pass_verdict(b :: m.Bands) -> m.Verdict {
  mk("pass", "Pass", "Not enough signal on any axis. Pass.", b)
}

fn verdict_for(b :: m.Bands) -> m.Verdict {
  match b {
    Bands({ idea: High, execution: High, relevance: High }) =>
      mk("bet-on-it", "Bet on it",
         "Good idea, good execution, real demand. Adopt, contribute, or invest.", b),
    Bands({ idea: High, execution: High, relevance: Medium }) =>
      mk("bet-on-it", "Bet on it",
         "Good idea, good execution, growing demand. Adopt or contribute.", b),
    Bands({ idea: High, execution: Low, relevance: High }) =>
      mk("worth-helping", "Worth helping",
         "Good idea with weak execution and clear demand. Contribute, fork, or fund.", b),
    Bands({ idea: High, execution: Low, relevance: Medium }) =>
      mk("worth-helping", "Worth helping",
         "Good idea, early execution. High risk but big upside.", b),
    Bands({ idea: High, execution: Medium, relevance: Medium }) =>
      mk("promising-prototype", "Promising prototype",
         "Solid idea, execution halfway there. Revisit in 3 months.", b),
    Bands({ idea: High, execution: Medium, relevance: Low }) =>
      mk("promising-prototype", "Promising prototype",
         "Good idea executing OK but no visible demand yet.", b),
    Bands({ idea: High, execution: High, relevance: Low }) =>
      mk("ahead-of-its-time", "Ahead of its time",
         "Brilliant work without a market yet. Track it; don't bet today.", b),
    Bands({ idea: Low, execution: High, relevance: High }) =>
      mk("solid-commodity", "Solid commodity",
         "Real problem, good execution, no differentiation. Adopt if needed; no upside.", b),
    Bands({ idea: Low, execution: High, relevance: Medium }) =>
      mk("solid-commodity", "Solid commodity",
         "Good execution of a known problem. Useful, not novel.", b),
    Bands({ idea: Low, execution: High, relevance: Low }) =>
      mk("skill-in-search", "Skill in search of a problem",
         "Strong builder solving an irrelevant problem. Talent reusable; project isn't.", b),
    Bands({ idea: Medium, execution: Low, relevance: Low }) =>
      mk("incomplete-thesis", "Incomplete thesis",
         "Not enough signal. Come back when there's more code or traction.", b),
    Bands({ idea: Medium, execution: Medium, relevance: Medium }) =>
      mk("promising-prototype", "Promising prototype",
         "Everything halfway. If you like the space, it's worth following.", b),
    _ => pass_verdict(b),
  }
}


// --- public entry point -----------------------------------------

fn compute_verdict(r :: m.Report) -> m.Verdict {
  let bands := Bands({
    idea:      band_or_na(idea_has_data(r),      idea_score(r)),
    execution: band_or_na(execution_has_data(r), execution_score(r)),
    relevance: band_or_na(relevance_has_data(r), relevance_score(r)),
  })
  if axes_with_data(r) < 2 {
    mk("indeterminate", "Indeterminate",
       "Missing data on at least 2 of the 3 axes (idea / execution / relevance). Verdict suspended until there's more signal.",
       bands)
  } else {
    verdict_for(bands)
  }
}
