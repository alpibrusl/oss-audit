# Rust language runner — port of
# `rubric/technical/lang_runners.py::run_rust`.
#
# Same shape as run_python.lex but uses `proc.spawn` with `cwd`
# (cargo audit / clippy must run inside the repo). The lex side
# spawns, drains stdout, waits for exit, then parses the output.
#
# Effects: `[proc, fs_walk, io]` — fs_walk for the Cargo.toml
# probe, io is transitively required when std.process drains
# stderr behind the scenes.
#
# NOT cross-checked at audit time (would double subprocess cost).
# Validated manually against synthetic Rust repos.
#
# Surface:
#   run_rust(repo) -> [proc, fs_walk, io] {
#     language    :: Str,
#     skipped     :: Str,            # "" if not skipped
#     cargo_audit :: ToolResult,
#     clippy      :: ClippyResult,
#   }

import "std.process" as proc
import "std.fs"      as fs
import "std.list"    as list
import "std.str"     as str
import "std.map"     as map
import "std.json"    as json


type ToolResult = {
  available :: Bool,
  count     :: Int,
  error     :: Str,
}

# Clippy returns warnings + errors separately; bundle them.
type ClippyResult = {
  available :: Bool,
  warnings  :: Int,
  errors    :: Int,
  exit_code :: Int,
  error     :: Str,
}

type RunResult = {
  language    :: Str,
  skipped     :: Str,
  cargo_audit :: ToolResult,
  clippy      :: ClippyResult,
}


# --- helpers -----------------------------------------------------

fn _has(cmd :: Str) -> [proc] Bool {
  match proc.run(cmd, ["--version"]) {
    Err(_) => false,
    Ok(r)  => r.exit_code == 0,
  }
}

fn _join(repo :: Str, name :: Str) -> Str {
  str.concat(str.concat(repo, "/"), name)
}

# Drain stdout line-by-line until EOF. Recursive — fine for the
# bounded outputs cargo emits.
fn _drain(h :: ProcessHandle) -> [proc] List[Str] {
  match proc.read_stdout_line(h) {
    None       => [],
    Some(line) => list.concat([line], _drain(h)),
  }
}

fn _spawn_in(
  cmd :: Str, args :: List[Str], cwd :: Str,
) -> [proc] Result[{ stdout :: List[Str], code :: Int }, Str] {
  match proc.spawn(cmd, args,
    { cwd: Some(cwd), env: map.new(), stdin: None }) {
    Err(e) => Err(e),
    Ok(h)  => {
      let lines := _drain(h)
      let info  := proc.wait(h)
      Ok({ stdout: lines, code: info.code })
    },
  }
}


# --- cargo audit -------------------------------------------------
# Output shape: { vulnerabilities: { list: [...] } }. We just need
# the count, so a slim `parse` is enough.

type AuditOut = { vulnerabilities :: { list :: List[{ id :: Str }] } }

fn _run_cargo_audit(repo :: Str) -> [proc] ToolResult {
  if not _has("cargo") {
    { available: false, count: 0, error: "" }
  } else {
    if not _has("cargo-audit") {
      { available: false, count: 0, error: "" }
    } else {
      match _spawn_in("cargo", ["audit", "--json"], repo) {
        Err(e) => { available: true, count: 0, error: e },
        Ok(r)  => {
          let joined := str.join(r.stdout, "\n")
          let trimmed := str.trim(joined)
          if trimmed == "" {
            { available: true, count: 0, error: "" }
          } else {
            let parsed :: Result[AuditOut, Str] := json.parse(trimmed)
            match parsed {
              Err(_)   => { available: true, count: 0, error: "parse_failed" },
              Ok(out)  => {
                let n := list.len(out.vulnerabilities.list)
                { available: true, count: n, error: "" }
              },
            }
          }
        },
      }
    }
  }
}


# --- cargo clippy ------------------------------------------------
# Output is JSONL — each line is a compiler message. We want lines
# where reason == "compiler-message" and bucket by message.level.

type ClippyMsg = { reason :: Str, message :: { level :: Str } }

fn _classify_clippy_line(
  line :: Str, acc :: { warnings :: Int, errors :: Int },
) -> { warnings :: Int, errors :: Int } {
  let trimmed := str.trim(line)
  if trimmed == "" { acc }
  else {
    let parsed :: Result[ClippyMsg, Str] := json.parse(trimmed)
    match parsed {
      Err(_)   => acc,
      Ok(msg)  =>
        if msg.reason == "compiler-message" {
          if msg.message.level == "warning" {
            { warnings: acc.warnings + 1, errors: acc.errors }
          } else {
            if msg.message.level == "error" {
              { warnings: acc.warnings, errors: acc.errors + 1 }
            } else {
              acc
            }
          }
        } else {
          acc
        },
    }
  }
}

fn _run_clippy(repo :: Str) -> [proc] ClippyResult {
  if not _has("cargo") {
    { available: false, warnings: 0, errors: 0, exit_code: 0, error: "" }
  } else {
    let args := [
      "clippy", "--workspace", "--all-targets",
      "--message-format=json", "--", "-W", "clippy::all",
    ]
    match _spawn_in("cargo", args, repo) {
      Err(e) => {
        available: true, warnings: 0, errors: 0, exit_code: -1, error: e,
      },
      Ok(r)  => {
        let counts := list.fold(r.stdout,
          { warnings: 0, errors: 0 },
          fn (acc :: { warnings :: Int, errors :: Int }, line :: Str) -> { warnings :: Int, errors :: Int } {
            _classify_clippy_line(line, acc)
          })
        {
          available: true,
          warnings:  counts.warnings,
          errors:    counts.errors,
          exit_code: r.code,
          error:     "",
        }
      },
    }
  }
}


# --- public API --------------------------------------------------

fn run_rust(repo :: Str) -> [proc, fs_walk, io] RunResult {
  if not fs.exists(_join(repo, "Cargo.toml")) {
    {
      language:    "Rust",
      skipped:     "no Cargo.toml found",
      cargo_audit: { available: false, count: 0, error: "" },
      clippy:      { available: false, warnings: 0, errors: 0, exit_code: 0, error: "" },
    }
  } else {
    {
      language:    "Rust",
      skipped:     "",
      cargo_audit: _run_cargo_audit(repo),
      clippy:      _run_clippy(repo),
    }
  }
}
