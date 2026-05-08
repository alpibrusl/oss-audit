"""Cross-check Python's `_extract_gh_url` against the lex pilot.

Skipped silently if `lex` isn't on $PATH. Exercises the URL field,
text field, trailing-punctuation cleanup, and the host-parts
validation that filters non-repo URLs.

The lex `[net]` half (HN API fetcher) lives in `hn_source_net.lex`
and is exercised manually — sandbox-blocked egress in CI makes a
unit test pointless, and nothing on the audit hot path depends on
it.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rubric.lex_cross_check import (  # noqa: E402
    compare_extract_gh_url, lex_extract_gh_url,
)
from rubric.sources.hn import _extract_gh_url  # noqa: E402


# Each case is an HN-item-shaped dict; `_extract_gh_url` consumes
# the `url` / `text` fields directly. The lex bridge takes them as
# separate positional args (defaulting to "" if absent).
CASES: list[dict] = [
    # url field, simple repo
    {"url": "https://github.com/foo/bar"},
    # url field, gist with trailing slash
    {"url": "https://gist.github.com/alice/abc123/"},
    # text field, with trailing-punctuation that needs trimming
    {"url": "https://example.com",
     "text": "check this out https://github.com/foo/bar/baz."},
    # text field, no GitHub URL
    {"text": "just a comment, no links"},
    # url field, sponsors path (Python doesn't actually filter — comment is misleading)
    {"url": "https://github.com/sponsors/x"},
    # url field, www. prefix
    {"url": "https://www.github.com/foo/bar"},
    # http (not https) prefix
    {"url": "http://github.com/foo/bar"},
    # empty
    {},
    # url field with .git suffix
    {"url": "https://github.com/foo/bar.git"},
]


def main() -> int:
    if shutil.which("lex") is None:
        print("[lex-hn] lex binary not on PATH — skipping")
        return 0
    failures: list[str] = []
    for item in CASES:
        py_result = _extract_gh_url(item)
        lex_result = lex_extract_gh_url(
            item.get("url", "") or "", item.get("text", "") or "",
        )
        diffs = compare_extract_gh_url(py_result, lex_result)
        label = item.get("url") or item.get("text") or "<empty>"
        if diffs:
            failures.append(f"{label!r}: {diffs}")
        else:
            print(f"  OK   py={py_result!r:55} lex={lex_result!r}")
    if failures:
        print("\n[lex-hn] FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n[lex-hn] All cases agree ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
