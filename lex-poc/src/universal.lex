# Universal technical-pillar detectors — pilot port from
# `rubric/technical/universal.py`.
#
# Validates the boundary cost for fs-touching code:
#   - exercises std.fs.exists (gated by [fs_walk])
#   - exercises std.io.read (gated by [io])
#   - exercises std.str (pure)
# Together with the required scope flags, lex enforces this code can
# only read the repo path it was given — the type system + runtime
# gate are doing real work.
#
# Surface today:
#   detect_license(repo)          -> [fs_walk, io] Str   # "MIT" | "Apache-2.0" | ...
#   detect_security_md(repo)      -> [fs_walk] Bool
#   cross_check_universal(repo)   -> [fs_walk, io] { license, has_security_md }

import "std.fs"  as fs
import "std.io"  as io
import "std.str" as str


# --- license classification (pure) -------------------------------

fn classify(content :: Str) -> Str {
  let head := str.to_upper(str.slice(content, 0, 500))
  let head_short := str.slice(head, 0, 200)
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


# --- cross-check entry point -------------------------------------
# One subprocess invocation gets both signals in a single JSON object.

fn cross_check_universal(repo :: Str) -> [fs_walk, io] { license :: Str, has_security_md :: Bool } {
  {
    license:         detect_license(repo),
    has_security_md: detect_security_md(repo),
  }
}
