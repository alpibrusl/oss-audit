# Lex Pilot — State of the Port

Generated 2026-05-09. Snapshot of where the lex re-implementation
of rubric stands after ~15 PRs.

## TL;DR

The pilot covers every **calibration-sensitive surface** of rubric
via lex cross-checks that fire on every audit. The pilot is **not**
a drop-in lex engine — Python still drives the pipeline, and the
remaining unported surface (HTTP server, full markdown rendering,
storage) is bounded by lex stdlib gaps that aren't on lex's roadmap.

The first real calibration round (this report) caught one real bug
that single-language smoke tests had missed.

## Coverage

### Cross-checked on every audit (calibration-drift catches)

13 cross-checks fire when `RUBRIC_LEX_CROSS_CHECK=1` is set:

| Check | Source | Validates |
|---|---|---|
| `rubric` | `adapter.lex` + `scorer.lex` + `verdict.lex` | Overall score / grade / verdict code |
| `ingest` | `ingestion.lex` | GitHub + gist URL parsers |
| `ingest-io` | `ingestion_io.lex` | Language detection + doc-chars + classify decision |
| `tech-score` | `tech_score.lex` | Technical pillar 13-input weighted sum |
| `composability` | `composability.lex` | 5 surface detectors + monorepo subdir traversal |
| `lang-dispatch` | `lang_dispatch.lex` | Which language runners to invoke (5% LOC threshold) |
| `community-score (public/private)` | `community_score.lex` | Community pillar scoring, both modes |
| `agent-readiness` | `agent_readiness.lex` | 6 agent-context detectors |
| `universal` | `universal.lex` | License classification, SECURITY.md, manifest license, CI security tools |
| `lens-score` | `lens_scorer.lex` | Lens-aware pillar weight remix (5 perspectives) |
| `lens-guard` | `lens_scorer.lex` | Security-perspective critical-finding downgrade |
| `gh-metrics` | `gh_metrics.lex` | Bus factor, commits-90d, has-releases derivations |
| `business-score` | `business_score.lex` | Business pillar 6-input weighted sum |

### Working ports without cross-check (would double cost)

| Module | Source | Status |
|---|---|---|
| Python runner | `run_python.lex` | ruff + pip-audit via std.process |
| Rust runner | `run_rust.lex` | cargo audit + clippy (JSONL parsed) |
| JS runner | `run_js.lex` | npm audit |
| HN URL extractor | `hn_source.lex` | Same regex + validation as Python |
| HN net probe | `hn_source_net.lex` | std.http smoke test |
| Badge SVG | `badge.lex` | shields.io URL + endpoint + markdown |
| Markdown scaffold | `markdown_scaffold.lex` | Title + meta + verdict block (top-of-fold only) |

Each has a stand-alone parity test in `tests/lex_*_test.py`.

### Not ported (and why)

| Module | Blocker |
|---|---|
| `web.py` HTTP server | No `std.http` *server* primitive in lex (only client) |
| `days_since_iso` / `avg_close_days` | `std.datetime.Duration` is one-way — constructors but no accessors (`duration_seconds` exists, no `to_seconds`) |
| Full `markdown.py` (per-pillar findings, audience views, snapshot table, footer) | Pure mechanical translation, low cross-check ROI (presentation drift, not calibration drift) |
| Go runner | `govulncheck` not on test image; pattern is identical to Rust |
| Full `fetch_hn_candidates` | Item-by-item fanout, no audit-time pressure to port |
| `storage/db` (sqlite) | Low ROI; `std.sql` exercise only |

## Calibration round results

Five public repos audited with `RUBRIC_LEX_CROSS_CHECK=1`:

| Repo | Lang mix | Overall | Notes |
|---|---|---|---|
| `pallets/click` | Python | 50.6 bronze (pass) | All 8 cross-checks agreed |
| `BurntSushi/xsv` | Rust | 48.0 bronze (indeterminate) | All 8 agreed |
| `sindresorhus/p-limit` | JS + TS | 37.5 fail (indeterminate) | All 8 agreed **after fix** |
| `bazelbuild/bazel-skylib` | Go + C++ | 50.5 bronze (indeterminate) | All 8 agreed **after fix** |
| `alpibrusl/oss-audit` (self) | Python | 57.4 bronze (pass) | All 8 cross-checks agreed |

(`community-score` and `gh-metrics` don't appear because the public
runs had no `GITHUB_TOKEN`; the API failed early and no signals were
stashed. Running with a token would add 2 more checks per audit.)

(`business-score` doesn't appear because audits ran with
`skip_business=True` to avoid the LLM call.)

### Bug caught

**`ingest-io` silently returned `None` on any repo with 2+ known
languages.** Lex `_insert_sorted` in `ingestion_io.lex` did
`el < hl` on `Str` to sort languages alphabetically — but lex
stdlib (v0.5) has no `<` ordering on `Str`, only `==`. The lex
runtime crashed with `Num op: Str("JavaScript") Str("TypeScript")`,
the bridge swallowed the failure as None, and the cross-check was
skipped silently.

Single-language smoke tests never tripped it. The diverse-repo
calibration round surfaced it on the first multi-language repo
(`p-limit`: JS + TS).

**Fix** (commit alongside this report): drop the lex-side sort.
The cross-check bridge already sorts both sides alphabetically
before comparing, so insertion order is fine.

**Pattern this fits**: silent-skip cross-checks are dangerous
exactly because they look like a pass. A future hardening pass
should distinguish "skipped because lex isn't installed" from
"skipped because lex crashed" and surface the latter.

## Lex stdlib gaps that hit us

Documented here so the lex team can prioritize if any of them
matter to other consumers.

| Gap | Where it bit | Workaround used |
|---|---|---|
| No `<` `>` `<=` `>=` on `Str` | Sort languages in `ingestion_io.lex` | Drop lex-side sort; bridge sorts both |
| No `Duration` extractors (`to_seconds`, etc.) | `days_since_iso` / `avg_close_days` | Date math not ported |
| Tuples don't decode from JSON CLI args | `lang_dispatch.lex` initial draft | Switched inputs to records |
| No `proc.which` | Tool detection in all runners | `_has(cmd)` runs `cmd --version` |
| No HTTP server primitive | `web.py` | Not portable |
| No HTML / templating story | Markdown / web | Hand-rolled strings; verbose but works |
| Whole-file effect envelope | Mixing pure + effectful code | Split into sibling files (e.g. `hn_source.lex` / `hn_source_net.lex`) |
| `parse_strict` strict on type AND presence | `package.json` field extraction | Substring detection fallback |
| Per-module-private helpers not supported | Runner code reuse | Duplicated `_spawn_in` / `_has` across 3 runner files |

## Strategic read: lex's direction

v0.4.0 + v0.5.0 together shipped seven major features. **All seven**
are in the agent-VCS layer (op-log packfiles, GC, delta-encoded
stages, multi-writer CAS, attestation-cascade migration, walk-back
producer-block gate, `lex op pull`). Zero new stdlib modules in
that span.

This isn't a critique — it's a signal. Lex is positioning itself
as **the storage substrate where multiple AI agents collaborate on
code**, not as a general-purpose scripting language with a wide
stdlib. The gaps we hit (HTTP server, templating, date extractors)
are unlikely to be filled by lex without specific asks.

A natural angle for rubric to align with that direction: publish
audit results as `lex` attestations into an op-log. The
producer-block gate (#256/#248) is conceptually adjacent to what
rubric does. **Different product from a port, but the bones are
there now.**

## Recommendations

1. **Ship the bug fix from this round.** The
   `_insert_sorted` removal goes in this same PR.

2. **Freeze the port surface here.** The 13 cross-checks cover the
   calibration-sensitive layer; remaining items are either blocked
   on lex stdlib gaps or low-ROI.

3. **Harden "silent skip" detection.** The bridge should
   distinguish "lex crashed" (suppressed today as `None`) from
   "lex not installed" and surface the former as a yellow finding.
   Otherwise future bugs of the same shape will hide.

4. **File the stdlib gaps as a single issue** to lex. Even if
   they don't ship, having them documented upstream means a future
   pilot consumer doesn't re-discover them.

5. **Decide on the next phase out-of-band.** Three real options:
   - Keep the pilot as a permanent test harness (current state)
   - Push toward lex-as-primary by filling the unported gaps (HTTP
     server is the long pole; needs lex upstream work)
   - Prototype the agent-VCS angle — rubric publishes audit results
     as lex attestations
