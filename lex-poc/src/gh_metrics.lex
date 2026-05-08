# GitHub-metrics derivations — pure port of the calculations in
# `rubric/community/github_metrics.py::audit_community` that turn
# raw GitHub API responses into signals.
#
# Scope is intentionally narrow: the pure derivations only.
#   - bus_factor_top1 / bus_factor_top3 from the contributors list
#   - commits_90d from the participation feed (last 13 weeks)
#   - has_releases from the releases list
#
# Skipped:
#   - HTTP fetching itself (validated by hn_source_net.lex's std.http
#     probe — same plumbing). Not on the audit cross-check path.
#   - days_since_iso / avg_close_days. Both need a frozen "now" to
#     cross-check meaningfully; lands in a follow-up alongside a
#     std.datetime probe.
#
# Inputs are records that mirror the relevant GitHub API response
# shapes — kept slim (just the fields we read), so the bridge can
# project the API JSON down to what lex needs.

import "std.float" as float
import "std.int"   as int
import "std.list"  as list


type Contributor = { contributions :: Int }


# --- bus factor --------------------------------------------------
#
# Python iterates `sorted(contribs, key=lambda c: -c.get("contributions",0))`
# and divides top-1 / top-3 by the total. We do the same — fold the
# list to find the top-3 contribution counts, no full sort needed.

fn _round1(x :: Float) -> Float {
  let scaled := x * 10.0
  let bumped := if scaled >= 0.0 { scaled + 0.5 } else { scaled - 0.5 }
  let i := float.to_int(bumped)
  int.to_float(i) / 10.0
}

# Simple O(n) "top-3 in non-increasing order" via fold + insert.
type Top3 = { a :: Int, b :: Int, c :: Int }

fn _top3_init() -> Top3 { { a: 0, b: 0, c: 0 } }

fn _top3_insert(t :: Top3, v :: Int) -> Top3 {
  if v > t.a {
    { a: v, b: t.a, c: t.b }
  } else {
    if v > t.b {
      { a: t.a, b: v, c: t.b }
    } else {
      if v > t.c {
        { a: t.a, b: t.b, c: v }
      } else {
        t
      }
    }
  }
}

fn _total_contributions(contribs :: List[Contributor]) -> Int {
  list.fold(contribs, 0,
    fn (acc :: Int, c :: Contributor) -> Int { acc + c.contributions })
}

fn _top3_of(contribs :: List[Contributor]) -> Top3 {
  list.fold(contribs, _top3_init(),
    fn (t :: Top3, c :: Contributor) -> Top3 { _top3_insert(t, c.contributions) })
}

fn bus_factor_top1(contribs :: List[Contributor]) -> Float {
  let total := _total_contributions(contribs)
  if total <= 0 { 0.0 }
  else {
    let t := _top3_of(contribs)
    _round1(int.to_float(t.a) / int.to_float(total) * 100.0)
  }
}

fn bus_factor_top3(contribs :: List[Contributor]) -> Float {
  let total := _total_contributions(contribs)
  if total <= 0 { 0.0 }
  else {
    let t := _top3_of(contribs)
    _round1(int.to_float(t.a + t.b + t.c) / int.to_float(total) * 100.0)
  }
}


# --- commits in last 90 days -------------------------------------
# Python's `audit_community` reads `stats/participation`'s `all`
# array (52 weekly counts) and sums the last 13. <13 entries → 0.

fn commits_90d(weeks :: List[Int]) -> Int {
  let n := list.len(weeks)
  if n < 13 { 0 }
  else {
    # Take the last 13 entries via fold-with-reverse-insert.
    let rev := list.fold(weeks, [],
      fn (acc :: List[Int], w :: Int) -> List[Int] {
        list.concat([w], acc)
      })
    let last13 := _take(rev, 13)
    list.fold(last13, 0,
      fn (acc :: Int, w :: Int) -> Int { acc + w })
  }
}

fn _take(xs :: List[Int], n :: Int) -> List[Int] {
  if n <= 0 { [] } else {
    match list.head(xs) {
      None    => [],
      Some(h) => list.concat([h], _take(list.tail(xs), n - 1)),
    }
  }
}


# --- releases (trivial) ------------------------------------------

fn has_releases(releases :: List[{ id :: Int }]) -> Bool {
  list.len(releases) > 0
}


# --- cross-check entry ------------------------------------------
# Bundles the three derivations into a single roundtrip so the
# bridge does one subprocess invocation per audit.

fn cross_check_gh_metrics(
  contribs :: List[Contributor],
  weeks    :: List[Int],
  releases :: List[{ id :: Int }],
) -> {
  bus_top1     :: Float,
  bus_top3     :: Float,
  commits_90d  :: Int,
  has_releases :: Bool,
} {
  {
    bus_top1:     bus_factor_top1(contribs),
    bus_top3:     bus_factor_top3(contribs),
    commits_90d:  commits_90d(weeks),
    has_releases: has_releases(releases),
  }
}
