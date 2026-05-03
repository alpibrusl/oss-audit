# lex-poc — OSS Auditor scoring core in lex-lang

A proof-of-concept port of the **pure** parts of OSS Auditor's
scoring + verdict layer to [lex-lang](https://github.com/alpibrusl/lex-lang).
Eats our own dogfood: the rubric we use to audit lex-lang is now
itself written in lex.

## Status: type-checks and runs

```
$ lex check lex-poc/src/main.lex
ok
required effects: io
hint: lex run --allow-effects io lex-poc/src/main.lex <fn> [args]

$ lex run --allow-effects io lex-poc/src/main.lex main
only-technical  | score=90   grade=bronze verdict=indeterminate bands=(idea=n/a, exec=high, rel=n/a)
tech+business   | score=87.7 grade=gold   verdict=pass          bands=(idea=high, exec=high, rel=n/a)
full-3-axes     | score=85.8 grade=gold   verdict=bet-on-it     bands=(idea=high, exec=high, rel=high)
biz-unavailable | score=56   grade=bronze verdict=pass          bands=(idea=n/a, exec=high, rel=high)
```

All four scenarios produce **byte-identical scores, grades, and verdicts**
to the Python reference (`oss_auditor/reporter/{scorer,verdict}.py`) on
the same fixtures.

## Layout

| File | Role |
|------|------|
| `lex-poc/src/oss_audit.lex` | Library: types + scorer + verdict (no `[io]`). |
| `lex-poc/src/main.lex` | Demo runner: imports `./oss_audit` and prints four scenarios. |

The library and runner are split. We don't split the library further (e.g.
into `models` / `scorer` / `verdict`) because lex's MVP local imports
mangle types per-importer — `scorer.m.Report` and `verdict.m.Report`
become distinct nominal types even when both files `import "./models"`.
See "Open lex limitations" below.

## What's ported

- **Renormalization fairness** (PR #10): only `Skipped` pillars are
  redistributed; `Unavailable` keeps its weight and contributes 0.
- **Grade cap**: <2 available pillars => max grade Bronze.
- **Indeterminate verdict** when fewer than 2 of the 3 axes
  (idea / execution / relevance) carry real data.
- The full 8-verdict matrix + the `pass` default.

Pure throughout — the only `[io]` is in `main.lex::main`, and
`lex check` now surfaces that grant up front (no need to `lex run`
once just to learn the requirement).

## Lex fixes that landed in upstream PRs #83–#86

After filing the issues, the lex team shipped four improvements that
let us drop most of the workarounds the previous POC had to wear:

| Workaround the old POC had | Fixed by |
|----------------------------|----------|
| Single-file consolidation | local file imports (#83) — split into library + runner |
| `mk_*` constructor wrappers around every nominal record | record literals coerce at every position (#86) — gone |
| Alphabetical field declaration order | (#86) — restored logical grouping |
| Trailing commas stripped from fn params/args | trailing commas everywhere (#84) — restored |
| Trial-and-error to discover `--allow-effects io` | `lex check` reports required grants (#85) |

Net change: 410 LOC across two files instead of 370 LOC in one
single defensive file, and reads like idiomatic lex.

## Open lex limitations (still worked around)

Two things are still pending:

- **Diamond-import duplication.** When `main.lex` imports both
  `scorer` and `verdict`, and each of those imports `models`, lex's
  MVP loader mangles them as `main.scorer.m.Report` and
  `main.verdict.m.Report` — distinct nominal types. The
  `diamond_keeps_shared_module_once` test in lex-syntax flags this
  as known MVP behavior pending "store-native imports / SigId
  stability". For now we keep all types in the library file so
  every consumer references them through a single alias path.
- **Record-pattern matching on nominal types.** `match b { { idea: High, ... } => ... }`
  against `b :: Bands` (a nominal record) fails with
  `expected: record, got: core.Bands; context: in record pattern`.
  PR #86 documented "pattern" as a covered position, but in
  practice it covers constructor patterns (`Foo({ ... })`), not
  bare record patterns. The verdict matrix uses nested per-axis
  matches instead — works fine, slightly more verbose than
  the structural form would be.

## What's NOT ported (and why)

The 80% of OSS Auditor that's integration glue, not algorithm:

| Component | Why stubbed |
|-----------|-------------|
| Repo ingestion (`git clone`, language detection) | needs `[fs] [proc]` + git wrappers |
| GitHub API client | needs `[net]` |
| LLM backend (Anthropic / Claude SDK / OpenAI-compatible) | needs `[net]` |
| Per-language runners (cargo, ruff, npm, govulncheck) | needs `[proc]` |
| SQLite + FastAPI web UI | needs DB binding + HTTP server |
| Markdown rendering | string templating, doable but uninteresting |

These are integrations, not rubric.

## Integration plan (not in this PR)

The natural shape is a thin Python shell that delegates the verdict to lex:

```
ingest   ─┐
GitHub   ─┤   build dossier (Python)
LLM      ─┘
                │
                ▼
   ┌──────────────────────────────┐
   │ lex run oss_audit.lex        │  ← this POC
   │   compute_verdict --json …   │
   └──────────────────────────────┘
                │
                ▼
       SQLite + markdown + web (Python)
```

Two ways to dock it:

1. **CLI bridge** — `pipeline.py` calls `lex run` with a JSON-encoded
   `Report` and parses the JSON `Verdict` out. Slow per audit but
   trivially scriptable.
2. **`lex serve`** — the lex toolchain ships an HTTP/JSON agent API
   server. Long-running daemon, low-latency per call. Better fit for
   the calibration dashboard which re-scores stored audits.

## Running it locally

Requires the lex toolchain on `$PATH`:

```bash
git clone --depth 1 https://github.com/alpibrusl/lex-lang.git /tmp/lex-lang
(cd /tmp/lex-lang && cargo build --release)
export PATH="/tmp/lex-lang/target/release:$PATH"

lex check lex-poc/src/main.lex
lex run --allow-effects io lex-poc/src/main.lex main
```

About 60 seconds to build the toolchain on a fresh box, then sub-second
to type-check and run the POC.
