# Ingestion — pure pieces of `rubric/ingestion.py`.
#
# Side-effect-free portion only — the io / fs_walk port lives in
# `ingestion_io.lex` so that the pure cross-check stays pure (lex's
# effect checker treats the whole file's surface as the envelope).
#
# Exposed for the cross-check bridge:
#   parse_github_url(url)        -> Option[(Str, Str)]
#   parse_gist_url(url)          -> Option[(Str, Str)]
#   language_for_ext(ext)        -> Str   ("Unknown" if unknown)
#   classify_repo_type_pure(loc :: Int, doc_chars :: Int,
#                           has_remote_traction :: Bool) -> (Str, Str)
#   cross_check_ingest(url, loc, doc_chars, has_traction)
#                                -> { ... record }

import "std.regex" as regex
import "std.list"  as list
import "std.str"   as str
import "std.int"   as int


# --- URL parsers (pure) ------------------------------------------

# Compile + match in one shot; returns (group1, group2) when both
# groups are present. Compiled regex isn't exported as a named type,
# so the helper takes the pattern string and inlines compile+find.
fn _match2(pattern :: Str, url :: Str) -> Option[(Str, Str)] {
  match regex.compile(pattern) {
    Err(_) => None,
    Ok(re) => match regex.find(re, url) {
      None    => None,
      Some(m) => match list.head(m.groups) {
        None    => None,
        Some(a) => match list.head(list.tail(m.groups)) {
          None    => None,
          Some(b) => Some((a, b)),
        },
      },
    },
  }
}

fn parse_github_url(url :: Str) -> Option[(Str, Str)] {
  let trimmed := str.trim(url)
  # Strict pattern: rejects dots in the repo segment, trims `.git`.
  match _match2("github\\.com[:/]([^/]+)/([^/.]+?)(?:\\.git)?/?$", trimmed) {
    Some(p) => Some(p),
    # Permissive fallback: allows dots in the repo segment.
    None    => _match2("github\\.com[:/]([^/]+)/([^/]+?)/?$", trimmed),
  }
}

fn parse_gist_url(url :: Str) -> Option[(Str, Str)] {
  _match2("gist\\.github\\.com[:/]([^/]+)/([0-9a-f]+)", str.trim(url))
}


# --- extension → language map (pure) ------------------------------

fn _ext_table() -> List[(Str, Str)] {
  [
    (".py",    "Python"),
    (".js",    "JavaScript"),
    (".jsx",   "JavaScript"),
    (".ts",    "TypeScript"),
    (".tsx",   "TypeScript"),
    (".rs",    "Rust"),
    (".go",    "Go"),
    (".java",  "Java"),
    (".kt",    "Kotlin"),
    (".rb",    "Ruby"),
    (".php",   "PHP"),
    (".cs",    "C#"),
    (".cpp",   "C++"),
    (".cc",    "C++"),
    (".c",     "C"),
    (".h",     "C"),
    (".swift", "Swift"),
  ]
}

fn language_for_ext(ext :: Str) -> Str {
  let e := str.to_lower(ext)
  list.fold(_ext_table(), "Unknown",
    fn (acc :: Str, p :: (Str, Str)) -> Str {
      match p {
        (k, v) => if acc == "Unknown" and k == e { v } else { acc },
      }
    })
}


# --- classify_repo_type (pure variant) ----------------------------
#
# Decoupled from filesystem so the lex side can cross-check the
# decision logic without duplicating the doc-chars probe. The
# orchestrator (Python today, lex tomorrow) computes doc_chars from
# the repo and feeds it in.
#
# Heuristic mirrors `rubric/ingestion.py::classify_repo_type`:
#   - LOC ≥ 500 → implementation.
#   - Otherwise, doc_chars ≥ 5K AND (has_remote_traction OR loc < 50)
#     → proposal.
#   - Else → implementation.

fn classify_repo_type_pure(
  loc :: Int, doc_chars :: Int, has_remote_traction :: Bool,
) -> (Str, Str) {
  if loc >= 500 {
    ("implementation",
     str.concat(int.to_str(loc), " LOC indicates a code artifact"))
  } else {
    if doc_chars >= 5000 and (has_remote_traction or loc < 50) {
      ("proposal",
       str.concat(
         str.concat(int.to_str(loc), " LOC + "),
         str.concat(int.to_str(doc_chars), " chars of docs suggest a spec artifact")
       ))
    } else {
      ("implementation", "code present, doesn't look like a pure spec")
    }
  }
}


# --- cross-check entry point -------------------------------------
# Single subprocess invocation gets every pure-ingestion signal back.
# The four `*_*` string fields hold "" when the parser didn't match.

fn cross_check_ingest(
  url :: Str, loc :: Int, doc_chars :: Int, has_traction :: Bool,
) -> {
  github_owner   :: Str,
  github_repo    :: Str,
  gist_owner     :: Str,
  gist_id        :: Str,
  classified     :: Str,
  reason         :: Str,
} {
  let gh := match parse_github_url(url) {
    Some((o, r)) => (o, r),
    None         => ("", ""),
  }
  let gi := match parse_gist_url(url) {
    Some((o, r)) => (o, r),
    None         => ("", ""),
  }
  let cls := classify_repo_type_pure(loc, doc_chars, has_traction)
  match (gh, gi, cls) {
    ((gho, ghr), (gio, gir), (rt, rs)) => {
      github_owner: gho,
      github_repo:  ghr,
      gist_owner:   gio,
      gist_id:      gir,
      classified:   rt,
      reason:       rs,
    },
  }
}
