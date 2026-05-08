# Agent-readiness detection — port of
# `rubric/community/agent_readiness.py`.
#
# Detects "agent-readiness" signals: how well-prepared the repo is
# to be discovered and operated by AI agents. Six categories, 2 pts
# each, capped at 10:
#   - Claude Code context (CLAUDE.md / .claude/)
#   - Universal agent context (AGENTS.md)
#   - Cursor / Copilot rules
#   - ACLI / skill manifests (.cli/ / SKILL.md)
#   - MCP server manifest (mcp.json / .mcp/)
#   - Runnable examples (examples/ with .py/.js/.ts/.rs/.go/.sh)
#
# Min-bytes guard (200) avoids 5-byte placeholder CLAUDE.md files
# from gaming the score. Faithful to Python.
#
# Surface today:
#   score_agent_readiness(repo)        -> [fs_walk, io] { score, signals }
#   cross_check_agent_readiness(repo)  -> [fs_walk, io] { ... record }

import "std.fs"   as fs
import "std.list" as list
import "std.str"  as str


fn _min_bytes() -> Int { 200 }

fn _has_real_file(path :: Str) -> [fs_walk] Bool {
  match fs.stat(path) {
    Err(_) => false,
    Ok(s)  => s.is_file and s.size >= _min_bytes(),
  }
}

fn _has_nonempty_dir(path :: Str) -> [fs_walk] Bool {
  if not fs.is_dir(path) { false }
  else {
    match fs.list_dir(path) {
      Err(_)        => false,
      Ok(children)  => list.len(children) > 0,
    }
  }
}

fn _join(repo :: Str, name :: Str) -> Str {
  str.concat(str.concat(repo, "/"), name)
}


# --- per-category detectors --------------------------------------

fn _category_claude(repo :: Str) -> [fs_walk] Option[Str] {
  if _has_real_file(_join(repo, "CLAUDE.md"))
      or _has_nonempty_dir(_join(repo, ".claude")) {
    Some("Claude Code context (CLAUDE.md/.claude)")
  } else {
    None
  }
}

fn _category_universal(repo :: Str) -> [fs_walk] Option[Str] {
  if _has_real_file(_join(repo, "AGENTS.md")) {
    Some("Universal agent context (AGENTS.md)")
  } else {
    None
  }
}

fn _category_editor_rules(repo :: Str) -> [fs_walk] Option[Str] {
  if fs.exists(_join(repo, ".cursorrules"))
      or _has_nonempty_dir(_join(_join(repo, ".cursor"), "rules")) {
    Some("Cursor rules")
  } else {
    if _has_real_file(_join(_join(repo, ".github"), "copilot-instructions.md")) {
      Some("Copilot instructions")
    } else {
      None
    }
  }
}

fn _category_skill_manifest(repo :: Str) -> [fs_walk] Option[Str] {
  if _has_nonempty_dir(_join(repo, ".cli")) {
    Some("ACLI skill folder (.cli/)")
  } else {
    if _has_real_file(_join(repo, "SKILL.md")) {
      Some("Agent skill manifest (SKILL.md)")
    } else {
      None
    }
  }
}

fn _category_mcp(repo :: Str) -> [fs_walk] Option[Str] {
  if _has_real_file(_join(repo, "mcp.json")) {
    Some("MCP server manifest (mcp.json)")
  } else {
    if _has_real_file(_join(repo, ".mcp.json")) {
      Some("MCP server manifest (.mcp.json)")
    } else {
      if _has_nonempty_dir(_join(repo, ".mcp")) {
        Some("MCP folder (.mcp/)")
      } else {
        None
      }
    }
  }
}


# --- runnable examples -----------------------------------------------
# Python uses `examples.rglob("*")` to recursively search; lex's
# fs.walk gives the same all-paths list. We then check ext + is_file.

fn _runnable_exts() -> List[Str] {
  [".py", ".js", ".ts", ".rs", ".go", ".sh"]
}

fn _ext_of(path :: Str) -> Str {
  let parts := str.split(path, "/")
  let basename := list.fold(parts, "",
    fn (acc :: Str, p :: Str) -> Str { p })
  let bits := str.split(basename, ".")
  if list.len(bits) <= 1 { "" }
  else {
    let last := list.fold(bits, "",
      fn (acc :: Str, b :: Str) -> Str { b })
    str.to_lower(str.concat(".", last))
  }
}

fn _is_runnable(path :: Str) -> Bool {
  let e := _ext_of(path)
  list.fold(_runnable_exts(), false,
    fn (acc :: Bool, x :: Str) -> Bool { acc or x == e })
}

fn _category_examples(repo :: Str) -> [fs_walk] Option[Str] {
  let examples := _join(repo, "examples")
  if not fs.is_dir(examples) { None }
  else {
    let all := match fs.walk(examples) {
      Err(_)    => [],
      Ok(paths) => paths,
    }
    let has_runnable := list.fold(all, false,
      fn (acc :: Bool, p :: Str) -> [fs_walk] Bool {
        if acc { true }
        else { fs.is_file(p) and _is_runnable(p) }
      })
    if has_runnable {
      Some("Runnable examples folder")
    } else {
      None
    }
  }
}


# --- aggregator --------------------------------------------------

fn _detect_all(repo :: Str) -> [fs_walk] List[Str] {
  let cats := [
    _category_claude(repo),
    _category_universal(repo),
    _category_editor_rules(repo),
    _category_skill_manifest(repo),
    _category_mcp(repo),
    _category_examples(repo),
  ]
  list.fold(cats, [],
    fn (out :: List[Str], opt :: Option[Str]) -> List[Str] {
      match opt {
        None    => out,
        Some(s) => list.concat(out, [s]),
      }
    })
}

fn score_agent_readiness(repo :: Str) -> [fs_walk] {
  score   :: Int,
  signals :: List[Str],
} {
  let signals := _detect_all(repo)
  let raw := list.len(signals) * 2
  let capped := if raw >= 10 { 10 } else { raw }
  { score: capped, signals: signals }
}

fn cross_check_agent_readiness(repo :: Str) -> [fs_walk] {
  score   :: Int,
  signals :: List[Str],
} {
  score_agent_readiness(repo)
}
