# Calibration v0.7 — report

Pre-registered predictions in [`PREDICTIONS.md`](./PREDICTIONS.md).
Raw outputs in [`raw/`](./raw/).

This is the first real calibration round on Rubric. The findings are
mostly **bugs and gaps in the rubric machinery**, not in the rubric
itself — most of the questions we wrote down to answer can't be
answered yet because the data we tried to collect was tainted by
infrastructure issues. Those infrastructure issues are themselves the
v0.7 calibration signal.

## What was supposed to happen

Run 5 diverse repos through full three-pillar audits (`technical` +
`business` + `community`), capture verdict / grade / score, compare
against the predictions written down before any audit ran. Disagreement
between gut and rubric is the signal we built lenses, private-mode,
and the lex cross-check to surface.

## What actually happened

The five audits ran (exit 0 each) but two of three pillars degraded:

- **`business` pillar collapsed**: `claude-agent-sdk` backend returned
  `"Fatal error in message reader: Command failed with exit code 1"`
  on every audit including a self-audit that had worked once at the
  start of the session. Score 0 across all five → no `idea` axis.
- **`community` pillar rate-limited**: without `GITHUB_TOKEN` we hit
  HTTP 403 after the first ~2 audits. Finding surfaces as `info`
  severity but the score crashes to 0.

We pivoted to `--mode private --skip-business`, which works without
GitHub API and without the LLM backend. That exposed a **third bug**.

## Findings

Ordered by severity (critical → positive validation).

### A. CRITICAL — shallow-clone bug breaks private-mode community signals

`rubric/ingestion.py::clone_repo` runs `git clone --depth 1`. Public
mode is fine — community signals come from the GitHub API, not the
local clone. **Private mode** reads `git log` for contributor / recency
/ bus-factor data; on a depth-1 clone, `git log` returns exactly one
commit by exactly one author.

Symptom on every private-mode remote audit:

```
                              T      C   score   grade   verdict          contribs   90d
alpibrusl/lex-lang         98.0   29.0    71.5  silver   pass                   1     1
astral-sh/uv               70.0   29.0    54.2  bronze   pass                   1     1
simonw/datasette           88.0   15.0    59.9  bronze   pass                   1     1
karpathy/llm.c             77.0    0.0    47.4  bronze   indeterminate          1     0
httpie/cli                 74.0    5.0    47.5  bronze   pass                   1     0
```

**Every repo audited as `1 contributor, 100% top-1 bus factor`.** The
private-mode community pillar is fundamentally broken when the input
is a remote URL. It works fine on a path the user already has cloned.

**Fix options:**

1. Detect remote ingestion and switch to `git clone --depth 1000` (or
   `--no-shallow`) when `--mode private` is set. Trade-off: deeper
   clones are slower; for large repos it's the difference between 1s
   and 30s.
2. Detect shallow clones in `internal_metrics.py` (check `is_shallow`
   marker file) and emit a clear `info` finding: "private mode on a
   shallow clone — community signals unreliable; re-clone with full
   history". Don't pretend the score is meaningful.
3. Refuse private mode on remote URLs entirely and require a local
   path. Cleanest but breaks the demo / ergonomic case.

I'd land (1) for v0.7.1 with a knob to opt out for users who care
about clone speed.

### B. HIGH — secret scanner has noisy false positives

The technical pillar's regex-based secret scan flagged uv multiple
times for "Hardcoded Password" — uv obviously doesn't have hardcoded
passwords; the pattern `(?i)password\s*[:=]\s*['\"][^'\"]{8,}['\"]`
catches every `password = "anything-of-eight-chars"` regardless of
context. Test fixtures, example configs, mock auth in docs — all
trip it.

**Concrete impact:** uv landed at technical=70 in the audit; remove
the false-positive hits and it should be ~85+. The whole calibration
sample is biased downward by this.

**Fix options:**

1. Skip directories that are obviously test/example/docs context:
   `tests/`, `test/`, `fuzz/`, `examples/`, `docs/`, `*.test.*`, etc.
2. Add a heuristic that down-grades severity when the matched value
   is a placeholder (`changeme`, `your-password-here`, `xxx`,
   `test-only`, etc.).
3. Make the password pattern require a non-trivial entropy signal
   (mix of letters + digits + symbols) — purely-alphabetic strings
   look like fixtures.

(1) alone probably fixes 90% of the noise. (3) is the cleanest fix
but also the most code.

### C. MEDIUM — GitHub API rate-limit failure has poor UX

When the API returns 403, the community pillar emits an `info`-severity
finding ("GitHub API returned status 403") and the score collapses to
0. The CLI panel then shows `community: 0.0` with no explanation
visible to the user — they have to dig into the JSON envelope or look
at the verdict's "indeterminate" reasoning to figure out what went
wrong.

**Fix:** when the community pillar's data_status is `unavailable`
because of an HTTP 403 specifically, surface a top-level warning at
the same level as the lens hint: "⚠️ GitHub API rate-limited; set
`GITHUB_TOKEN` for accurate community signals." Three-line patch in
`pipeline.py` and `cli.py`.

### D. MEDIUM — `claude-agent-sdk` backend failure is opaque + stateful

All five audits failed the business pillar with the same generic
error ("Fatal error in message reader: Command failed with exit code
1"). Critically, **a self-audit that worked at the start of the
session also failed at the end** — without me changing anything.
Suggests session-state leakage between successive `claude` CLI
invocations, or a process-level resource limit.

`claude-cli` (subprocess) backend timed out at 90s for a single
`alpibrusl/lex-lang` audit. Hard to call this a Rubric bug since
both backends are external dependencies, but the **error reporting
is bad**: the cryptic message gives no actionable hint and the SDK
swallows the upstream error from `claude`.

**Fix:** wrap the backend call's stderr capture properly so the actual
underlying error surfaces in `BusinessReport.summary` instead of the
host's generic SDK panic message. Already mostly there in
`business/analyzer.py` — needs `e.stderr` plumbed through.

### E. POSITIVE — indeterminate-verdict logic correctly refused false positives

PR #10's `indeterminate` verdict: when fewer than 2 of 3 axes have
real data, refuse to commit. With business=0 (LLM failure) and most
community=0 (rate limit), 4 of 5 audits had only the `execution` axis.
The verdict layer correctly returned `indeterminate` for the strict
cases (datasette, llm.c, httpie/cli) and `pass` for the ones with a
non-zero community signal (lex-lang, uv).

**Validation:** the rubric is NOT giving us false positives even
under the worst infrastructure conditions. That's a load-bearing
property of the v0.7 work and it held up.

### F. POSITIVE — technical pillar scoring spread is reasonable

Across 5 deliberately-diverse picks the technical scores spanned
70–98:

| Repo | Technical | Notes |
|------|-----------|-------|
| lex-lang | 98 | Tests + fuzz + composability + license all present |
| datasette | 88 | Mature, well-tested |
| llm.c | 77 | Simple structure, fewer signals |
| httpie/cli | 74 | Mature CLI, conventional |
| uv | 70 | Tanked by false-positive secrets (see Finding B) |

Differentiation is roughly in line with my gut. The uv anomaly is
explained by Finding B; everything else feels right.

## Calibration questions — what we can answer

Reproducing the questions from `PREDICTIONS.md`:

- **Q1 (solo-author handling)**: NOT ANSWERED — needs working
  community pillar to differentiate (1) lex-lang from (3) datasette
  from (4) llm.c. Current data has all of them at the broken
  `contribs=1` baseline.
- **Q2 (stars-as-relevance)**: NOT ANSWERED — needs business pillar
  for the LLM-judged `market_signals` and accurate stars from the
  community pillar.
- **Q3 (mature-vs-novel)**: NOT ANSWERED — needs business pillar for
  `idea` axis to distinguish bet-on-it from solid-commodity.
- **Q4 (cross-check stability)**: PARTIALLY ANSWERED — lex
  cross-check ran on the public-mode pre-pivot audits and didn't
  surface drift on the technical signals. Cross-check on the
  private-mode audits is gated by the LLM business pillar, which is
  broken, so the cross-check skipped.

## Recommended next steps

In priority order:

1. **Fix Finding A** (shallow-clone in private mode) — it's a real
   bug that ships; takes ~30min. PR title: "fix: deepen the clone
   when --mode private".
2. **Fix Finding B** (secret-scanner false positives) — the test-
   directory exclusion is a 5-line change; try it on uv to confirm
   the score recovers from 70 → ~85+.
3. **Fix Finding D's error-surface** (plumb backend stderr through)
   — small change with big debugging payoff for users.
4. **Re-run this calibration** with a real `GITHUB_TOKEN` and a
   working LLM backend. Until that's in place, this calibration round
   is more "rubric infrastructure audit" than "rubric semantic
   calibration".
5. **Once the above are landed**, do a v0.7.1 calibration round
   targeting the four questions above with a 10-repo sample.

The rubric *itself* — pillars, weights, lens behavior, indeterminate
verdict logic — held up where it could be measured. The infrastructure
(ingestion, secret scanning, backend stability, API failure surfacing)
is where the calibration found real work.
