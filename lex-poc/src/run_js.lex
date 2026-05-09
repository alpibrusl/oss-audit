# JavaScript/TypeScript language runner — port of
# `rubric/technical/lang_runners.py::run_js`.
#
# Same shape as run_rust.lex. Spawns `npm audit --json` inside
# the repo, parses the metadata.vulnerabilities tally.
#
# Effects: `[proc, fs_walk, io]`. NOT cross-checked at audit time.
#
# Surface:
#   run_js(repo) -> [proc, fs_walk, io] {
#     language   :: Str,
#     skipped    :: Str,
#     npm_audit  :: ToolResult,
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

type RunResult = {
  language  :: Str,
  skipped   :: Str,
  npm_audit :: ToolResult,
}


# --- helpers (duplicated from run_rust.lex; lex has no module-private
# imports yet, so each runner carries its own copy) ----------------

fn _has(cmd :: Str) -> [proc] Bool {
  match proc.run(cmd, ["--version"]) {
    Err(_) => false,
    Ok(r)  => r.exit_code == 0,
  }
}

fn _join(repo :: Str, name :: Str) -> Str {
  str.concat(str.concat(repo, "/"), name)
}

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


# --- npm audit --------------------------------------------------
# Output: { metadata: { vulnerabilities: { critical, high, moderate, low, info } } }
# Total = sum of (critical + high + moderate + low). info excluded
# to match Python.

type NpmVulns = {
  critical :: Int,
  high     :: Int,
  moderate :: Int,
  low      :: Int,
}
type NpmMeta = { vulnerabilities :: NpmVulns }
type NpmOut  = { metadata :: NpmMeta }

fn _run_npm_audit(repo :: Str) -> [proc] ToolResult {
  if not _has("npm") {
    { available: false, count: 0, error: "" }
  } else {
    match _spawn_in("npm", ["audit", "--json"], repo) {
      Err(e) => { available: true, count: 0, error: e },
      Ok(r)  => {
        let joined := str.join(r.stdout, "\n")
        let trimmed := str.trim(joined)
        if trimmed == "" {
          { available: true, count: 0, error: "" }
        } else {
          let parsed :: Result[NpmOut, Str] := json.parse(trimmed)
          match parsed {
            Err(_)  => { available: true, count: 0, error: "parse_failed" },
            Ok(out) => {
              let v := out.metadata.vulnerabilities
              let total := v.critical + v.high + v.moderate + v.low
              { available: true, count: total, error: "" }
            },
          }
        }
      },
    }
  }
}


# --- public API --------------------------------------------------

fn run_js(repo :: Str) -> [proc, fs_walk, io] RunResult {
  if not fs.exists(_join(repo, "package.json")) {
    {
      language:  "JavaScript/TypeScript",
      skipped:   "no package.json",
      npm_audit: { available: false, count: 0, error: "" },
    }
  } else {
    {
      language:  "JavaScript/TypeScript",
      skipped:   "",
      npm_audit: _run_npm_audit(repo),
    }
  }
}
