"""Manual test for lex's Rust language runner.

Skipped silently if `lex` or `cargo` isn't on $PATH. Builds a tiny
synthetic Cargo project, runs both Python's `run_rust` and lex's
`run_rust`, asserts the cargo-audit availability and clippy
warnings/errors counts match.

NOT in the audit hot path. Once-off proof that lex's std.process
+ std.json plumbing produces the same answer Python does for tools
that need a `cwd` (cargo audit / clippy).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rubric.lex_cross_check import LEX_BINARY, LEX_POC_ROOT  # noqa: E402
from rubric.technical.lang_runners import run_rust  # noqa: E402

RUN_RUST_PATH = LEX_POC_ROOT / "run_rust.lex"


def make_fake_repo(root: Path) -> Path:
    repo = root / "fake-rs"
    (repo / "src").mkdir(parents=True)
    (repo / "Cargo.toml").write_text(
        '[package]\nname = "fake"\nversion = "0.1.0"\nedition = "2021"\n'
    )
    (repo / "src" / "lib.rs").write_text(
        "pub fn add(a: i32, b: i32) -> i32 { a + b }\n"
    )
    return repo


def lex_run_rust(repo: Path) -> dict | None:
    try:
        result = subprocess.run(
            [
                LEX_BINARY, "run",
                "--allow-effects", "fs_walk,io,proc",
                "--allow-fs-read", str(repo),
                str(RUN_RUST_PATH), "run_rust",
                json.dumps(str(repo)),
            ],
            capture_output=True, text=True, timeout=300, check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def main() -> int:
    if shutil.which("lex") is None:
        print("[lex-run-rust] lex binary not on PATH — skipping")
        return 0
    if shutil.which("cargo") is None:
        print("[lex-run-rust] cargo not on PATH — skipping")
        return 0

    with tempfile.TemporaryDirectory() as td:
        repo = make_fake_repo(Path(td))
        py_result = run_rust(repo)
        lex_result = lex_run_rust(repo)

        if lex_result is None:
            print("[lex-run-rust] lex runner returned None")
            return 1

        py_audit = py_result.get("tools", {}).get("cargo-audit", {})
        py_clippy = py_result.get("tools", {}).get("clippy", {})

        py_audit_avail = bool(py_audit.get("available"))
        py_clippy_avail = bool(py_clippy.get("available"))
        py_warnings = int(py_clippy.get("warnings", 0))
        py_errors = int(py_clippy.get("errors", 0))

        lex_audit_avail = lex_result["cargo_audit"]["available"]
        lex_clippy_avail = lex_result["clippy"]["available"]
        lex_warnings = lex_result["clippy"]["warnings"]
        lex_errors = lex_result["clippy"]["errors"]

        print(f"  python: cargo-audit avail={py_audit_avail}; clippy avail={py_clippy_avail} "
              f"warnings={py_warnings} errors={py_errors}")
        print(f"  lex:    cargo-audit avail={lex_audit_avail}; clippy avail={lex_clippy_avail} "
              f"warnings={lex_warnings} errors={lex_errors}")

        if py_audit_avail != lex_audit_avail:
            print("\n[lex-run-rust] FAIL: cargo-audit availability disagrees")
            return 1
        if py_clippy_avail != lex_clippy_avail:
            print("\n[lex-run-rust] FAIL: clippy availability disagrees")
            return 1
        if py_warnings != lex_warnings or py_errors != lex_errors:
            print("\n[lex-run-rust] FAIL: clippy counts disagree")
            return 1
        print("\n[lex-run-rust] Both runners agree ✅")
        return 0


if __name__ == "__main__":
    sys.exit(main())
