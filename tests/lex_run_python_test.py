"""Manual test for lex's Python language runner.

Skipped silently if `lex` or `ruff` isn't on $PATH. Builds a tiny
synthetic Python repo with one known lint issue, runs both Python's
`run_python` and lex's `run_python`, and asserts they agree on
ruff's issue count.

NOT in the audit hot path — running both on every audit would
double the subprocess cost. This is a once-off proof that lex's
std.process + std.json plumbing produces the same answer Python
does on the same code.
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
from rubric.technical.lang_runners import run_python  # noqa: E402

RUN_PYTHON_PATH = LEX_POC_ROOT / "run_python.lex"


def make_fake_repo(root: Path) -> Path:
    repo = root / "fake-py"
    repo.mkdir()
    (repo / "main.py").write_text(
        # F841 — unused local variable
        "def hello():\n    print('hi')\n    x = 42\n"
    )
    (repo / "pyproject.toml").write_text(
        "[project]\nname = 'fake'\nversion = '0.1.0'\n"
    )
    return repo


def lex_run_python(repo: Path) -> dict | None:
    try:
        result = subprocess.run(
            [
                LEX_BINARY, "run",
                "--allow-effects", "fs_walk,io,proc",
                "--allow-fs-read", str(repo),
                str(RUN_PYTHON_PATH), "run_python",
                json.dumps(str(repo)),
            ],
            capture_output=True, text=True, timeout=120, check=False,
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
        print("[lex-run-python] lex binary not on PATH — skipping")
        return 0
    if shutil.which("ruff") is None:
        print("[lex-run-python] ruff not on PATH — skipping")
        return 0

    with tempfile.TemporaryDirectory() as td:
        repo = make_fake_repo(Path(td))
        py_result = run_python(repo)
        lex_result = lex_run_python(repo)

        if lex_result is None:
            print("[lex-run-python] lex runner returned None")
            return 1

        py_ruff = py_result.get("tools", {}).get("ruff", {})
        py_issues = int(py_ruff.get("issues", 0)) if py_ruff.get("available") else 0
        lex_issues = int(lex_result["ruff"]["count"]) if lex_result["ruff"]["available"] else 0

        print(f"  python: ruff available={py_ruff.get('available')} issues={py_issues}")
        print(f"  lex:    ruff available={lex_result['ruff']['available']} count={lex_issues}")

        if py_ruff.get("available") != lex_result["ruff"]["available"]:
            print("\n[lex-run-python] FAIL: ruff availability disagrees")
            return 1
        if py_issues != lex_issues:
            print(f"\n[lex-run-python] FAIL: ruff issue count {py_issues} != {lex_issues}")
            return 1

        print("\n[lex-run-python] Both runners agree on ruff issue count ✅")
        return 0


if __name__ == "__main__":
    sys.exit(main())
