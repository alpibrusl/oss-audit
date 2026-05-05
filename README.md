# Rubric

[![Rubric (technical)](https://img.shields.io/badge/rubric-89.0%2F100_gold-brightgreen)](.rubric.md)
[![CI](https://github.com/alpibrusl/oss-audit/actions/workflows/ci.yml/badge.svg)](https://github.com/alpibrusl/oss-audit/actions/workflows/ci.yml)
[![License: EUPL-1.2](https://img.shields.io/badge/license-EUPL--1.2-blue)](LICENSE)

An audit tool that doesn't stop at giving you a number: it tells you **what to do** with the information — adopt, contribute, fund, wait, or pass. Works on public OSS repos (default) or **on your own private/company repos** with `--mode private` (no network needed; signals come from the local git log + process docs).

> ⚠️ **Status: alpha (v0.5.x).** The API and the rubric may change between minor versions. We're collecting feedback from real audits to calibrate.

## Why another "OSS quality" tool

Existing tools (OpenSSF Scorecard, Snyk, Sonar) measure **process quality** — good for spotting abandonment and vulnerabilities, bad at telling an innovative project apart from a derivative one. Their rubrics implicitly assume "good OSS = large team + long history", which unfairly penalizes the fastest-growing category: **solo-author + AI-agent projects**.

Rubric is built around three convictions:

1. **The post-LLM era changed the game.** One person plus AI agents can ship at the pace of a five-person team. A bus factor of `94% one author` isn't a quality red flag if commits are daily — it's a continuity signal, not an execution one.
2. **Measuring execution isn't enough.** A repo with 92/100 on technical metrics can still be an irrelevant clone. The real question is **idea × execution × relevance**, not execution alone.
3. **A score without an action is noise.** The report has to answer "do I use it? do I adopt it? do I fund it?" depending on who's reading.

## Demo: `lex-lang` audited by Rubric

```
╭───────────────── Rubric ──────────────────╮
│ lex-lang                                       │
│ Score: 62.4/100 (SILVER)                       │
╰────────────────────────────────────────────────╯

Pillars:
  🔧 Technical            98.0    40%
  💡 Thesis & innovation  64.9    35%
  👥 Community             2.0    25%

╭──── Verdict: ahead-of-its-time ────────────────╮
│ Ahead of its time                              │
│ (idea: high · exec: high · relevance: low)     │
│ Brilliant work without a market yet. Track it  │
│ closely; don't bet on it today.                │
╰────────────────────────────────────────────────╯
```

Audience views (excerpt):
- **Developer**: "If you're a contributor, the code is clean and the architecture instructive, but there are no users validating that your work matters yet."
- **CTO**: "Medium-high stack risk. I'd wait until 1.0+ with 2-3 external contributors and a real case study."
- **Investor**: "Conceptually fundable. Pre-seed at most. Main risk: market."

Mind-changers (what would change the assessment):
1. Adoption by ≥1 mainstream AI agent (Claude, ChatGPT, Gemini) using it as a default sandbox.
2. 5+ external contributors with meaningful commits in 6 months.
3. A paper at PLDI/ICFP, or citations in AI safety / code-gen research.
4. The Lex compiler rewritten in Lex itself (dogfooding).

## Installation

```bash
git clone https://github.com/alpibrusl/oss-audit
cd rubric
pip install -e .
```

Optional external tools (boost the technical pillar when present in `$PATH`):

| Tool | For |
|------|-----|
| `gitleaks` | richer secret scanning |
| `cargo` + `cargo-audit` | Rust |
| `ruff`, `pip-audit` | Python |
| `npm` | JS / TS |
| `govulncheck` | Go |

## LLM backend

The thesis & innovation pillar needs an LLM. Three options, auto-detected or forced via `RUBRIC_BACKEND`:

| Option | How | Auth |
|--------|-----|------|
| `claude-agent-sdk` | You have the `claude` CLI installed | **Your Pro/Max subscription** (no API key) |
| `anthropic-api` | `ANTHROPIC_API_KEY=sk-ant-…` | Console billing (separate from your sub) |
| `openai-compatible` | `OPENAI_API_KEY=…` + `OPENAI_BASE_URL=…` | OpenAI / OpenRouter / Groq / Ollama / vLLM / LM Studio |

**Got none of those configured?** Run with `--skip-business` and you'll still get every local signal (technical + community + agent-readiness + composability + programmatic verdict). Without the LLM the verdict will be conservative, but everything else works.

```bash
# Explicit override
export RUBRIC_BACKEND=openai-compatible
export OPENAI_BASE_URL=http://localhost:11434/v1   # local Ollama
export RUBRIC_MODEL=llama3.1:70b
```

A GitHub token is recommended but optional (without one the rate limit is 60 req/h):

```bash
GITHUB_TOKEN=ghp_…
```

## Usage

```bash
# Full audit (technical + thesis + community)
rubric audit https://github.com/alpibrusl/lex-lang

# Local signals only, no LLM nor GitHub API
rubric audit ~/code/my-project --skip-business --skip-community

# JSON envelope for agents / scripts
rubric audit https://github.com/alpibrusl/lex-lang --output json

# "Proposal"-type repos (gists, RFCs, specs)
rubric audit https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

# List / show stored audits
rubric list
rubric show 1

# Generate a shields.io badge for the README
rubric badge                            # markdown for the latest audit
rubric badge 1 --format url             # static URL
rubric badge 1 --format endpoint        # JSON for img.shields.io/endpoint?url=…

# Local web UI to browse history
rubric serve

# Auto-discovery for agents
rubric introspect    # full command tree as JSON

# Audit through a specific perspective (re-weights pillars + reorders findings)
rubric audit . --perspective security    # security engineer's view
rubric audit . --for cto                 # CTO / VP Engineering's view
# perspectives: general | developer | cto | investor | security | maintainer

# Audit a private / internal company repo — no network, no GitHub API
rubric audit ~/code/internal-service --mode private
rubric audit ~/code/internal-service --mode private --for cto
```

## Key concepts

### Artifact type
Before scoring, Rubric classifies the repo:
- **`implementation`** — the code is the artifact (most repos).
- **`proposal`** — the spec / idea is the artifact (gists, RFCs, "ideas with traction"). Auto-detected from gist URLs or from low-LOC + heavy README + traction. In proposal mode the technical pillar is **skipped** and the weights are renormalized.

### Three pillars
| Pillar | Weight | What it measures |
|--------|--------|------------------|
| 🔧 Technical | 40% | Tests, test density, fuzz / property tests, CI, secrets, vulns, lint, license, **composability** (CLI / library / MCP / HTTP / workspace) |
| 💡 Thesis & innovation | 35% | Problem clarity, ambition-vs-execution gap, differentiation, market signals, **intellectual contribution** (citable as future prior art?) |
| 👥 Community | 25% | Stars / forks / contributors, **velocity-per-author** (AI-era signal), recency, agent-readiness (CLAUDE.md, .cli/, mcp.json, …), bus factor (as context, not as punishment) |

### Verdict (advisor layer)
A combination of three axes (idea × execution × relevance, each `low`/`medium`/`high`) maps to one of 8 verdicts:

| Verdict | When | Action |
|---------|------|--------|
| `bet-on-it` | high / high / high | Adopt, contribute, invest |
| `worth-helping` | high / low / high+ | Good idea, weak execution → fork, fund |
| `promising-prototype` | high / med / med | Watch, revisit in 3 months |
| `ahead-of-its-time` | high / high / **low** | Track, don't bet today |
| `solid-commodity` | low / high / high+ | Adopt if you need it; no upside |
| `skill-in-search` | low / high / low | Talent is reusable; the project isn't |
| `incomplete-thesis` | medium / low / low | Not enough signal |
| `pass` | (default) | Skip |

Each verdict ships pre-baked actions for developer / CTO / investor.

### Audience views
Every audit (with the LLM enabled) emits three short paragraphs based on the **same evidence** but framed for the reader:
- **Developer**: do I use it in prod? do I contribute? do I learn from it?
- **CTO / VP-Eng**: adopt / pilot / wait / pass + stack risk + is the team hireable?
- **Investor**: fundable / stage match + risk (technical / market / team)

### Public vs private mode
The audit's third pillar can come from two sources:

- **`--mode public`** (default): GitHub REST API — stars, forks, contributors, public issues, public bus factor. Requires `GITHUB_TOKEN` for any non-trivial use.
- **`--mode private`**: local git log + repo files only — no network. Reads `git log` for contributor patterns / recency / bus factor, and scans for `CODEOWNERS`, `CONTRIBUTING.md`, PR templates, ADR folders (`docs/adr/` etc.), and runbook folders (`runbooks/`, `docs/runbooks/`). Designed for company-internal repos where stars/forks are meaningless and the signals that matter are review routing, decision documentation, and team-health.

Mode is **orthogonal to the perspective lens** — `--mode private --for cto` is a CTO's view of an internal repo.

### Perspective lenses
The audience views are LLM prose. The `--perspective` flag goes a layer deeper: it **reweights the pillars and reorders findings** programmatically, so the same audit returns a different score and a different "what to look at first" for each role.

| Perspective | Weights (T / B / C) | Top finding categories |
|-------------|--------------------|------------------------|
| `general` (default) | 40 / 35 / 25 | severity-only |
| `developer` | 55 / 20 / 25 | testing → process → quality |
| `cto` | 40 / 20 / 40 | legal → security → community |
| `investor` | 20 / 55 / 25 | community → legal → security |
| `security` | 65 / 10 / 25 | security → dependencies → process |
| `maintainer` | 45 / 15 / 40 | testing → process → community |

The `security` lens additionally **downgrades** any positive verdict (`bet-on-it`, `worth-helping`, …) when there's an unfixed critical finding in the technical pillar, with a "fix criticals first" annotation.

### Counterfactuals — "what would change my mind"
Two kinds:
- **Programmatic**: simulate +30 on the weakest pillar; if the verdict changes, report it.
- **LLM `mind_changers`**: falsifiable observable signals — *"if X shows up in N months, my assessment changes."*

## Architecture

```
rubric/
├── cli.py                      # `rubric` (ACLI-compliant)
├── pipeline.py                 # End-to-end orchestrator
├── ingestion.py                # Clone/local + language detection + classifier
├── models.py                   # Pydantic schemas
├── technical/
│   ├── runner.py               # Technical score
│   ├── universal.py            # Secrets, CI, tests, fuzz, property, license
│   ├── composability.py        # CLI / library / MCP / HTTP / workspace
│   └── lang_runners.py         # cargo, ruff, npm, govulncheck, ...
├── business/
│   ├── context_builder.py      # Rich dossier (NOT just the README)
│   ├── analyzer.py             # Prompt + JSON schema + parser
│   └── backends.py             # Anthropic API / Claude SDK / OpenAI-compatible
├── community/
│   ├── github_metrics.py       # Stars / forks / velocity / bus factor
│   └── agent_readiness.py      # CLAUDE.md / AGENTS.md / .cli/ / mcp.json / ...
├── reporter/
│   ├── scorer.py               # Aggregate score (renormalizes active pillars)
│   ├── verdict.py              # 8 verdicts + programmatic counterfactuals
│   ├── badge.py                # Shields.io static / endpoint / markdown
│   └── markdown.py             # Report rendering
├── storage/db.py               # Local SQLite
└── web.py                      # FastAPI for history
```

## Roadmap

- **v0.6 — Calibration with real data.** Tune thresholds and weights against ≥10 audits of diverse projects. Until then the verdict thresholds are reasonable approximations, not calibrated truth.
- **v0.7 — More backends + more languages.** Bedrock, Vertex, Cohere; runners for Java / Kotlin / Swift.
- **v0.8 — Temporal comparison.** Diff between two audits of the same repo (did it improve? did it stall?).
- **v0.9 — "Monitor" mode.** Audit each PR in CI; alert when the verdict changes.

## Contributing

Best first PR: add a detector to `rubric/community/agent_readiness.py` or `rubric/technical/composability.py`. They're self-contained modules and easy to test.

```bash
pip install -e .
python tests/smoke_test.py
rubric audit . --skip-business --skip-community  # eat your own dogfood
```

Issues are welcome for:
- False positives / negatives in artifact-type classification (`implementation` vs `proposal`).
- Verdict threshold calibration (40 / 70).
- Repos where the rubric returns a verdict that feels clearly wrong — those are gold.

## License

[EUPL-1.2](LICENSE) — short-form notice per Article 12 of the license.
