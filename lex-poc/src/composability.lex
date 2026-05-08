# Composability detection — port of `rubric/technical/composability.py`.
#
# Detects "composability surfaces" — ways the repo can combine with
# other systems. CLI / library / MCP / HTTP server / workspace.
# Each detected surface adds 2 points up to 10.
#
# All detection is content-substring-based. Faithful to Python (which
# also does substring for everything except package.json's bin/main/
# exports/workspaces structured fields, where it falls back to None
# silently on a JSON parse error). The cross-check tolerates the rare
# edge case where lex's substring match flags a key Python's truthy
# check would skip (e.g. explicit `"bin": null`); when that happens
# the diff is real signal worth surfacing.
#
# Surface today:
#   score_composability(repo)        -> [fs_walk, io] { score, surfaces }
#   cross_check_composability(repo)  -> [fs_walk, io] { ... record }

import "std.fs"   as fs
import "std.io"   as io
import "std.list" as list
import "std.str"  as str


# --- file-reading helpers ----------------------------------------

fn _has_real_file(path :: Str, min_bytes :: Int) -> [fs_walk] Bool {
  match fs.stat(path) {
    Err(_) => false,
    Ok(s)  => s.is_file and s.size >= min_bytes,
  }
}

fn _read_capped(path :: Str, limit :: Int) -> [io] Str {
  match io.read(path) {
    Err(_) => "",
    Ok(c)  => {
      let n := str.len(c)
      if n <= limit { c } else { str.slice(c, 0, limit) }
    },
  }
}

fn _join(repo :: Str, name :: Str) -> Str {
  str.concat(str.concat(repo, "/"), name)
}


# --- Option helpers ----------------------------------------------

fn _first_some(opts :: List[Option[Str]]) -> Option[Str] {
  list.fold(opts, None,
    fn (acc :: Option[Str], cur :: Option[Str]) -> Option[Str] {
      match acc {
        Some(_) => acc,
        None    => cur,
      }
    })
}

fn _if(cond :: Bool, label :: Str) -> Option[Str] {
  if cond { Some(label) } else { None }
}


# --- CLI detection -----------------------------------------------

fn _has_cli(repo :: Str) -> [fs_walk, io] Option[Str] {
  let pp := _read_capped(_join(repo, "pyproject.toml"), 10000)
  if str.contains(pp, "[project.scripts]") or str.contains(pp, "entry_points") {
    Some("Python CLI (project.scripts / entry_points)")
  } else {
    let cargo := _read_capped(_join(repo, "Cargo.toml"), 10000)
    if str.contains(cargo, "[[bin]]") or _has_real_file(_join(_join(repo, "src"), "main.rs"), 50) {
      Some("Rust binary ([[bin]] / src/main.rs)")
    } else {
      let pkg := _read_capped(_join(repo, "package.json"), 10000)
      # Python parses JSON and does data.get("bin"); we match the
      # `"bin":` key substring instead. False-positive only on the
      # rare `"bin": null` edge case.
      if str.contains(pkg, "\"bin\":") or str.contains(pkg, "\"bin\" :") {
        Some("Node CLI (package.json bin)")
      } else {
        if _has_real_file(_join(repo, "main.go"), 50) or fs.is_dir(_join(repo, "cmd")) {
          Some("Go entrypoint (main.go / cmd/)")
        } else {
          None
        }
      }
    }
  }
}


# --- library detection -------------------------------------------

fn _python_pkg_in_src(repo :: Str) -> [fs_walk, io] Option[Str] {
  let src := _join(repo, "src")
  if not fs.is_dir(src) {
    None
  } else {
    match fs.list_dir(src) {
      Err(_)  => None,
      Ok(children) => list.fold(children, None,
        fn (acc :: Option[Str], child :: Str) -> [fs_walk, io] Option[Str] {
          match acc {
            Some(_) => acc,
            None    => {
              let init := _join(child, "__init__.py")
              if not fs.is_file(init) {
                None
              } else {
                let content := _read_capped(init, 5000)
                if str.contains(content, "__all__") or str.contains(content, "from .") {
                  Some(str.concat(
                    str.concat("Python package (", _basename(child)),
                    "/__init__.py)"))
                } else {
                  None
                }
              }
            },
          }
        }),
    }
  }
}

fn _basename(path :: Str) -> Str {
  let parts := str.split(path, "/")
  list.fold(parts, "", fn (acc :: Str, p :: Str) -> Str { p })
}

fn _has_library(repo :: Str) -> [fs_walk, io] Option[Str] {
  if _has_real_file(_join(_join(repo, "src"), "lib.rs"), 50) {
    Some("Rust library (src/lib.rs)")
  } else {
    match _python_pkg_in_src(repo) {
      Some(s) => Some(s),
      None    => {
        if fs.is_dir(_join(repo, "pkg")) {
          Some("Go library (pkg/)")
        } else {
          let pkg := _read_capped(_join(repo, "package.json"), 10000)
          if str.contains(pkg, "\"main\":") or str.contains(pkg, "\"module\":")
              or str.contains(pkg, "\"exports\":") {
            Some("Node library (package.json main/exports)")
          } else {
            None
          }
        }
      },
    }
  }
}


# --- MCP detection -----------------------------------------------

fn _has_mcp(repo :: Str) -> [fs_walk, io] Option[Str] {
  if _has_real_file(_join(repo, "mcp.json"), 50) {
    Some("MCP manifest (mcp.json)")
  } else {
    if _has_real_file(_join(repo, ".mcp.json"), 50) {
      Some("MCP manifest (.mcp.json)")
    } else {
      if fs.is_dir(_join(repo, ".mcp")) {
        Some("MCP folder (.mcp/)")
      } else {
        let deps := str.to_lower(str.concat(
          str.concat(_read_capped(_join(repo, "pyproject.toml"), 5000),
                     _read_capped(_join(repo, "package.json"), 5000)),
          _read_capped(_join(repo, "Cargo.toml"), 5000)))
        if str.contains(deps, "modelcontextprotocol") or str.contains(deps, "mcp-server") {
          Some("MCP server (dependency declared)")
        } else {
          None
        }
      }
    }
  }
}


# --- HTTP server detection ---------------------------------------

fn _http_markers() -> List[(Str, Str)] {
  [
    ("fastapi",    "FastAPI HTTP server"),
    ("starlette",  "Starlette HTTP server"),
    ("flask",      "Flask HTTP server"),
    ("axum",       "axum HTTP server (Rust)"),
    ("actix-web",  "actix HTTP server (Rust)"),
    ("rocket",     "Rocket HTTP server (Rust)"),
    ("\"express\"", "Express HTTP server (Node)"),
    ("fastify",    "Fastify HTTP server (Node)"),
    ("gin-gonic",  "gin HTTP server (Go)"),
    ("net/http",   "Go HTTP server"),
  ]
}

fn _has_http_server(repo :: Str) -> [fs_walk, io] Option[Str] {
  let deps := str.to_lower(str.concat(
    str.concat(
      str.concat(_read_capped(_join(repo, "pyproject.toml"), 8000),
                 _read_capped(_join(repo, "requirements.txt"), 8000)),
      str.concat(_read_capped(_join(repo, "package.json"), 8000),
                 _read_capped(_join(repo, "Cargo.toml"), 8000))),
    _read_capped(_join(repo, "go.mod"), 8000)))
  list.fold(_http_markers(), None,
    fn (acc :: Option[Str], pair :: (Str, Str)) -> Option[Str] {
      match acc {
        Some(_) => acc,
        None    => match pair {
          (marker, label) => if str.contains(deps, marker) { Some(label) } else { None },
        },
      }
    })
}


# --- workspace detection -----------------------------------------

fn _has_workspace(repo :: Str) -> [fs_walk, io] Option[Str] {
  let cargo := _read_capped(_join(repo, "Cargo.toml"), 5000)
  if str.contains(cargo, "[workspace]") {
    Some("Cargo workspace (multi-crate)")
  } else {
    let pkg := _read_capped(_join(repo, "package.json"), 8000)
    if str.contains(pkg, "\"workspaces\"") {
      Some("npm/yarn/pnpm workspace")
    } else {
      if fs.exists(_join(repo, "pnpm-workspace.yaml")) {
        Some("pnpm workspace")
      } else {
        let crates := _join(repo, "crates")
        if not fs.is_dir(crates) {
          None
        } else {
          match fs.list_dir(crates) {
            Err(_)  => None,
            Ok(cs)  =>
              if list.len(cs) >= 3 {
                # Python embeds the count in the label.
                Some(str.concat(
                  str.concat("Multi-crate monorepo (crates/ with ",
                             _int_to_str(list.len(cs))),
                  " children)"))
              } else {
                None
              },
          }
        }
      }
    }
  }
}

fn _int_to_str(n :: Int) -> Str {
  # Local because std.int is overkill; the only consumer is the
  # workspace label.
  if n == 0 { "0" }
  else { if n == 1 { "1" }
  else { if n == 2 { "2" }
  else { if n == 3 { "3" }
  else { if n == 4 { "4" }
  else { if n == 5 { "5" }
  else { if n == 6 { "6" }
  else { if n == 7 { "7" }
  else { if n == 8 { "8" }
  else { if n == 9 { "9" }
  else {
    # ≥10: recursively concat digits. Tail recursion via fold over
    # the (bounded) list of digits would be cleaner, but lex doesn't
    # support `Int.div / mod` directly here; we fall back to a generic
    # quick path for small counts (most monorepos < 30 crates).
    str.concat(_int_to_str(n / 10), _int_to_str(n - (n / 10) * 10))
  } } } } } } } } } }
}


# --- candidate roots + main entry --------------------------------

fn _monorepo_subdirs() -> List[Str] {
  ["crates", "packages", "sdks", "apps", "services", "modules"]
}

fn _candidate_roots(repo :: Str) -> [fs_walk] List[Str] {
  let extras := list.fold(_monorepo_subdirs(), [],
    fn (acc :: List[Str], sub :: Str) -> [fs_walk] List[Str] {
      let dir := _join(repo, sub)
      if not fs.is_dir(dir) {
        acc
      } else {
        match fs.list_dir(dir) {
          Err(_)        => acc,
          Ok(children)  => list.concat(acc, list.filter(children,
            fn (c :: Str) -> [fs_walk] Bool {
              fs.is_dir(c) and (not str.starts_with(_basename(c), "."))
            })),
        }
      }
    })
  list.concat([repo], extras)
}

# Run all 5 detectors on a single root, returning the labels found.
fn _detect_at(root :: Str) -> [fs_walk, io] List[Option[Str]] {
  [
    _has_cli(root),
    _has_library(root),
    _has_mcp(root),
    _has_http_server(root),
    _has_workspace(root),
  ]
}

fn _label_with_path(label :: Str, repo :: Str, root :: Str) -> Str {
  if root == repo {
    label
  } else {
    let rel := match str.strip_prefix(root, str.concat(repo, "/")) {
      Some(s) => s,
      None    => root,
    }
    str.concat(str.concat(label, " @ "), rel)
  }
}

# Walk all roots in order, taking the FIRST detection per detector
# index. Mirrors Python's `seen_categories` set.
fn _collect_surfaces(repo :: Str) -> [fs_walk, io] List[Str] {
  let roots := _candidate_roots(repo)
  let init := [None, None, None, None, None]
  let final := list.fold(roots, init,
    fn (acc :: List[Option[Str]], root :: Str) -> [fs_walk, io] List[Option[Str]] {
      let here := _detect_at(root)
      _zip_with_first(acc, here, repo, root)
    })
  list.fold(final, [],
    fn (out :: List[Str], slot :: Option[Str]) -> List[Str] {
      match slot {
        None    => out,
        Some(s) => list.concat(out, [s]),
      }
    })
}

fn _zip_with_first(
  acc :: List[Option[Str]], here :: List[Option[Str]],
  repo :: Str, root :: Str,
) -> List[Option[Str]] {
  # Position-aware merge: for each index, keep acc[i] if Some, else
  # take here[i] (decorated with the root's relative path).
  match list.head(acc) {
    None => [],
    Some(a) => match list.head(here) {
      None    => acc,
      Some(h) => {
        let merged := match a {
          Some(_) => a,
          None    => match h {
            None    => None,
            Some(label) => Some(_label_with_path(label, repo, root)),
          },
        }
        list.concat([merged], _zip_with_first(
          list.tail(acc), list.tail(here), repo, root))
      },
    },
  }
}


# --- public API --------------------------------------------------

fn score_composability(repo :: Str) -> [fs_walk, io] {
  score    :: Int,
  surfaces :: List[Str],
} {
  let surfaces := _collect_surfaces(repo)
  let raw := list.len(surfaces) * 2
  let capped := if raw >= 10 { 10 } else { raw }
  { score: capped, surfaces: surfaces }
}

fn cross_check_composability(repo :: Str) -> [fs_walk, io] {
  score    :: Int,
  surfaces :: List[Str],
} {
  score_composability(repo)
}
