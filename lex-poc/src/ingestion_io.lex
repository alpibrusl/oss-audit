# Effect-bearing half of the ingestion port.
#
# Lives in its own file because lex's effect checker treats the
# whole file's surface as the effect envelope: putting these
# functions next to the pure URL parsers would force every caller
# to grant `[fs_walk, io]` even when invoking only `parse_github_url`.
#
# Mirrors the corresponding chunks of `rubric/ingestion.py`:
#   count_lines           — non-empty lines, encoding-tolerant
#   detect_languages      — walk + filter + per-lang LOC
#   doc_chars             — README + docs/*.md byte total
#   classify_repo_type    — io wrapper around classify_repo_type_pure
#   cross_check_ingest_io — single-roundtrip cross-check

import "std.fs"    as fs
import "std.io"    as io
import "std.list"  as list
import "std.str"   as str
import "std.int"   as int
import "std.float" as float

import "./ingestion" as ing


# --- ignored-dir filter ------------------------------------------

fn _ignore_dirs() -> List[Str] {
  [
    ".git", "node_modules", "target", "dist", "build", "__pycache__",
    ".venv", "venv", ".tox", ".pytest_cache", ".mypy_cache", ".cargo",
    "vendor", ".idea", ".vscode", "out",
  ]
}

fn _is_ignored_segment(name :: Str) -> Bool {
  if str.starts_with(name, ".") {
    # Dotted dirs are skipped wholesale, matching Python's
    # `not d.startswith(".")` filter — IGNORE_DIRS still lists a
    # few dotted entries (`.git`, `.venv`, …) for clarity.
    true
  } else {
    list.fold(_ignore_dirs(), false,
      fn (acc :: Bool, d :: Str) -> Bool { acc or d == name })
  }
}

fn _strip_prefix(s :: Str, prefix :: Str) -> Str {
  match str.strip_prefix(s, prefix) {
    Some(rest) => rest,
    None       => s,
  }
}

fn _path_in_ignored(repo :: Str, path :: Str) -> Bool {
  # Inspect intermediate directory segments only — the file's own
  # basename may start with a dot (e.g. `.travis.yml`).
  let rel   := _strip_prefix(_strip_prefix(path, repo), "/")
  let parts := str.split(rel, "/")
  let dirs  := _all_but_last(parts)
  list.fold(dirs, false,
    fn (acc :: Bool, p :: Str) -> Bool { acc or _is_ignored_segment(p) })
}

fn _all_but_last(xs :: List[Str]) -> List[Str] {
  let n := list.len(xs)
  if n <= 1 { [] } else { _take(xs, n - 1) }
}

fn _take(xs :: List[Str], n :: Int) -> List[Str] {
  if n <= 0 { [] } else {
    match list.head(xs) {
      None    => [],
      Some(h) => list.concat([h], _take(list.tail(xs), n - 1)),
    }
  }
}


# --- file extension extraction -----------------------------------

fn _ext_of(path :: Str) -> Str {
  # Last "." in the basename, lowercased; "" if none.
  let parts    := str.split(path, "/")
  let basename := match list.head(_take_last(parts)) {
    None    => path,
    Some(b) => b,
  }
  let bits := str.split(basename, ".")
  if list.len(bits) <= 1 {
    ""
  } else {
    match list.head(_take_last(bits)) {
      None    => "",
      Some(e) => str.to_lower(str.concat(".", e)),
    }
  }
}

fn _take_last(xs :: List[Str]) -> List[Str] {
  # Returns [last] or [] for an empty list. Walks in O(n) via fold.
  list.fold(xs, [], fn (acc :: List[Str], x :: Str) -> List[Str] { [x] })
}


# --- count_lines + detect_languages ------------------------------

fn count_lines(path :: Str) -> [io] Int {
  match io.read(path) {
    Err(_) => 0,
    Ok(content) => list.fold(str.split(content, "\n"), 0,
      fn (acc :: Int, line :: Str) -> Int {
        if str.trim(line) == "" { acc } else { acc + 1 }
      }),
  }
}

# One walk + one filter + per-language sum. We don't dedupe the
# extension list because each path is matched exactly once via
# `language_for_ext`, so each LOC count lands in exactly one bucket.
# Returned as a sorted (lang, loc, pct) triple list — easier for the
# Python cross-check to diff than a record with dynamic field names.

fn detect_languages(repo :: Str) -> [fs_walk, io] {
  total_files :: Int,
  total_loc   :: Int,
  per_lang    :: List[(Str, Int, Float)],
} {
  let all := match fs.walk(repo) {
    Err(_)    => [],
    Ok(paths) => paths,
  }
  let candidates := list.filter(all,
    fn (p :: Str) -> [fs_walk] Bool {
      fs.is_file(p) and
      (not _path_in_ignored(repo, p)) and
      (ing.language_for_ext(_ext_of(p)) != "Unknown")
    })
  let entries := list.map(candidates,
    fn (p :: Str) -> [io] (Str, Int) {
      (ing.language_for_ext(_ext_of(p)), count_lines(p))
    })
  # Drop zero-LOC files (matching Python's `if lines > 0` guard).
  let kept := list.filter(entries,
    fn (e :: (Str, Int)) -> Bool {
      match e { (_, n) => n > 0 }
    })
  let total_files := list.len(kept)
  let total_loc := list.fold(kept, 0,
    fn (acc :: Int, e :: (Str, Int)) -> Int {
      match e { (_, n) => acc + n }
    })
  let per_lang_raw := _bucket_by_lang(kept)
  let sorted := _sort_by_lang(per_lang_raw)
  let with_pct := list.map(sorted,
    fn (e :: (Str, Int)) -> (Str, Int, Float) {
      match e {
        (lang, n) => {
          let pct := if total_loc == 0 { 0.0 } else {
            _round2(int.to_float(n) * 100.0 / int.to_float(total_loc))
          }
          (lang, n, pct)
        },
      }
    })
  {
    total_files: total_files,
    total_loc:   total_loc,
    per_lang:    with_pct,
  }
}

fn _round2(x :: Float) -> Float {
  # `round(x, 2)` semantics — multiply, round to nearest, divide.
  let scaled := x * 100.0
  let i := float.to_int(scaled + 0.5)
  int.to_float(i) / 100.0
}

fn _bucket_by_lang(entries :: List[(Str, Int)]) -> List[(Str, Int)] {
  let langs := _unique_langs(entries)
  list.map(langs,
    fn (lang :: Str) -> (Str, Int) {
      let total := list.fold(entries, 0,
        fn (acc :: Int, e :: (Str, Int)) -> Int {
          match e { (l, n) => if l == lang { acc + n } else { acc } }
        })
      (lang, total)
    })
}

fn _unique_langs(entries :: List[(Str, Int)]) -> List[Str] {
  list.fold(entries, [],
    fn (acc :: List[Str], e :: (Str, Int)) -> List[Str] {
      match e {
        (l, _) => if _contains(acc, l) { acc } else { list.concat(acc, [l]) },
      }
    })
}

fn _contains(xs :: List[Str], target :: Str) -> Bool {
  list.fold(xs, false,
    fn (acc :: Bool, x :: Str) -> Bool { acc or x == target })
}

# Insertion sort over (lang, loc) by lang ascending. Lists in audits
# are tiny (≤17 known languages) so O(n²) is fine.
fn _sort_by_lang(xs :: List[(Str, Int)]) -> List[(Str, Int)] {
  list.fold(xs, [],
    fn (acc :: List[(Str, Int)], e :: (Str, Int)) -> List[(Str, Int)] {
      _insert_sorted(acc, e)
    })
}

fn _insert_sorted(
  acc :: List[(Str, Int)], e :: (Str, Int),
) -> List[(Str, Int)] {
  match list.head(acc) {
    None => [e],
    Some(h) => match (h, e) {
      ((hl, _), (el, _)) =>
        if el < hl {
          list.concat([e], acc)
        } else {
          list.concat([h], _insert_sorted(list.tail(acc), e))
        },
    },
  }
}


# --- doc_chars + classify wrapper --------------------------------

fn _safe_size(path :: Str) -> [fs_walk] Int {
  match fs.stat(path) {
    Err(_) => 0,
    Ok(s)  => s.size,
  }
}

fn doc_chars(repo :: Str) -> [fs_walk] Int {
  # README at top level, plus every *.md under docs/. Mirrors Python.
  let readmes := [
    str.concat(repo, "/README.md"),
    str.concat(repo, "/README.rst"),
    str.concat(repo, "/README"),
    str.concat(repo, "/SPEC.md"),
    str.concat(repo, "/RFC.md"),
    str.concat(repo, "/PROPOSAL.md"),
  ]
  let readme_total := list.fold(readmes, 0,
    fn (acc :: Int, p :: Str) -> [fs_walk] Int { acc + _safe_size(p) })
  let docs_md := match fs.glob(str.concat(repo, "/docs/*.md")) {
    Err(_)    => [],
    Ok(paths) => paths,
  }
  let docs_total := list.fold(docs_md, 0,
    fn (acc :: Int, p :: Str) -> [fs_walk] Int { acc + _safe_size(p) })
  readme_total + docs_total
}

fn classify_repo_type(
  repo :: Str, total_loc :: Int, has_remote_traction :: Bool,
) -> [fs_walk] (Str, Str) {
  ing.classify_repo_type_pure(total_loc, doc_chars(repo), has_remote_traction)
}


# --- io cross-check entry ----------------------------------------

fn cross_check_ingest_io(repo :: Str, has_traction :: Bool) -> [fs_walk, io] {
  total_files :: Int,
  total_loc   :: Int,
  per_lang    :: List[(Str, Int, Float)],
  doc_chars   :: Int,
  classified  :: Str,
  reason      :: Str,
} {
  let langs := detect_languages(repo)
  let dc    := doc_chars(repo)
  let cls   := ing.classify_repo_type_pure(langs.total_loc, dc, has_traction)
  match cls {
    (rt, rs) => {
      total_files: langs.total_files,
      total_loc:   langs.total_loc,
      per_lang:    langs.per_lang,
      doc_chars:   dc,
      classified:  rt,
      reason:      rs,
    },
  }
}
