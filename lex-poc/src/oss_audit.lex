# OSS Auditor scoring + verdict library.
#
# Pure functional port of the rubric-critical core:
#   - oss_auditor/reporter/scorer.py::compute_overall
#   - oss_auditor/reporter/verdict.py::compute_verdict
#
# Types, scoring, and verdict live in one module so every consumer
# references them through a single alias — works around lex's MVP
# local-import mangling, which currently treats the same module
# imported from two paths as two distinct nominal types (per the
# `diamond_keeps_shared_module_once` test in lex-syntax).

import "std.float" as float
import "std.int"   as int


# ---- types -----------------------------------------------------

type DataStatus = Available | Skipped | Unavailable
type Grade      = Platinum | Gold | Silver | Bronze | Fail
type Band       = Low | Medium | High | NA
type RepoType   = Implementation | Proposal


type Technical = {
  score       :: Float,
  data_status :: DataStatus,
}

type Business = {
  score                     :: Float,
  data_status               :: DataStatus,
  problem_clarity           :: Float,
  differentiation           :: Float,
  intellectual_contribution :: Float,
  market_signals            :: Float,
  execution_vs_ambition     :: Float,
}

type Community = {
  score       :: Float,
  data_status :: DataStatus,
}

type Report = {
  repo_type :: RepoType,
  technical :: Technical,
  business  :: Business,
  community :: Community,
}

type Verdict = {
  code           :: Str,
  label          :: Str,
  one_liner      :: Str,
  idea_band      :: Band,
  execution_band :: Band,
  relevance_band :: Band,
}

type Bands = {
  idea      :: Band,
  execution :: Band,
  relevance :: Band,
}

type Outcome = {
  score :: Float,
  grade :: Grade,
}


# ---- scoring ---------------------------------------------------

fn w_technical() -> Float { 0.40 }
fn w_business()  -> Float { 0.35 }
fn w_community() -> Float { 0.25 }


fn is_available(s :: DataStatus) -> Bool {
  match s { Available => true, _ => false }
}

fn is_skipped(s :: DataStatus) -> Bool {
  match s { Skipped => true, _ => false }
}


fn skipped_weight(r :: Report) -> Float {
  let t := if is_skipped(r.technical.data_status) { w_technical() } else { 0.0 }
  let b := if is_skipped(r.business.data_status)  { w_business()  } else { 0.0 }
  let c := if is_skipped(r.community.data_status) { w_community() } else { 0.0 }
  t + b + c
}

fn weighted_sum(r :: Report) -> Float {
  let t := if is_available(r.technical.data_status) {
             r.technical.score * w_technical()
           } else { 0.0 }
  let b := if is_available(r.business.data_status) {
             r.business.score * w_business()
           } else { 0.0 }
  let c := if is_available(r.community.data_status) {
             r.community.score * w_community()
           } else { 0.0 }
  t + b + c
}

fn n_available(r :: Report) -> Int {
  let t := if is_available(r.technical.data_status) { 1 } else { 0 }
  let b := if is_available(r.business.data_status)  { 1 } else { 0 }
  let c := if is_available(r.community.data_status) { 1 } else { 0 }
  t + b + c
}


# floor(x * 10 + 0.5) / 10 — sidesteps a float.round dependency.
fn round1(x :: Float) -> Float {
  int.to_float(float.to_int(x * 10.0 + 0.5)) / 10.0
}

# Fewer than 2 axes of evidence is calibration noise. Cap at Bronze.
fn grade_for(overall :: Float, n :: Int) -> Grade {
  if n < 2 {
    if overall >= 40.0 { Bronze } else { Fail }
  } else {
    if overall >= 90.0 {
      if n >= 3 { Platinum } else { Gold }
    } else {
      if overall >= 75.0 { Gold }
      else {
        if overall >= 60.0 { Silver }
        else {
          if overall >= 40.0 { Bronze } else { Fail }
        }
      }
    }
  }
}


fn compute_overall(r :: Report) -> Outcome {
  let n := n_available(r)
  if n == 0 {
    { score: 0.0, grade: Fail }
  } else {
    let denom   := 1.0 - skipped_weight(r)
    let raw     := weighted_sum(r) / denom
    let rounded := round1(raw)
    { score: rounded, grade: grade_for(rounded, n) }
  }
}


# ---- verdict ---------------------------------------------------

fn band_of(score :: Float) -> Band {
  if score >= 70.0 { High }
  else {
    if score >= 40.0 { Medium } else { Low }
  }
}


fn idea_score(r :: Report) -> Float {
  let pc := r.business.problem_clarity
  let di := r.business.differentiation
  let ic := r.business.intellectual_contribution
  if ic > 0.0 {
    (pc + di + ic) / 3.0
  } else {
    (pc + di) / 2.0
  }
}

fn execution_score(r :: Report) -> Float {
  match r.repo_type {
    Proposal       => (r.business.execution_vs_ambition + r.community.score) / 2.0,
    Implementation => r.technical.score,
  }
}

fn relevance_score(r :: Report) -> Float {
  (r.business.market_signals + r.community.score) / 2.0
}


fn idea_has_data(r :: Report) -> Bool {
  is_available(r.business.data_status)
}

fn execution_has_data(r :: Report) -> Bool {
  match r.repo_type {
    Proposal       => is_available(r.business.data_status)
                      and is_available(r.community.data_status),
    Implementation => is_available(r.technical.data_status),
  }
}

fn relevance_has_data(r :: Report) -> Bool {
  is_available(r.community.data_status)
}

fn band_or_na(has_data :: Bool, score :: Float) -> Band {
  if has_data { band_of(score) } else { NA }
}

fn axes_with_data(r :: Report) -> Int {
  let i := if idea_has_data(r)      { 1 } else { 0 }
  let e := if execution_has_data(r) { 1 } else { 0 }
  let v := if relevance_has_data(r) { 1 } else { 0 }
  i + e + v
}


fn mk(code :: Str, label :: Str, one_liner :: Str, b :: Bands) -> Verdict {
  {
    code:           code,
    label:          label,
    one_liner:      one_liner,
    idea_band:      b.idea,
    execution_band: b.execution,
    relevance_band: b.relevance,
  }
}

fn pass_verdict(b :: Bands) -> Verdict {
  mk("pass", "Pass", "Not enough signal on any axis. Pass.", b)
}

# Verdict matrix as nested matches per axis. Record-pattern matching
# directly on a nominal type isn't accepted yet (lex emits
# `expected record, got core.Bands` — the #86 record-coercion fix
# covers literals/let/args but not destructure patterns).
fn verdict_high(b :: Bands) -> Verdict {
  match b.execution {
    High => match b.relevance {
      High   => mk("bet-on-it", "Bet on it",
                   "Good idea, good execution, real demand. Adopt, contribute, or invest.", b),
      Medium => mk("bet-on-it", "Bet on it",
                   "Good idea, good execution, growing demand. Adopt or contribute.", b),
      Low    => mk("ahead-of-its-time", "Ahead of its time",
                   "Brilliant work without a market yet. Track it; don't bet today.", b),
      _      => pass_verdict(b),
    },
    Low => match b.relevance {
      High   => mk("worth-helping", "Worth helping",
                   "Good idea with weak execution and clear demand. Contribute, fork, or fund.", b),
      Medium => mk("worth-helping", "Worth helping",
                   "Good idea, early execution. High risk but big upside.", b),
      _      => pass_verdict(b),
    },
    Medium => match b.relevance {
      Medium => mk("promising-prototype", "Promising prototype",
                   "Solid idea, execution halfway there. Revisit in 3 months.", b),
      Low    => mk("promising-prototype", "Promising prototype",
                   "Good idea executing OK but no visible demand yet.", b),
      _      => pass_verdict(b),
    },
    _ => pass_verdict(b),
  }
}

fn verdict_low(b :: Bands) -> Verdict {
  match b.execution {
    High => match b.relevance {
      High   => mk("solid-commodity", "Solid commodity",
                   "Real problem, good execution, no differentiation. Adopt if needed; no upside.", b),
      Medium => mk("solid-commodity", "Solid commodity",
                   "Good execution of a known problem. Useful, not novel.", b),
      Low    => mk("skill-in-search", "Skill in search of a problem",
                   "Strong builder solving an irrelevant problem. Talent reusable; project isn't.", b),
      _      => pass_verdict(b),
    },
    _ => pass_verdict(b),
  }
}

fn verdict_medium(b :: Bands) -> Verdict {
  match b.execution {
    Low => match b.relevance {
      Low => mk("incomplete-thesis", "Incomplete thesis",
                "Not enough signal. Come back when there's more code or traction.", b),
      _   => pass_verdict(b),
    },
    Medium => match b.relevance {
      Medium => mk("promising-prototype", "Promising prototype",
                   "Everything halfway. If you like the space, it's worth following.", b),
      _      => pass_verdict(b),
    },
    _ => pass_verdict(b),
  }
}

fn verdict_for(b :: Bands) -> Verdict {
  match b.idea {
    High   => verdict_high(b),
    Low    => verdict_low(b),
    Medium => verdict_medium(b),
    NA     => pass_verdict(b),
  }
}


fn compute_verdict(r :: Report) -> Verdict {
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
