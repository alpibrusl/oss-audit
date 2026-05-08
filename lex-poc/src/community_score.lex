# Community pillar scoring — pure port of the scoring halves of
# `rubric/community/github_metrics.py` (public mode) and
# `rubric/community/internal_metrics.py` (private mode).
#
# Same calibration-sensitive surface as tech_score.lex: this is
# where threshold tweaks land. Cross-checking catches drift between
# the two implementations whenever one is updated without the other.
#
# Bus factor is intentionally NOT a score lever — Python surfaces it
# as a contextual finding only. The lex port mirrors that decision.
#
# Exposed entry points:
#   score_community_public(signals)             -> Float
#   score_community_internal(signals)           -> Float
#   cross_check_community_score_public(signals) -> { score :: Float }
#   cross_check_community_score_internal(signals) -> { score :: Float }

import "std.float" as float
import "std.int"   as int


type CommunityPublicSignals = {
  stars                    :: Int,
  commits_90d              :: Int,
  contributors_count       :: Int,
  last_commit_days         :: Option[Int],
  agent_readiness_score    :: Int,
  has_releases             :: Bool,
  avg_issue_close_days     :: Option[Float],
}

type CommunityInternalSignals = {
  n_commits_90d            :: Int,
  contributors_total       :: Int,
  last_commit_days         :: Option[Int],
  has_codeowners           :: Bool,
  has_contributing         :: Bool,
  has_pr_template          :: Bool,
  has_adrs                 :: Bool,
  has_runbooks             :: Bool,
  agent_readiness_score    :: Int,
}


# --- shared helpers ---------------------------------------------

fn _round1(x :: Float) -> Float {
  let scaled := x * 10.0
  let bumped := if scaled >= 0.0 { scaled + 0.5 } else { scaled - 0.5 }
  let i := float.to_int(bumped)
  int.to_float(i) / 10.0
}

fn _cap_100(x :: Float) -> Float {
  if x >= 100.0 { 100.0 } else { x }
}

# Velocity tier shared by both modes (same thresholds: 50/15/3 → 25/18/10).
fn _score_velocity(commits_90d :: Int) -> Float {
  if commits_90d >= 50 { 25.0 }
  else { if commits_90d >= 15 { 18.0 }
  else { if commits_90d >= 3  { 10.0 }
  else { 0.0 } } }
}

# Recency tier shared by both modes (14/60/180 days → 15/9/4).
fn _score_recency(last_commit_days :: Option[Int]) -> Float {
  match last_commit_days {
    None => 0.0,
    Some(d) =>
      if d <= 14  { 15.0 }
      else { if d <= 60  { 9.0 }
      else { if d <= 180 { 4.0 }
      else { 0.0 } } },
  }
}


# --- public-mode (GitHub API path) -------------------------------

# Adoption (stars): 25 / 20 / 15 / 8 / clamped-stars-as-points
fn _score_stars(stars :: Int) -> Float {
  if stars >= 1000 { 25.0 }
  else { if stars >= 100 { 20.0 }
  else { if stars >= 25  { 15.0 }
  else { if stars >= 5   { 8.0 }
  else {
    # `max(stars, 0)` in Python — clamp negative just in case.
    if stars < 0 { 0.0 } else { int.to_float(stars) }
  } } } }
}

# Velocity-per-author (AI-era signal): 5 / 3 / 1
fn _score_cpa(commits_90d :: Int, contributors :: Int) -> Float {
  let denom :: Int := if contributors == 0 { 1 } else { contributors }
  let cpa   :: Float := int.to_float(commits_90d) / int.to_float(denom)
  # Python guards `if contributors_count else 0.0` — so 0-contrib repos
  # produce 0 CPA. Mirror that by short-circuiting here.
  if contributors == 0 { 0.0 }
  else {
    if cpa >= 30.0 { 5.0 }
    else { if cpa >= 15.0 { 3.0 }
    else { if cpa >= 5.0  { 1.0 }
    else { 0.0 } } }
  }
}

# Contributor diversity (public): 10 / 6 / 3 (thresholds 20 / 5 / 2)
fn _score_diversity_public(contributors :: Int) -> Float {
  if contributors >= 20 { 10.0 }
  else { if contributors >= 5 { 6.0 }
  else { if contributors >= 2 { 3.0 }
  else { 0.0 } } }
}

fn _score_releases(has :: Bool) -> Float {
  if has { 5.0 } else { 0.0 }
}

# Issue close time: 5 (≤7d) / 3 (≤30d) / 0
fn _score_close_time(avg :: Option[Float]) -> Float {
  match avg {
    None => 0.0,
    Some(d) =>
      if d <= 7.0  { 5.0 }
      else { if d <= 30.0 { 3.0 } else { 0.0 } },
  }
}

fn score_community_public(s :: CommunityPublicSignals) -> Float {
  let raw := _score_stars(s.stars)
    + _score_velocity(s.commits_90d)
    + _score_cpa(s.commits_90d, s.contributors_count)
    + _score_recency(s.last_commit_days)
    + int.to_float(s.agent_readiness_score)
    + _score_diversity_public(s.contributors_count)
    + _score_releases(s.has_releases)
    + _score_close_time(s.avg_issue_close_days)
  _cap_100(_round1(raw))
}


# --- private-mode (local clone path) -----------------------------

# Contributor diversity (private): 15 / 10 / 5 (thresholds 10 / 4 / 2)
# Different from public — internal repos are typically smaller teams.
fn _score_diversity_internal(contributors :: Int) -> Float {
  if contributors >= 10 { 15.0 }
  else { if contributors >= 4 { 10.0 }
  else { if contributors >= 2 { 5.0 }
  else { 0.0 } } }
}

# Process docs: 5 each, total 25
fn _score_process_docs(s :: CommunityInternalSignals) -> Float {
  let a := if s.has_codeowners   { 5.0 } else { 0.0 }
  let b := if s.has_contributing { 5.0 } else { 0.0 }
  let c := if s.has_pr_template  { 5.0 } else { 0.0 }
  let d := if s.has_adrs         { 5.0 } else { 0.0 }
  let e := if s.has_runbooks     { 5.0 } else { 0.0 }
  a + b + c + d + e
}

fn score_community_internal(s :: CommunityInternalSignals) -> Float {
  let raw := _score_velocity(s.n_commits_90d)
    + _score_recency(s.last_commit_days)
    + _score_diversity_internal(s.contributors_total)
    + _score_process_docs(s)
    + int.to_float(s.agent_readiness_score)
  _cap_100(_round1(raw))
}


# --- cross-check entry points ------------------------------------

fn cross_check_community_score_public(
  s :: CommunityPublicSignals,
) -> { score :: Float } {
  { score: score_community_public(s) }
}

fn cross_check_community_score_internal(
  s :: CommunityInternalSignals,
) -> { score :: Float } {
  { score: score_community_internal(s) }
}
