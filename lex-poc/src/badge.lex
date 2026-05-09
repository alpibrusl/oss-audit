# Badge generation — port of `rubric/reporter/badge.py`.
#
# Three outputs:
#   - shields.io static URL: img.shields.io/badge/<label>-<msg>-<color>
#   - shields.io endpoint payload (JSON record)
#   - Markdown snippet
#
# All pure. The shields.io escape rules are:
#   `-` → `--`  ;  `_` → `__`  ;  ` ` → `_`  ;  `/` → `%2F`
# Letters, digits, `.`, `_`, `-` need no further URL encoding for
# the inputs we emit (score-string / lens-name / grade — verified
# via Python parity).
#
# Color mapping follows the GRADE_COLOR dict — drift here would
# show up as a real disagreement.
#
# Exposed:
#   to_shields_url(score, grade, label)         -> Str
#   to_endpoint_payload(score, grade, label)    -> { ... record }
#   to_markdown(score, grade, label, link_url)  -> Str
#   cross_check_badge(score, grade, label)      -> { ... record }

import "std.float" as float
import "std.int"   as int
import "std.str"   as str


# --- color mapping -----------------------------------------------

fn _color_for(grade :: Str) -> Str {
  if grade == "platinum" { "blueviolet"  }
  else { if grade == "gold"     { "brightgreen" }
  else { if grade == "silver"   { "green"       }
  else { if grade == "bronze"   { "yellow"      }
  else { if grade == "fail"     { "red"         }
  else { "lightgrey" } } } } }
}


# --- shields escape ----------------------------------------------

fn _shields_escape(s :: Str) -> Str {
  # Order matters: dashes first, then underscores, then spaces.
  # Each replace is applied to the result of the previous.
  let s1 := str.replace(s, "-", "--")
  let s2 := str.replace(s1, "_", "__")
  let s3 := str.replace(s2, " ", "_")
  # URL-encode the only char that survives substitution and isn't
  # alphanumeric / `.` / `-` / `_` for our typical inputs: `/`.
  str.replace(s3, "/", "%2F")
}


# --- score formatting --------------------------------------------
#
# Python uses `f"{report.overall_score:.1f}"` — always one decimal,
# rounding half-to-even-ish (Python 3 default). Lex's _round1 does
# half-up; the difference matters only when the second decimal is
# exactly 5, and overall_score has already been _round1'd by the
# scorer so this is a no-op for any value the pipeline produces.

fn _format_score_1dp(score :: Float) -> Str {
  # Multiply by 10, round, format. Negative inputs aren't expected.
  let scaled := score * 10.0
  let rounded := float.to_int(scaled + 0.5)
  let whole := rounded / 10
  let frac  := rounded - whole * 10
  str.concat(str.concat(int.to_str(whole), "."), int.to_str(frac))
}


# --- public API --------------------------------------------------

fn _message(score :: Float, grade :: Str) -> Str {
  str.concat(
    str.concat(_format_score_1dp(score), "/100 "),
    grade
  )
}

fn to_shields_url(score :: Float, grade :: Str, label :: Str) -> Str {
  let color := _color_for(grade)
  let lab   := _shields_escape(label)
  let msg   := _shields_escape(_message(score, grade))
  str.concat(
    str.concat(
      str.concat("https://img.shields.io/badge/", lab),
      str.concat("-", str.concat(msg, "-"))
    ),
    color
  )
}

fn to_endpoint_payload(
  score :: Float, grade :: Str, label :: Str,
) -> {
  schemaVersion :: Int,
  label         :: Str,
  message       :: Str,
  color         :: Str,
  cacheSeconds  :: Int,
} {
  {
    schemaVersion: 1,
    label:         label,
    message:       _message(score, grade),
    color:         _color_for(grade),
    cacheSeconds:  3600,
  }
}

fn to_markdown(
  score :: Float, grade :: Str, label :: Str, link_url :: Str,
) -> Str {
  let badge := to_shields_url(score, grade, label)
  str.concat(
    str.concat("[![OSS Audit](", badge),
    str.concat(")](", str.concat(link_url, ")"))
  )
}


# --- cross-check entry ------------------------------------------
# Bundles all three outputs into a single roundtrip.

fn cross_check_badge(
  score :: Float, grade :: Str, label :: Str, link_url :: Str,
) -> {
  url      :: Str,
  message  :: Str,
  color    :: Str,
  markdown :: Str,
} {
  {
    url:      to_shields_url(score, grade, label),
    message:  _message(score, grade),
    color:    _color_for(grade),
    markdown: to_markdown(score, grade, label, link_url),
  }
}
