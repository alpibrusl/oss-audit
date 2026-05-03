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
| `lex-poc/src/models.lex`  | Types only. No imports. |
| `lex-poc/src/scorer.lex`  | `compute_overall` + grade cap. Imports `./models`. |
| `lex-poc/src/verdict.lex` | `compute_verdict` + 8-verdict matrix. Imports `./models`. |
| `lex-poc/src/main.lex`    | Demo runner. Imports `./models`, `./scorer`, `./verdict`. |

The diamond (`main` → `scorer`/`verdict` → `models`) resolves cleanly
since lex 0.1.0 + #91 — `m.Report` is the same nominal type whether
referenced from `scorer.lex` or `verdict.lex`.

## What's ported

- **Renormalization fairness** (PR #10): only `Skipped` pillars are
  redistributed; `Unavailable` keeps its weight and contributes 0.
- **Grade cap**: <2 available pillars => max grade Bronze.
- **Indeterminate verdict** when fewer than 2 of the 3 axes
  (idea / execution / relevance) carry real data.
- The full 8-verdict matrix as a flat 12-row record-pattern match
  on `Bands` (idea / execution / relevance triple).

Pure throughout — the only `[io]` is in `main.lex::main`, and
`lex check` surfaces that grant up front.

## Lex fixes used

The shape of this POC tracks six upstream lex improvements; the
issues were filed during the first port and the fixes landed
in PRs #83–#91:

| Workaround needed before fix | Fixed by |
|------------------------------|----------|
| Single-file consolidation | local file imports (#83) |
| Single-library workaround for diamond imports | per-file content-hash mangling so the same module collapses to one nominal type (#91) |
| `mk_*` constructor wrappers around every nominal record | record literals coerce at every position (#86) |
| Alphabetical field declaration order | (#86) |
| 3-char band-key string match (`"HHH"`, `"HML"`, …) → nested per-axis match | bare record patterns match nominal record aliases (#90) |
| Trailing commas stripped from fn params/args | trailing commas everywhere (#84) |
| Trial-and-error to discover `--allow-effects io` | `lex check` reports required grants (#85) |

The current POC reads like idiomatic lex, not defensive code.

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

## Cross-check from the Python pipeline

`oss_auditor/lex_cross_check.py` invokes the lex POC on every audit
when the `OSS_AUDITOR_LEX_CROSS_CHECK=1` env var is set and the
`lex` binary is on `$PATH`:

```bash
OSS_AUDITOR_LEX_CROSS_CHECK=1 oss-audit audit . --skip-business --skip-community
# ...
# ⚖️  Verdict and counterfactuals...
# ✓ lex cross-check: agree
```

The boundary is `lex-poc/src/adapter.lex::cross_check`, which takes
a flat primitive-only record (the `$variant` JSON convention isn't
wired for `lex run` arguments yet — see open lex issue) and returns
a pipe-delimited `<verdict_code>|<grade>|<score>`. The Python side
parses that string and compares against its own `compute_verdict` /
`compute_overall` outputs.

A disagreement is logged but does NOT fail the audit — that's
deliberate. The two implementations are meant to be a calibration
cross-check: drift between them is the v0.6 calibration signal.

## Integration plan (not in this PR)

The natural shape is a thin Python shell that delegates the verdict to lex:

```
ingest   ─┐
GitHub   ─┤   build dossier (Python)
LLM      ─┘
                │
                ▼
   ┌──────────────────────────────┐
   │ lex run main.lex             │  ← this POC
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
