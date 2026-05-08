# Technical pillar scoring — pure port of the scoring half of
# `rubric/technical/runner.py::audit_technical`.
#
# Calibration-sensitive: this is where threshold tweaks land
# ("count fuzz tests as 3 points instead of 2", etc.). Cross-checking
# Python's score against the lex port catches drift between the two
# implementations whenever one is updated without the other.
#
# The signals record below mirrors the values Python computes from
# universal_checks + lang_runners + composability before adding them
# to the score. Pure: no fs / no proc / no net. The Python side gathers
# them and feeds the same inputs to both implementations.
#
# Exposed entry points:
#   score_technical(signals)                    -> Float   (0-100)
#   cross_check_tech_score(signals)             -> { score :: Float }
#
# The *cap* at 100.0 + the round-to-1-decimal mirror Python's
# `min(round(score, 1), 100.0)`.

import "std.float" as float
import "std.int"   as int


type TechSignals = {
  has_tests             :: Bool,
  test_density          :: Float,
  has_fuzz_tests        :: Bool,
  has_property_tests    :: Bool,
  has_ci                :: Bool,
  secrets_count         :: Int,
  total_vulns           :: Int,
  total_lint_warnings   :: Int,
  total_lint_errors     :: Int,
  has_security_policy   :: Bool,
  has_license           :: Bool,
  comp_score            :: Float,
  tools_run_count       :: Int,
}


# --- per-axis scoring (each piece returns its raw point award) ---

# Tests presence: 8
fn _score_tests(s :: TechSignals) -> Float {
  if s.has_tests { 8.0 } else { 0.0 }
}

# Test density: 0-4 (test_files / source_files)
fn _score_density(s :: TechSignals) -> Float {
  let d := s.test_density
  if d >= 0.5  { 4.0 }
  else { if d >= 0.25 { 3.0 }
  else { if d >= 0.10 { 2.0 }
  else { if d >= 0.05 { 1.0 }
  else { 0.0 } } } }
}

# Fuzz / property tests: 3 (fuzz) + 2 (property)
fn _score_fuzz_property(s :: TechSignals) -> Float {
  let f := if s.has_fuzz_tests     { 3.0 } else { 0.0 }
  let p := if s.has_property_tests { 2.0 } else { 0.0 }
  f + p
}

# CI: 10
fn _score_ci(s :: TechSignals) -> Float {
  if s.has_ci { 10.0 } else { 0.0 }
}

# Secrets: 20 / 10 / 0
fn _score_secrets(s :: TechSignals) -> Float {
  if s.secrets_count == 0 { 20.0 }
  else { if s.secrets_count <= 2 { 10.0 } else { 0.0 } }
}

# Vulnerabilities: 20 / 12 / 5 / 0
fn _score_vulns(s :: TechSignals) -> Float {
  let v := s.total_vulns
  if v == 0 { 20.0 }
  else { if v <= 3  { 12.0 }
  else { if v <= 10 { 5.0  }
  else { 0.0 } } }
}

# Lint: 15 / 10 / 5 / 0 (errors-block-points then warning thresholds)
fn _score_lint(s :: TechSignals) -> Float {
  if s.total_lint_errors == 0 and s.total_lint_warnings < 20 {
    15.0
  } else {
    if s.total_lint_errors == 0 and s.total_lint_warnings < 100 {
      10.0
    } else {
      if s.total_lint_errors == 0 { 5.0 } else { 0.0 }
    }
  }
}

# Security policy: 5
fn _score_secpol(s :: TechSignals) -> Float {
  if s.has_security_policy { 5.0 } else { 0.0 }
}

# License: 5
fn _score_license(s :: TechSignals) -> Float {
  if s.has_license { 5.0 } else { 0.0 }
}

# Tools-coverage bonus: min(tools * 2, 5)
fn _score_coverage_bonus(s :: TechSignals) -> Float {
  let raw := int.to_float(s.tools_run_count) * 2.0
  if raw >= 5.0 { 5.0 } else { raw }
}


# --- aggregator -------------------------------------------------

fn score_technical(s :: TechSignals) -> Float {
  let raw := _score_tests(s)
    + _score_density(s)
    + _score_fuzz_property(s)
    + _score_ci(s)
    + _score_secrets(s)
    + _score_vulns(s)
    + _score_lint(s)
    + _score_secpol(s)
    + _score_license(s)
    + s.comp_score
    + _score_coverage_bonus(s)
  let rounded := _round1(raw)
  if rounded >= 100.0 { 100.0 } else { rounded }
}

fn _round1(x :: Float) -> Float {
  # `round(x, 1)` semantics — multiply by 10, round to nearest, divide.
  # Negative inputs aren't expected (no axis subtracts), but handle them
  # symmetrically to avoid surprise.
  let scaled := x * 10.0
  let bumped := if scaled >= 0.0 { scaled + 0.5 } else { scaled - 0.5 }
  let i := float.to_int(bumped)
  int.to_float(i) / 10.0
}


# --- cross-check entry ------------------------------------------

fn cross_check_tech_score(s :: TechSignals) -> { score :: Float } {
  { score: score_technical(s) }
}
