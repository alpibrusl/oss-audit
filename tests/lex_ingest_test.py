"""Cross-check Python's URL parsers against the lex pilot.

Skipped silently if `lex` isn't on $PATH. When run, exercises the
six URL shapes the Python pipeline actually sees in practice and
asserts both implementations agree per-call.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rubric.lex_cross_check import compare_ingest, lex_ingest  # noqa: E402

CASES = [
    "https://github.com/foo/bar.git",
    "https://github.com/foo/bar",
    "git@github.com:foo/bar.git",
    "https://github.com/foo/repo.with.dots",
    "https://gitlab.com/foo/bar",
    "https://gist.github.com/alice/abc123def456",
    "/tmp/some/local/path",
]


def main() -> int:
    if shutil.which("lex") is None:
        print("[lex-ingest] lex binary not on PATH — skipping")
        return 0
    failures: list[str] = []
    for url in CASES:
        result = lex_ingest(url, 100, 0, False)
        if result is None:
            failures.append(f"{url}: lex_ingest returned None")
            continue
        diffs = compare_ingest(url, result)
        if diffs:
            failures.append(f"{url}: {'; '.join(diffs)}")
        else:
            print(f"  OK   {url}")
    if failures:
        print("\n[lex-ingest] FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n[lex-ingest] All cases agree ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
