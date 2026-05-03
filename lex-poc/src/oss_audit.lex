# OSS Auditor scoring + verdict, in lex.
#
# Pure functional port of the rubric-critical core:
#   - oss_auditor/reporter/scorer.py::compute_overall
#   - oss_auditor/reporter/verdict.py::compute_verdict
#
# Everything is effect-free except `main`, which prints to stdout.
# Local imports between .lex files aren't a thing yet, so the whole
# POC lives in one module.

import "std.io"    as io
import "std.str"   as str
import "std.int"   as int
import "std.float" as float


# ---- types -----------------------------------------------------

type DataStatus = Available | Skipped | Unavailable
type Grade      = Platinum | Gold | Silver | Bronze | Fail
type Band       = Low | Medium | High | NA
type RepoType   = Implementation | Proposal

# Field order in type defs must match what lex's inference normalizes
# record literals to (alphabetical), otherwise the type checker rejects
# `{ ... } :: NominalType` shaped values.

type Technical = {
  data_status :: DataStatus,
  score       :: Float,
}

type Business = {
  data_status               :: DataStatus,
  differentiation           :: Float,
  execution_vs_ambition     :: Float,
  intellectual_contribution :: Float,
  market_signals            :: Float,
  problem_clarity           :: Float,
  score                     :: Float,
}

type Community = {
  data_status :: DataStatus,
  score       :: Float,
}

type Report = {
  business  :: Business,
  community :: Community,
  repo_type :: RepoType,
  technical :: Technical,
}

type Verdict = {
  code           :: Str,
  execution_band :: Band,
  idea_band      :: Band,
  label          :: Str,
  one_liner      :: Str,
  relevance_band :: Band,
}

type Bands = {
  execution :: Band,
  idea      :: Band,
  relevance :: Band,
}

type Outcome = {
  grade :: Grade,
  score :: Float,
}


# ---- constructors ----------------------------------------------
# Lex coerces anonymous record literals to nominal types only at
# function-return boundaries. Wrapping each literal in a `mk_*`
# function makes the coercion explicit and reusable.

fn mk_technical(score :: Float, ds :: DataStatus) -> Technical {
  { data_status: ds, score: score }
}

fn mk_business(
  score :: Float, ds :: DataStatus,
  pc :: Float, di :: Float, ic :: Float, ms :: Float, eva :: Float
) -> Business {
  {
    data_status:               ds,
    differentiation:           di,
    execution_vs_ambition:     eva,
    intellectual_contribution: ic,
    market_signals:            ms,
    problem_clarity:           pc,
    score:                     score,
  }
}

fn mk_community(score :: Float, ds :: DataStatus) -> Community {
  { data_status: ds, score: score }
}

fn mk_report(
  rt :: RepoType, t :: Technical, b :: Business, c :: Community
) -> Report {
  { business: b, community: c, repo_type: rt, technical: t }
}

fn mk_bands(e :: Band, i :: Band, r :: Band) -> Bands {
  { execution: e, idea: i, relevance: r }
}

fn mk_outcome(score :: Float, grade :: Grade) -> Outcome {
  { grade: grade, score: score }
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

# floor(x * 10 + 0.5) / 10 — sidesteps any float.round dependency.
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
    mk_outcome(0.0, Fail)
  } else {
    let denom   := 1.0 - skipped_weight(r)
    let raw     := weighted_sum(r) / denom
    let rounded := round1(raw)
    mk_outcome(rounded, grade_for(rounded, n))
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
    execution_band: b.execution,
    idea_band:      b.idea,
    label:          label,
    one_liner:      one_liner,
    relevance_band: b.relevance,
  }
}

fn pass_verdict(b :: Bands) -> Verdict {
  mk("pass", "Pass", "Not enough signal on any axis. Pass.", b)
}

# Encode the band triple as a 3-char string and dispatch on that.
# Lex doesn't support record-pattern matching on nominal types, but
# string match is cheap and keeps the table readable.
fn band_char(b :: Band) -> Str {
  match b {
    Low    => "L",
    Medium => "M",
    High   => "H",
    NA     => "_",
  }
}

fn verdict_for(b :: Bands) -> Verdict {
  let key := str.concat(
    str.concat(band_char(b.idea), band_char(b.execution)),
    band_char(b.relevance)
  )
  match key {
    "HHH" => mk("bet-on-it", "Bet on it",
                "Good idea, good execution, real demand. Adopt, contribute, or invest.", b),
    "HHM" => mk("bet-on-it", "Bet on it",
                "Good idea, good execution, growing demand. Adopt or contribute.", b),
    "HLH" => mk("worth-helping", "Worth helping",
                "Good idea with weak execution and clear demand. Contribute, fork, or fund.", b),
    "HLM" => mk("worth-helping", "Worth helping",
                "Good idea, early execution. High risk but big upside.", b),
    "HMM" => mk("promising-prototype", "Promising prototype",
                "Solid idea, execution halfway there. Revisit in 3 months.", b),
    "HML" => mk("promising-prototype", "Promising prototype",
                "Good idea executing OK but no visible demand yet.", b),
    "HHL" => mk("ahead-of-its-time", "Ahead of its time",
                "Brilliant work without a market yet. Track it; don't bet today.", b),
    "LHH" => mk("solid-commodity", "Solid commodity",
                "Real problem, good execution, no differentiation. Adopt if needed; no upside.", b),
    "LHM" => mk("solid-commodity", "Solid commodity",
                "Good execution of a known problem. Useful, not novel.", b),
    "LHL" => mk("skill-in-search", "Skill in search of a problem",
                "Strong builder solving an irrelevant problem. Talent reusable; project isn't.", b),
    "MLL" => mk("incomplete-thesis", "Incomplete thesis",
                "Not enough signal. Come back when there's more code or traction.", b),
    "MMM" => mk("promising-prototype", "Promising prototype",
                "Everything halfway. If you like the space, it's worth following.", b),
    _     => pass_verdict(b),
  }
}

fn compute_verdict(r :: Report) -> Verdict {
  let bands := mk_bands(
    band_or_na(execution_has_data(r), execution_score(r)),
    band_or_na(idea_has_data(r),      idea_score(r)),
    band_or_na(relevance_has_data(r), relevance_score(r))
  )
  if axes_with_data(r) < 2 {
    mk("indeterminate", "Indeterminate",
       "Missing data on at least 2 of the 3 axes (idea / execution / relevance). Verdict suspended until there's more signal.",
       bands)
  } else {
    verdict_for(bands)
  }
}


# ---- demo runner -----------------------------------------------

fn band_label(b :: Band) -> Str {
  match b {
    High   => "high",
    Medium => "medium",
    Low    => "low",
    NA     => "n/a",
  }
}

fn grade_label(g :: Grade) -> Str {
  match g {
    Platinum => "platinum",
    Gold     => "gold",
    Silver   => "silver",
    Bronze   => "bronze",
    Fail     => "fail",
  }
}

fn make_business(score :: Float, status :: DataStatus) -> Business {
  mk_business(score, status, 80.0, 80.0, 80.0, 80.0, 80.0)
}

fn make_report(
  tech_score :: Float, tech :: DataStatus,
  biz_score  :: Float, biz  :: DataStatus,
  com_score  :: Float, com  :: DataStatus
) -> Report {
  mk_report(
    Implementation,
    mk_technical(tech_score, tech),
    make_business(biz_score, biz),
    mk_community(com_score, com)
  )
}

fn line(name :: Str, r :: Report) -> Str {
  let out := compute_overall(r)
  let v   := compute_verdict(r)
  str.join(
    [
      name, " | score=", float.to_str(out.score),
      " grade=", grade_label(out.grade),
      " verdict=", v.code,
      " bands=(idea=", band_label(v.idea_band),
      ", exec=", band_label(v.execution_band),
      ", rel=", band_label(v.relevance_band), ")"
    ],
    ""
  )
}

fn main() -> [io] Nil {
  # Polars-style: technical alone, others skipped → bronze, indeterminate.
  io.print(line(
    "only-technical",
    make_report(90.0, Available, 0.0, Skipped, 0.0, Skipped)
  ))
  # Tech + business, community skipped: 2 axes available.
  io.print(line(
    "tech+business",
    make_report(90.0, Available, 85.0, Available, 0.0, Skipped)
  ))
  # All three available, all hot → bet-on-it / gold.
  io.print(line(
    "full-3-axes",
    make_report(90.0, Available, 85.0, Available, 80.0, Available)
  ))
  # Business attempted but unavailable: penalty applies, not renormalized.
  io.print(line(
    "biz-unavailable",
    make_report(90.0, Available, 0.0, Unavailable, 80.0, Available)
  ))
}
