# lex-poc — OSS Auditor scoring core in lex-lang

A proof-of-concept port of the **pure** parts of OSS Auditor's scoring + verdict
layer to [lex-lang](https://github.com/alpibrusl/lex-lang). The goal: eat our
own dogfood by writing the small but rubric-critical core in the language we
audit, without rewriting the integration surface.

## What's ported

| File | Mirrors | Lines |
|------|---------|-------|
| `src/models.lex` | `oss_auditor/models.py` (verdict-relevant subset) | ~50 |
| `src/scorer.lex` | `oss_auditor/reporter/scorer.py::compute_overall` | ~100 |
| `src/verdict.lex` | `oss_auditor/reporter/verdict.py::compute_verdict` | ~150 |
| `src/main.lex` | smoke runner across the four canonical scenarios | ~80 |

The port preserves:
- **Renormalization fairness** (PR #10): only `Skipped` pillars are
  redistributed; `Unavailable` keeps its weight and contributes 0.
- **Grade cap**: <2 available pillars => max grade is Bronze.
- **Indeterminate verdict**: emitted when fewer than 2 of the 3 axes
  (idea / execution / relevance) carry real data.
- The full 8-verdict matrix + the `pass` default.

Everything is **pure** — no `[io]` effects in scorer/verdict/models. The only
`[io]` annotation is in `main.lex`'s `print_case`, since printing is an effect.
That gives lex's effect system something concrete to sandbox.

## What's NOT ported (and why)

The 80% of OSS Auditor that isn't in this POC:

| Component | Why stubbed |
|-----------|-------------|
| Repo ingestion (`git clone`, language detection) | needs `[fs] [exec]` effects + git |
| GitHub API client (issues, commits, stars) | needs `[net]` + http stdlib |
| LLM backend (Anthropic API / Claude SDK / OpenAI-compatible) | needs `[net]` + JSON streaming |
| Per-language runners (cargo, ruff, npm, govulncheck) | needs `[exec]` + JSON parsing |
| SQLite storage + FastAPI web | needs DB + HTTP server bindings |
| Markdown rendering | string templating, doable but not the interesting bit |

Those are integration glue, not algorithms — the cost/value of porting them
right now is poor.

## Integration plan (not in this PR)

The natural shape is a thin Python shell that delegates the verdict to lex:

```
ingest  ─┐
GitHub  ─┤   build dossier (Python)
LLM     ─┘
                │
                ▼
   ┌──────────────────────┐
   │  lex run verdict.lex │  ← this POC
   │   --json input.json  │
   └──────────────────────┘
                │
                ▼
       SQLite + markdown + web (Python)
```

Two ways to dock it:

1. **CLI bridge** — `pipeline.py` calls `lex run` with a JSON
   `Report` and parses the JSON `Verdict` out. Slow per audit but
   trivially scriptable.
2. **lex serve** — the lex toolchain ships an HTTP/JSON agent API
   server. Long-running daemon, low-latency per call. Better fit
   for the calibration dashboard which re-scores stored audits.

Either path keeps the rubric in one language (lex), the integration
in another (Python), and the boundary at a JSON schema we already
have (Pydantic on one side, lex types on the other).

## Caveats

This POC is **not run end-to-end** against the lex toolchain in this
PR. The lex syntax used here matches the public examples
(`fn ... -> Type { ... }`, `match`, variant types with record
payloads, `let x := y`, `import "..." as alias`), but a few things
are guessed:

- `int_to_float` / `float_to_int` may live under `std.float` or be
  spelled differently.
- `str.concat([...])` and `str.from_float` are educated guesses for
  the stdlib; if the actual API differs, `main.lex` will need a
  one-line tweak.
- Field destructuring in nested patterns
  (`Report({ technical: Technical({ data_status }) })`) follows the
  pattern from the public `Shape` example. If lex requires explicit
  record-field projection (`r.technical.data_status`), the
  destructure helpers in `scorer.lex` and `verdict.lex` collapse to
  plain accessors and the code gets shorter.

The point of this branch is to show **what the rubric looks like in
lex** — small, pure, easy to read, effect-honest. Whatever drift
exists from lex's actual stdlib is a one-pass cleanup, not a design
question.

## Running it (once docked)

```bash
# Type-check
lex check lex-poc/src/main.lex

# Run the demo cases
lex run lex-poc/src/main.lex main

# (Future) score a real audit
lex run lex-poc/src/verdict.lex compute_verdict --json @sample_report.json
```
