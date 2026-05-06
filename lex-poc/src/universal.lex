# Universal technical-pillar detectors — pilot port from
# `rubric/technical/universal.py` plus net-new lex-only signals.
#
# Validates the boundary cost for fs-touching code:
#   - exercises std.fs.exists / fs.list_dir (gated by [fs_walk])
#   - exercises std.io.read (gated by [io])
#   - exercises std.str (pure)
#   - exercises std.toml + std.yaml (pure, with #168's type-driven
#     missing-field validation — partial parses now produce Result::Err
#     instead of crashing at field access).
# Together with the required scope flags, lex enforces this code can
# only read the repo path it was given.
#
# Surface today:
#   detect_license(repo)        -> [fs_walk, io] Str
#   detect_security_md(repo)    -> [fs_walk] Bool
#   manifest_license(repo)      -> [fs_walk, io] Str   # NEW: parses pyproject.toml / Cargo.toml
#   ci_security_tools(repo)     -> [fs_walk, io] List[Str]  # NEW: detects security tool invocations
#   cross_check_universal(repo) -> [fs_walk, io] { ... full record }

import "std.fs"     as fs
import "std.io"     as io
import "std.str"    as str
import "std.list"   as list
import "std.regex"  as regex


# --- license classification (pure) -------------------------------

fn safe_slice(s :: Str, start :: Int, end :: Int) -> Str {
  # str.slice panics on out-of-range; clamp to actual length.
  let n := str.len(s)
  let e := if end > n { n } else { end }
  if start >= e { "" } else { str.slice(s, start, e) }
}

fn classify(content :: Str) -> Str {
  let head := str.to_upper(safe_slice(content, 0, 500))
  let head_short := safe_slice(head, 0, 200)
  if str.contains(head, "APACHE LICENSE") {
    "Apache-2.0"
  } else {
    if str.contains(head, "MIT LICENSE") {
      "MIT"
    } else {
      if str.contains(head_short, "MIT ") {
        "MIT"
      } else {
        if str.contains(head, "EUPL") {
          "EUPL-1.2"
        } else {
          if str.contains(head, "GPL") {
            "GPL"
          } else {
            if str.contains(head, "BSD") {
              "BSD"
            } else {
              "Unknown"
            }
          }
        }
      }
    }
  }
}


# --- file lookup with effect surface -----------------------------

fn try_license_at(repo :: Str, name :: Str) -> [fs_walk, io] Option[Str] {
  let p := str.concat(str.concat(repo, "/"), name)
  match fs.exists(p) {
    false => None,
    true  => match io.read(p) {
      Err(_) => None,
      Ok(c)  => Some(classify(c)),
    },
  }
}

fn detect_license(repo :: Str) -> [fs_walk, io] Str {
  match try_license_at(repo, "LICENSE") {
    Some(lic) => lic,
    None      => match try_license_at(repo, "LICENSE.md") {
      Some(lic) => lic,
      None      => match try_license_at(repo, "LICENSE.txt") {
        Some(lic) => lic,
        None      => match try_license_at(repo, "COPYING") {
          Some(lic) => lic,
          None      => "None",
        },
      },
    },
  }
}


fn detect_security_md(repo :: Str) -> [fs_walk] Bool {
  let a := fs.exists(str.concat(repo, "/SECURITY.md"))
  let b := fs.exists(str.concat(repo, "/security.md"))
  let c := fs.exists(str.concat(repo, "/.github/SECURITY.md"))
  a or b or c
}


# --- manifest-declared license (NEW) -----------------------------
#
# Extracts the declared license from pyproject.toml `[project].license`
# or Cargo.toml `[package].license`. We use std.regex over the file
# contents rather than typed `toml.parse` because lex-lang #168's
# type-driven validation only covers top-level required fields —
# nested `Inner.license` still crashes at field-access time. Regex
# is fine here: both manifest types define license only in their
# respective single section, so a content-level match is unambiguous.

fn extract_toml_license(content :: Str) -> Option[Str] {
  match regex.compile("(?m)^license\\s*=\\s*\"([^\"]+)\"") {
    Err(_) => None,
    Ok(re) => match regex.find(re, content) {
      None    => None,
      Some(m) => list.head(m.groups),
    },
  }
}

fn try_manifest(repo :: Str, name :: Str) -> [fs_walk, io] Option[Str] {
  let p := str.concat(str.concat(repo, "/"), name)
  match fs.exists(p) {
    false => None,
    true  => match io.read(p) {
      Err(_) => None,
      Ok(c)  => extract_toml_license(c),
    },
  }
}

fn manifest_license(repo :: Str) -> [fs_walk, io] Str {
  match try_manifest(repo, "pyproject.toml") {
    Some(l) => l,
    None    => match try_manifest(repo, "Cargo.toml") {
      Some(l) => l,
      None    => "None",
    },
  }
}


# --- CI security-tool detection (NEW) ----------------------------
#
# Walks .github/workflows/*.yml and detects security-tool invocations
# in the YAML body via str.contains. Doesn't structurally parse the
# workflow (most steps lack `run` or have only `uses`, and #168's
# strict-mode would reject those); content-substring is sufficient
# for tool detection and lets users see WHICH workflow file mentions
# each tool. Returns the unique tool names found, in stable order.

fn workflow_paths(repo :: Str) -> [fs_walk] List[Str] {
  # `fs.list_dir` returns full paths, not basenames — we feed those
  # directly to `io.read` below.
  let dir := str.concat(repo, "/.github/workflows")
  match fs.list_dir(dir) {
    Err(_)  => [],
    Ok(entries) => list.filter(entries, fn (e :: Str) -> Bool {
      str.ends_with(e, ".yml") or str.ends_with(e, ".yaml")
    }),
  }
}

fn read_workflow(path :: Str) -> [io] Str {
  match io.read(path) {
    Ok(c)  => c,
    Err(_) => "",
  }
}

# (tool-name, marker-substring) pairs. The substring is what we
# search for inside the workflow YAML — typically the CLI name as
# it would appear in a `run:` step or a `uses:` action reference.
fn tool_markers() -> List[(Str, Str)] {
  [
    ("cargo audit",   "cargo audit"),
    ("cargo-audit",   "cargo-audit"),
    ("pip-audit",     "pip-audit"),
    ("npm audit",     "npm audit"),
    ("yarn audit",    "yarn audit"),
    ("govulncheck",   "govulncheck"),
    ("gitleaks",      "gitleaks"),
    ("trivy",         "trivy"),
    ("snyk",          "snyk"),
    ("dependabot",    "dependabot"),
    ("codeql",        "codeql"),
    ("bandit",        "bandit"),
    ("semgrep",       "semgrep"),
  ]
}

fn ci_security_tools(repo :: Str) -> [fs_walk, io] List[Str] {
  let paths := workflow_paths(repo)
  let bodies := list.map(paths, fn (p :: Str) -> [io] Str { read_workflow(p) })
  let joined := str.join(bodies, "\n")
  let lower  := str.to_lower(joined)
  list.fold(tool_markers(), [], fn (acc :: List[Str], pair :: (Str, Str)) -> List[Str] {
    match pair {
      (label, marker) =>
        if str.contains(lower, marker) {
          list.concat(acc, [label])
        } else {
          acc
        },
    }
  })
}


# --- cross-check entry point -------------------------------------
# One subprocess invocation gets every signal in a single JSON object.

fn cross_check_universal(repo :: Str) -> [fs_walk, io] {
  license            :: Str,
  has_security_md    :: Bool,
  manifest_license   :: Str,
  ci_security_tools  :: List[Str],
} {
  {
    license:           detect_license(repo),
    has_security_md:   detect_security_md(repo),
    manifest_license:  manifest_license(repo),
    ci_security_tools: ci_security_tools(repo),
  }
}
