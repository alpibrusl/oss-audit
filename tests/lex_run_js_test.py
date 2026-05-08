"""Manual test for lex's JavaScript/TypeScript language runner.

Skipped silently if `lex` or `npm` isn't on $PATH. Builds a tiny
synthetic Node project + lockfile, runs both runners, asserts the
npm-audit availability and vulnerability count match.

NOT in the audit hot path.
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
from rubric.technical.lang_runners import run_js  # noqa: E402

RUN_JS_PATH = LEX_POC_ROOT / "run_js.lex"


def make_fake_repo(root: Path) -> Path:
    repo = root / "fake-js"
    repo.mkdir()
    (repo / "package.json").write_text(
        json.dumps({
            "name": "fake", "version": "0.1.0",
            "dependencies": {"lodash": "^4.17.0"},
        })
    )
    # Generate a lockfile so npm audit doesn't fail with ENOLOCK.
    subprocess.run(
        ["npm", "install", "--package-lock-only", "--no-audit", "--no-fund"],
        cwd=repo, capture_output=True, check=False, timeout=60,
    )
    return repo


def lex_run_js(repo: Path) -> dict | None:
    try:
        result = subprocess.run(
            [
                LEX_BINARY, "run",
                "--allow-effects", "fs_walk,io,proc",
                "--allow-fs-read", str(repo),
                str(RUN_JS_PATH), "run_js",
                json.dumps(str(repo)),
            ],
            capture_output=True, text=True, timeout=180, check=False,
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
        print("[lex-run-js] lex binary not on PATH — skipping")
        return 0
    if shutil.which("npm") is None:
        print("[lex-run-js] npm not on PATH — skipping")
        return 0

    with tempfile.TemporaryDirectory() as td:
        repo = make_fake_repo(Path(td))
        py_result = run_js(repo)
        lex_result = lex_run_js(repo)

        if lex_result is None:
            print("[lex-run-js] lex runner returned None")
            return 1

        py_audit = py_result.get("tools", {}).get("npm-audit", {})
        py_avail = bool(py_audit.get("available"))
        py_count = int(py_audit.get("vulnerabilities", 0))

        lex_avail = lex_result["npm_audit"]["available"]
        lex_count = lex_result["npm_audit"]["count"]

        print(f"  python: npm-audit avail={py_avail} vulns={py_count}")
        print(f"  lex:    npm-audit avail={lex_avail} count={lex_count}")

        if py_avail != lex_avail:
            print("\n[lex-run-js] FAIL: npm-audit availability disagrees")
            return 1
        if py_count != lex_count:
            print(f"\n[lex-run-js] FAIL: vulnerability count {py_count} != {lex_count}")
            return 1
        print("\n[lex-run-js] Both runners agree ✅")
        return 0


if __name__ == "__main__":
    sys.exit(main())
