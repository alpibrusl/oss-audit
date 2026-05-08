# Lens-aware overall scoring — port of `rubric/reporter/lens.py` +
# `rubric/reporter/scorer.py::compute_overall(lens=...)`.
#
# The base scorer (`scorer.lex::compute_overall`) hardcodes the
# general-lens weights (0.40 / 0.35 / 0.25). When a user picks
# a perspective (`developer / cto / investor / security / maintainer`)
# the same scoring math runs with different per-pillar weights —
# remixing how technical / business / community contribute without
# changing the underlying signals.
#
# Calibration-sensitive: weight changes between Python and lex would
# drift silently today. This port adds the cross-check.
#
# The lens-guard verdict downgrade (`require_no_critical` security
# gate) lives in a separate follow-up so this PR stays focused.
#
# Exposed entry point:
#   compute_overall_with_lens(report, lens_name)        -> Outcome
#   cross_check_lens_score(report, lens_name)           -> Outcome
#
# `lens_name` accepts: general / developer / cto / investor / security / maintainer.
# Unknown names fall back to general.

import "std.float" as float
import "std.int"   as int

import "./models"  as m
import "./scorer"  as base


# --- per-lens weight tables (kept in sync with rubric/reporter/lens.py) ---

type LensWeights = {
  technical :: Float,
  business  :: Float,
  community :: Float,
}

fn weights_for(lens_name :: Str) -> LensWeights {
  if lens_name == "developer" {
    { technical: 0.55, business: 0.20, community: 0.25 }
  } else { if lens_name == "cto" {
    { technical: 0.40, business: 0.20, community: 0.40 }
  } else { if lens_name == "investor" {
    { technical: 0.20, business: 0.55, community: 0.25 }
  } else { if lens_name == "security" {
    { technical: 0.65, business: 0.10, community: 0.25 }
  } else { if lens_name == "maintainer" {
    { technical: 0.45, business: 0.15, community: 0.40 }
  } else {
    # general / unknown — default rubric weights, same as scorer.lex
    { technical: 0.40, business: 0.35, community: 0.25 }
  } } } } }
}


# --- lens-aware versions of the base scorer's helpers --------------

fn _skipped_weight(r :: m.Report, w :: LensWeights) -> Float {
  let t := if base.is_skipped(r.technical.data_status) { w.technical } else { 0.0 }
  let b := if base.is_skipped(r.business.data_status)  { w.business  } else { 0.0 }
  let c := if base.is_skipped(r.community.data_status) { w.community } else { 0.0 }
  t + b + c
}

fn _weighted_sum(r :: m.Report, w :: LensWeights) -> Float {
  let t := if base.is_available(r.technical.data_status) {
             r.technical.score * w.technical
           } else { 0.0 }
  let b := if base.is_available(r.business.data_status) {
             r.business.score * w.business
           } else { 0.0 }
  let c := if base.is_available(r.community.data_status) {
             r.community.score * w.community
           } else { 0.0 }
  t + b + c
}


# --- public API --------------------------------------------------

fn compute_overall_with_lens(
  r :: m.Report, lens_name :: Str,
) -> m.Outcome {
  let n := base.n_available(r)
  if n == 0 {
    { score: 0.0, grade: Fail }
  } else {
    let w       := weights_for(lens_name)
    let denom   := 1.0 - _skipped_weight(r, w)
    let raw     := _weighted_sum(r, w) / denom
    let rounded := base.round1(raw)
    { score: rounded, grade: base.grade_for(rounded, n) }
  }
}


# --- cross-check entry -------------------------------------------
# Returns {code, grade, score} so the Python bridge can diff against
# the lens-applied report values. `code` echoes the verdict code Python
# computes — when the lens-guard downgrade lands, this entry will
# return the post-guard code; for now it returns the base verdict
# unchanged.

fn cross_check_lens_score(
  r :: m.Report, lens_name :: Str,
) -> { grade :: Str, score :: Float } {
  let outcome := compute_overall_with_lens(r, lens_name)
  let g := match outcome.grade {
    Platinum => "platinum",
    Gold     => "gold",
    Silver   => "silver",
    Bronze   => "bronze",
    Fail     => "fail",
  }
  { grade: g, score: outcome.score }
}
