# Per-language runner dispatch — pure port of
# `rubric/technical/lang_runners.py::run_for_languages`'s decision
# logic.
#
# Given the language-percentage breakdown ingestion produced, decide
# which runners to invoke. Calibration-sensitive: the 5% LOC threshold
# is the knob. The actual `runner(repo)` invocations + result merging
# stay in Python (those just dispatch external tools and aggregate
# their JSON output — same upstream concerns either side).
#
# Why pure: dedup happens by RUNNER FUNCTION identity in Python (so
# JavaScript and TypeScript both map to `run_js` and only fire once).
# Lex doesn't carry function identity across the bridge, but it does
# carry the canonical runner NAME which is good enough — both
# implementations agree on the resulting set of runners.
#
# Exposed:
#   should_run_for(languages, threshold_pct) -> List[Str]
#   cross_check_dispatch(languages_pcts)     -> { runners :: List[Str] }

import "std.list" as list
import "std.str"  as str


type LangPct = { name :: Str, pct :: Float }


# Map from detected language name to canonical runner name. Mirrors
# Python's `LANG_RUNNERS` dict; "JavaScript" and "TypeScript" both
# point at the same runner so they dedup naturally.
fn _runner_for(lang :: Str) -> Option[Str] {
  if lang == "Rust"        { Some("Rust")   }
  else { if lang == "Python"      { Some("Python") }
  else { if lang == "JavaScript"  { Some("JS")     }
  else { if lang == "TypeScript"  { Some("JS")     }
  else { if lang == "Go"          { Some("Go")     }
  else { None } } } } }
}


# The 5.0% threshold lives here so a tweak in either implementation
# without the other surfaces as a real cross-check disagreement.
fn _threshold_pct() -> Float { 5.0 }


# Records (not tuples) so the JSON CLI boundary stays clean: tuples
# decode as heterogeneous arrays which lex can't disambiguate from
# `List[?]` at runtime.
fn should_run_for(languages :: List[LangPct]) -> List[Str] {
  let kept := list.filter(languages,
    fn (p :: LangPct) -> Bool { p.pct >= _threshold_pct() })
  list.fold(kept, [],
    fn (acc :: List[Str], p :: LangPct) -> List[Str] {
      match _runner_for(p.name) {
        None    => acc,
        Some(r) => if _contains(acc, r) { acc } else { list.concat(acc, [r]) },
      }
    })
}

fn _contains(xs :: List[Str], target :: Str) -> Bool {
  list.fold(xs, false,
    fn (acc :: Bool, x :: Str) -> Bool { acc or x == target })
}


# --- cross-check entry -------------------------------------------

fn cross_check_dispatch(
  languages_pcts :: List[LangPct],
) -> { runners :: List[Str] } {
  { runners: should_run_for(languages_pcts) }
}
