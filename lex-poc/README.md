# lex-poc — OSS Auditor scoring core in lex-lang

A proof-of-concept port of the **pure** parts of OSS Auditor's scoring + verdict
layer to [lex-lang](https://github.com/alpibrusl/lex-lang). Eats our own
dogfood: the rubric we use to audit lex-lang is now itself written in lex.

## Status: type-checks and runs

```
$ lex check lex-poc/src/oss_audit.lex
ok

$ lex run --allow-effects io lex-poc/src/oss_audit.lex main
only-technical  | score=90   grade=bronze verdict=indeterminate bands=(idea=n/a, exec=high, rel=n/a)
tech+business   | score=87.7 grade=gold   verdict=pass          bands=(idea=high, exec=high, rel=n/a)
full-3-axes     | score=85.8 grade=gold   verdict=bet-on-it     bands=(idea=high, exec=high, rel=high)
biz-unavailable | score=56   grade=bronze verdict=pass          bands=(idea=n/a, exec=high, rel=high)
```

All four scenarios produce **byte-identical scores, grades, and verdicts**
to the Python reference (`oss_auditor/reporter/{scorer,verdict}.py`) on the
same fixtures.

## What's ported

A single module — `lex-poc/src/oss_audit.lex` — covering the rubric-critical
layer:

- **Renormalization fairness** (PR #10): only `Skipped` pillars are
  redistributed; `Unavailable` keeps its weight and contributes 0.
- **Grade cap**: <2 available pillars => max grade Bronze.
- **Indeterminate verdict** when fewer than 2 of the 3 axes
  (idea / execution / relevance) carry real data.
- The full 8-verdict matrix + the `pass` default.

Everything is **pure** — the only `[io]` effect is in `main`, which is
explicitly granted via `--allow-effects io`.

## What's NOT ported (and why)

The 80% of OSS Auditor that's integration glue, not algorithm:

| Component | Why stubbed |
|-----------|-------------|
| Repo ingestion (`git clone`, language detection) | needs `[fs] [proc]` + git wrappers |
| GitHub API client (issues, commits, stars) | needs `[net]` |
| LLM backend (Anthropic API / Claude SDK / OpenAI-compatible) | needs `[net]` |
| Per-language runners (cargo, ruff, npm, govulncheck) | needs `[proc]` |
| SQLite + FastAPI web UI | needs DB binding + HTTP server |
| Markdown rendering | string templating, doable but uninteresting |

These are integrations, not rubric. Their cost/value to port now is poor.

## Lessons learned wiring this up

A few lex-isms worth noting (and an entry on the radar of "nice things to
file as lex issues"):

- **No local imports yet.** `import "std.io" as io` works; `import "./models" as m`
  doesn't appear to be wired. The whole POC lives in one file as a result.
- **Nominal record types are strict.** A function declared to return
  `Community` will accept an anonymous `{ score: ..., data_status: ... }` at the
  return position, but won't unify it with `Community` when used as a field of
  an outer record literal or as a function argument. Workaround: explicit
  `mk_*` constructor functions for each record type. The `mk_*` pattern in the
  POC is the result.
- **Field declaration order matters.** Lex normalizes record literal fields
  alphabetically during inference, so the declared fields in `type Foo = {...}`
  must also be alphabetical or the structural/nominal compatibility check fails.
- **Trailing commas in fn parameter lists are rejected.** Match arms allow them;
  parameter lists don't.
- **No record-pattern matching on nominal types.** `match b { { idea: High, ... } => ... }`
  fails when `b :: Bands`. The POC dispatches the verdict matrix by encoding the
  band triple as a 3-char string (`"HHL"`, etc.) and matching on that — concise
  and avoids the limitation.
- **Comments are `#`, not `//`.**

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

Either path keeps the rubric in one language (lex), the integration
in another (Python), and the boundary at a JSON schema we already have.

## Running it locally

Requires the lex toolchain on `$PATH`:

```bash
git clone --depth 1 https://github.com/alpibrusl/lex-lang.git /tmp/lex-lang
(cd /tmp/lex-lang && cargo build --release)
export PATH="/tmp/lex-lang/target/release:$PATH"

lex check lex-poc/src/oss_audit.lex
lex run --allow-effects io lex-poc/src/oss_audit.lex main
```

About 60 seconds to build the toolchain on a fresh box, then sub-second to
type-check and run the POC.
