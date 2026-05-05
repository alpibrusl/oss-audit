# Calibration v0.7 — predictions (pre-registered)

Selected 5 repos with deliberately diverse shapes. Predictions written
**before** running any audits, so the post-audit report can honestly
compare gut-vs-rubric without fit-to-data.

Pillar weights and grade thresholds are at v0.7 defaults
(`general` lens, `public` mode, full three-pillar audit).

| # | Repo | Shape | Prediction (verdict / grade) | Why |
|---|------|-------|-------------------------------|-----|
| 1 | `alpibrusl/lex-lang` | Solo-author + AI-era new language | `ahead-of-its-time` / **silver** | Strong technical work, novel thesis, no real market yet. Matches the README demo (62.4 silver). |
| 2 | `astral-sh/uv` | Funded team, Rust-based Python tooling | `bet-on-it` / **gold** | Real adoption, strong team, well-known. Should be easy positive across all three pillars. |
| 3 | `simonw/datasette` | Solo author, mature (years), real users | `bet-on-it` / **gold** | The interesting solo case: high quality + long-running + actual users. Tests whether the rubric credits sustained solo work. |
| 4 | `karpathy/llm.c` | Viral + single-person + learning artifact | `ahead-of-its-time` or `promising-prototype` / **silver** | Lots of stars but low pull (it's a learning repo, not a product). Tests whether high stars alone fool the community pillar. |
| 5 | `httpie/cli` | Mature, popular CLI, long history | `solid-commodity` or `bet-on-it` / **gold** | Established commodity — does its job, low novelty by now. Tests whether maturity-without-novelty surfaces as `solid-commodity`. |

## Calibration questions

The 5 picks deliberately probe specific rubric beliefs:

- **Q1 (solo-author handling)**: do (1), (3), and (4) — all solo or near-solo — produce different verdicts based on adoption and maturity, or does the rubric over-penalize solo authorship in a way the `is_solo_active` finding doesn't fully repair?
- **Q2 (stars-as-relevance)**: does (4) `llm.c` (viral but learning) score similarly to (1) `lex-lang` (novel but not viral) on the relevance axis? If so, the LLM-judged `market_signals` is doing its job; if (4) gets a much higher relevance score from raw star count, the rubric is being fooled by viral-as-validation.
- **Q3 (mature-vs-novel)**: do (2) and (5) both produce `bet-on-it`? If yes, the matrix isn't distinguishing "fundable / new" from "buy-the-commodity / mature". The `idea` band should differ — (2) is a recent, sharp tool; (5) is a 14-year-old CLI.
- **Q4 (cross-check stability)**: do all 5 pass the lex cross-check? Disagreement on any of them means the rubric drifted between Python and lex implementations during the v0.7 work.

Running with:
```
RUBRIC_LEX_CROSS_CHECK=1 rubric audit <url>
```

Default lens (`general`), default mode (`public`). Saves to `~/.rubric/audits.db`.
The post-audit report (`REPORT.md`) compares actual vs prediction and surfaces
disagreements as the v0.7 calibration signal.
