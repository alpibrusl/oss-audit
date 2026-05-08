# HN source — pure half. Port of `rubric/sources/hn.py::_extract_gh_url`.
#
# The `[net]` half (HN API fetcher) lives in `hn_source_net.lex`;
# splitting keeps the cross-check pure (lex's effect checker treats
# the whole file's surface as the envelope).
#
# The full `fetch_hn_candidates` orchestrator (60+ item-by-item
# requests) stays in Python until the candidate CLI moves to lex —
# no audit-time pressure to port it sooner.

import "std.regex" as regex
import "std.list"  as list
import "std.str"   as str


# --- pure URL extraction ------------------------------------------

fn _gh_pattern() -> Str {
  # Matches github.com / gist.github.com / www.github.com prefixes.
  # `[\w./-]+` mirrors Python's character class.
  "https?://(?:www\\.)?(?:github\\.com|gist\\.github\\.com)/[\\w./-]+"
}

# Trim a few trailing punctuation characters HN bodies often leave on URLs.
fn _trim_trailing(s :: Str) -> Str {
  let trailers := [".", ",", ";", ")", "\"", "'"]
  list.fold(trailers, s,
    fn (acc :: Str, t :: Str) -> Str {
      match str.strip_suffix(acc, t) {
        Some(rest) => rest,
        None       => acc,
      }
    })
}

# After stripping scheme, the host is in parts[0] and we need at
# least owner/repo (parts[1] and parts[2] non-empty) to call it a
# repo URL — filters out e.g. `github.com/sponsors/x`.
fn _looks_like_repo_url(url :: Str) -> Bool {
  let stripped := match str.strip_prefix(url, "https://") {
    Some(s) => s,
    None    => match str.strip_prefix(url, "http://") {
      Some(s) => s,
      None    => url,
    },
  }
  let parts := str.split(stripped, "/")
  if list.len(parts) < 3 { false }
  else {
    match list.head(parts) {
      None    => false,
      Some(h) => h == "github.com" or h == "gist.github.com" or h == "www.github.com",
    }
  }
}

# Python's `_extract_gh_url(item)` searches the `url` field first,
# then the `text` field. Each is a string (or empty if absent) — we
# accept them as separate args so the function stays pure.
fn extract_gh_url(item_url :: Str, item_text :: Str) -> Option[Str] {
  match regex.compile(_gh_pattern()) {
    Err(_) => None,
    Ok(re) => {
      let from_url := match regex.find(re, item_url) {
        None    => None,
        Some(m) => Some(_trim_trailing(m.text)),
      }
      match from_url {
        Some(u) => if _looks_like_repo_url(u) { Some(u) } else { None },
        None    => match regex.find(re, item_text) {
          None    => None,
          Some(m) => {
            let candidate := _trim_trailing(m.text)
            if _looks_like_repo_url(candidate) { Some(candidate) } else { None }
          },
        },
      }
    },
  }
}



# --- cross-check entry ----------------------------------------

# `match_url` returns "" when there's no match, so the bridge can
# diff a single string per side.
fn cross_check_extract_gh_url(
  item_url :: Str, item_text :: Str,
) -> { match_url :: Str } {
  match extract_gh_url(item_url, item_text) {
    None    => { match_url: "" },
    Some(u) => { match_url: u },
  }
}
