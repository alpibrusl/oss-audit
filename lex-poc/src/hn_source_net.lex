# HN source — `[net]` half. Lives in its own file because lex's
# effect checker treats the whole file's surface as the envelope:
# putting these next to the pure URL extractor in `hn_source.lex`
# would force every caller to grant `[net]`.
#
# Minimal probe that validates the std.http surface end-to-end —
# the bigger candidate fetcher (60+ item-by-item requests) stays in
# Python until the candidate CLI moves to lex.

import "std.http" as http
import "std.list" as list
import "std.str"  as str


fn _int_to_str(n :: Int) -> Str {
  if n == 0 { "0" }
  else {
    if n < 10 {
      if n == 1 { "1" } else {
        if n == 2 { "2" } else {
          if n == 3 { "3" } else {
            if n == 4 { "4" } else {
              if n == 5 { "5" } else {
                if n == 6 { "6" } else {
                  if n == 7 { "7" } else {
                    if n == 8 { "8" } else { "9" }
                  }
                }
              }
            }
          }
        }
      }
    } else {
      str.concat(_int_to_str(n / 10), _int_to_str(n - (n / 10) * 10))
    }
  }
}

fn fetch_topstory_ids(source :: Str) -> [net] Result[List[Int], Str] {
  let url := str.concat(
    str.concat("https://hacker-news.firebaseio.com/v0/", source),
    ".json")
  match http.get(url) {
    Err(e) => Err("HN API didn't respond"),
    Ok(r)  =>
      if r.status >= 200 and r.status < 300 {
        let parsed :: Result[List[Int], HttpError] := http.json_body(r)
        match parsed {
          Err(_)  => Err("HN API returned non-JSON body"),
          Ok(ids) => Ok(ids),
        }
      } else {
        Err(str.concat("HN API status ", _int_to_str(r.status)))
      },
  }
}

# Returns the count of IDs from the topstories feed — small enough
# to fit on one line of CLI output, big enough to confirm the
# network round-trip succeeded end-to-end.
fn cross_check_topstories_count() -> [net] { count :: Int, error :: Str } {
  match fetch_topstory_ids("topstories") {
    Err(e)  => { count: 0, error: e },
    Ok(ids) => { count: list.len(ids), error: "" },
  }
}
