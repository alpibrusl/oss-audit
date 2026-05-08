# Python language runner — port of
# `rubric/technical/lang_runners.py::run_python`. Lives in its own
# file so the dispatcher (`lang_dispatch.lex`) stays pure.
#
# Effects: `[proc, fs_walk, io]`. Spawns ruff + pip-audit when
# they're on $PATH and the repo has Python markers, parses their
# JSON output, returns a normalized record matching the shape
# Python produces.
#
# Tool detection: lex's std.process has no `which` equivalent, so
# we probe by running the tool with `--version` and checking for a
# clean exit. That's one extra subprocess per tool but keeps the
# port faithful without requiring std.env / PATH walking.
#
# NOT cross-checked at audit time: running the same lint twice
# (Python + lex) would double the per-audit subprocess cost. The
# port ships as a working implementation that future code can
# call directly when the pipeline switches engines.
#
# Surface:
#   run_python(repo) -> [proc, fs_walk, io] {
#     language    :: Str,
#     skipped     :: Str,             # "" if not skipped
#     ruff        :: ToolResult,
#     pip_audit   :: ToolResult,
#   }
#
# Each ToolResult is { available :: Bool, count :: Int, error :: Str }
# where `count` carries either the issue count (ruff) or the
# vulnerability count (pip-audit). Slimmer than Python's `by_code`
# breakdown but enough for the score-side aggregator.

import "std.process" as proc
import "std.fs"      as fs
import "std.io"      as io
import "std.list"    as list
import "std.str"     as str
import "std.json"    as json


type ToolResult = {
  available :: Bool,
  count     :: Int,
  error     :: Str,
}

type RunResult = {
  language  :: Str,
  skipped   :: Str,
  ruff      :: ToolResult,
  pip_audit :: ToolResult,
}


# --- tool detection ----------------------------------------------

fn _has(cmd :: Str) -> [proc] Bool {
  match proc.run(cmd, ["--version"]) {
    Err(_) => false,
    Ok(r)  => r.exit_code == 0,
  }
}


# --- Python project markers --------------------------------------

fn _join(repo :: Str, name :: Str) -> Str {
  str.concat(str.concat(repo, "/"), name)
}

fn _has_pyproject(repo :: Str) -> [fs_walk] Bool {
  fs.exists(_join(repo, "pyproject.toml"))
}

fn _has_requirements(repo :: Str) -> [fs_walk] Bool {
  fs.exists(_join(repo, "requirements.txt"))
}

# Cheap check: any `.py` file under the repo. Uses fs.walk + ext
# match — same approach as ingestion_io.lex.
fn _has_any_py(repo :: Str) -> [fs_walk] Bool {
  match fs.walk(repo) {
    Err(_)    => false,
    Ok(paths) => list.fold(paths, false,
      fn (acc :: Bool, p :: Str) -> Bool {
        if acc { true } else { str.ends_with(p, ".py") }
      }),
  }
}


# --- ruff ---------------------------------------------------------

type RuffIssue = { code :: Str }

fn _run_ruff(repo :: Str) -> [proc] ToolResult {
  if not _has("ruff") {
    { available: false, count: 0, error: "" }
  } else {
    match proc.run("ruff", ["check", repo, "--output-format=json"]) {
      Err(e) => { available: true, count: 0, error: e },
      Ok(r)  => {
        let trimmed := str.trim(r.stdout)
        if trimmed == "" {
          { available: true, count: 0, error: "" }
        } else {
          let parsed :: Result[List[RuffIssue], Str] := json.parse(trimmed)
          match parsed {
            Err(_)  => { available: true, count: 0, error: "parse_failed" },
            Ok(xs)  => { available: true, count: list.len(xs), error: "" },
          }
        }
      },
    }
  }
}


# --- pip-audit ---------------------------------------------------

type PipAuditDep = { vulns :: List[{ id :: Str }] }
type PipAuditOut = { dependencies :: List[PipAuditDep] }

fn _run_pip_audit(repo :: Str) -> [proc, fs_walk] ToolResult {
  if not _has("pip-audit") {
    { available: false, count: 0, error: "" }
  } else {
    let has_pp := _has_pyproject(repo)
    let has_rq := _has_requirements(repo)
    if not (has_pp or has_rq) {
      { available: false, count: 0, error: "" }
    } else {
      let args := if has_rq {
        ["pip-audit", "--format", "json", "-r", _join(repo, "requirements.txt")]
      } else {
        ["pip-audit", "--format", "json"]
      }
      # pip-audit's CLI doesn't take cwd via run; pyproject path is
      # implicit when invoked without -r so we keep that simple.
      match proc.run("pip-audit", list.tail(args)) {
        Err(e) => { available: true, count: 0, error: e },
        Ok(r)  => {
          let trimmed := str.trim(r.stdout)
          if trimmed == "" {
            { available: true, count: 0, error: "" }
          } else {
            let parsed :: Result[PipAuditOut, Str] := json.parse(trimmed)
            match parsed {
              Err(_)  => { available: true, count: 0, error: "parse_failed" },
              Ok(out) => {
                let total := list.fold(out.dependencies, 0,
                  fn (acc :: Int, d :: PipAuditDep) -> Int {
                    acc + list.len(d.vulns)
                  })
                { available: true, count: total, error: "" }
              },
            }
          }
        },
      }
    }
  }
}


# --- public API --------------------------------------------------

fn run_python(repo :: Str) -> [proc, fs_walk, io] RunResult {
  let pp := _has_pyproject(repo)
  let rq := _has_requirements(repo)
  let py := _has_any_py(repo)
  if not (pp or rq or py) {
    {
      language:  "Python",
      skipped:   "no Python project markers",
      ruff:      { available: false, count: 0, error: "" },
      pip_audit: { available: false, count: 0, error: "" },
    }
  } else {
    {
      language:  "Python",
      skipped:   "",
      ruff:      _run_ruff(repo),
      pip_audit: _run_pip_audit(repo),
    }
  }
}
