# Markdown report — scaffold port of `rubric/reporter/markdown.py`.
#
# Tight scope: just the "above-the-fold" scaffold (title, meta lines,
# verdict block with optional one-liner + bands + actions table).
# Skip the rest: audience-views / counterfactuals / executive summary /
# snapshot table / per-pillar findings tables / footer / etc. — those
# are deeply conditional on lens/mode/data_status and add LOC fast.
#
# Cross-check rationale:
#   The markdown layer is presentation, NOT calibration. Cross-checking
#   it surfaces formatting drift, not audit-signal drift. The value is
#   limited and the false-positive risk (trailing-whitespace,
#   decimal-precision quirks) is real. We compare byte-for-byte but
#   don't wire into the audit hot path; stand-alone test only.
#
# `audited_at` is pre-formatted by Python into the "%Y-%m-%d %H:%M UTC"
# string and passed in — keeps lex pure (no [time] effect needed) and
# avoids the std.datetime extractor gap we hit in gh-metrics.

import "std.list"  as list
import "std.str"   as str
import "std.float" as float
import "std.int"   as int


# --- inputs -----------------------------------------------------

type MdInput = {
  repo_name      :: Str,
  repo_source    :: Str,
  audited_at     :: Str,
  overall_score  :: Float,
  grade          :: Str,
  lens_name      :: Str,
  lens_label     :: Str,
  lens_desc      :: Str,
  verdict_code   :: Str,
  verdict_label  :: Str,
  verdict_one    :: Str,
  idea_band      :: Str,
  execution_band :: Str,
  relevance_band :: Str,
  action_dev     :: Str,
  action_cto     :: Str,
  action_inv     :: Str,
}


# --- helpers ----------------------------------------------------

fn _grade_emoji(grade :: Str) -> Str {
  if grade == "platinum" { "💎" }
  else { if grade == "gold"     { "🥇" }
  else { if grade == "silver"   { "🥈" }
  else { if grade == "bronze"   { "🥉" }
  else { if grade == "fail"     { "❌" }
  else { "" } } } } }
}

fn _to_upper(s :: Str) -> Str { str.to_upper(s) }

# Python's default float repr keeps `84.0` (not `84`) and trims to
# the shortest representation. For our pipeline values (always
# _round1'd, so at most one decimal of precision), this collapses to
# `<int>.<digit>` — match that exactly.
fn _format_score(score :: Float) -> Str {
  let scaled := score * 10.0
  let bumped := if scaled >= 0.0 { scaled + 0.5 } else { scaled - 0.5 }
  let rounded := float.to_int(bumped)
  let whole := rounded / 10
  let frac  := rounded - whole * 10
  str.concat(str.concat(int.to_str(whole), "."), int.to_str(frac))
}


# --- title + meta block -----------------------------------------

fn _meta_lines(i :: MdInput) -> List[Str] {
  let title := str.concat("# Audit: ", i.repo_name)
  let source := str.concat(str.concat("**Source:** `", i.repo_source), "`  ")
  let audited := str.concat(str.concat("**Audited:** ", i.audited_at), "  ")
  let emoji := _grade_emoji(i.grade)
  let score_str := _format_score(i.overall_score)
  let score_line := str.concat(
    str.concat(
      str.concat("**Overall score:** **", score_str),
      "/100** "
    ),
    str.concat(emoji, str.concat(" _", str.concat(_to_upper(i.grade), "_")))
  )
  let base := [title, "", source, audited, score_line]
  if i.lens_name == "general" {
    list.concat(base, [""])
  } else {
    let perspective := str.concat(
      str.concat(
        str.concat("**Perspective:** `", i.lens_name),
        str.concat("` — ", i.lens_label)
      ),
      str.concat(". _", str.concat(i.lens_desc, "_  "))
    )
    list.concat(base, [perspective, ""])
  }
}


# --- verdict block -----------------------------------------------

fn _verdict_heading(i :: MdInput) -> Str {
  if i.verdict_code != "" and i.verdict_code != "pass" {
    str.concat(
      str.concat("## ⚖️ Verdict: `", i.verdict_code),
      str.concat("` — ", i.verdict_label)
    )
  } else {
    str.concat(str.concat("## ⚖️ Verdict: `", i.verdict_code), "`")
  }
}

fn _bands_line(i :: MdInput) -> Str {
  str.concat(
    str.concat(
      str.concat("**Idea:** `", i.idea_band),
      str.concat("` &middot; **Execution:** `", i.execution_band)
    ),
    str.concat("` &middot; **Relevance:** `", str.concat(i.relevance_band, "`"))
  )
}

fn _actions_rows(i :: MdInput) -> List[Str] {
  let rows := []
  let r1 := if i.action_dev != "" {
    list.concat(rows, [str.concat(str.concat("| Developer | ", i.action_dev), " |")])
  } else { rows }
  let r2 := if i.action_cto != "" {
    list.concat(r1, [str.concat(str.concat("| Cto | ", i.action_cto), " |")])
  } else { r1 }
  let r3 := if i.action_inv != "" {
    list.concat(r2, [str.concat(str.concat("| Investor | ", i.action_inv), " |")])
  } else { r2 }
  r3
}

fn _verdict_lines(i :: MdInput) -> List[Str] {
  let head := [_verdict_heading(i), ""]
  let after_one := if i.verdict_one != "" {
    list.concat(head, [str.concat("> ", i.verdict_one), ""])
  } else { head }
  let with_bands := list.concat(after_one, [_bands_line(i), ""])
  let rows := _actions_rows(i)
  if list.len(rows) == 0 {
    with_bands
  } else {
    let table_head := [
      "| Audience | Action |",
      "|----------|--------|",
    ]
    list.concat(list.concat(with_bands, table_head), list.concat(rows, [""]))
  }
}


# --- public API --------------------------------------------------

fn render_scaffold(i :: MdInput) -> Str {
  let lines := list.concat(_meta_lines(i), _verdict_lines(i))
  str.join(lines, "\n")
}

fn cross_check_markdown(i :: MdInput) -> { rendered :: Str } {
  { rendered: render_scaffold(i) }
}
