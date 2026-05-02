"""Smoke test: verifica que el pipeline carga y corre sin API keys.

Ejecuta el pilar técnico sobre un mini-repo creado en tmp.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oss_auditor.pipeline import run_audit  # noqa: E402


def make_fake_repo(tmpdir: Path) -> Path:
    repo = tmpdir / "fake-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)

    (repo / "README.md").write_text("# Fake\n\nA test repo.\n")
    (repo / "LICENSE").write_text("MIT License\nCopyright (c) 2024\n")
    (repo / "main.py").write_text("def hello():\n    print('hi')\n")
    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text("def test_hello():\n    assert True\n")

    # workflow CI
    wf = repo / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("name: CI\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n")

    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    return repo


def main():
    with tempfile.TemporaryDirectory() as td:
        repo = make_fake_repo(Path(td))
        print(f"[smoke] Created fake repo at {repo}")

        # Forzar skip de business y community para no requerir APIs
        report = run_audit(
            str(repo),
            skip_business=True,
            skip_community=True,
            progress=lambda x: print(f"  > {x}"),
        )

        print("\n[smoke] Pipeline OK")
        print(f"  - Repo: {report.repo.name}")
        print(f"  - Languages: {report.repo.languages}")
        print(f"  - Technical score: {report.technical.score}")
        print(f"  - Has tests: {report.technical.has_tests}")
        print(f"  - Has CI: {report.technical.has_ci}")
        print(f"  - License: {report.technical.raw.get('universal', {}).get('license')}")
        print(f"  - Tools run: {report.technical.tools_run}")
        print(f"  - Overall: {report.overall_score} ({report.grade})")

        assert report.technical.has_tests, "Tests should be detected"
        assert report.technical.has_ci, "CI should be detected"
        assert report.technical.score > 0, "Technical score should be > 0"
        print("\n[smoke] All assertions passed ✅")


if __name__ == "__main__":
    main()
