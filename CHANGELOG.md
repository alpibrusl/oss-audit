# Changelog

All releases follow [SemVer](https://semver.org). The API and rubric are unstable until `1.0.0`.

## v0.5.0 — Advisor layer

- **Verdict layer**: programmatic, with 8 verdicts (bet-on-it, worth-helping, ahead-of-its-time, solid-commodity, skill-in-search, promising-prototype, incomplete-thesis, pass) based on idea × execution × relevance.
- **Audience views**: the LLM produces separate paragraphs for developer / CTO / investor from the same evidence.
- **Counterfactuals**: programmatic ("if X went up to Y, the verdict changes") plus LLM `mind_changers` (falsifiable signals that would change the assessment).
- **Thesis & innovation**: the former "business" pillar, renamed and extended with a `intellectual_contribution` sub-score and new `novelty_summary` / `nearest_prior_art` fields.
- Verdict + audience views + counterfactuals serialize into the JSON envelope and render in markdown.

## v0.4.0 — AI-era signals

- **Repo-type classifier** (`implementation` vs `proposal`). Gist URLs are auto-detected as proposals; the technical pillar is skipped.
- **Velocity-per-author** in the community pillar — solo+AI shipping no longer scores the same as a large team with the same cadence.
- **Test density + fuzz / property tests**: detection of `cargo-fuzz`, `atheris`, `proptest`, `hypothesis`, etc., with a dedicated bonus.
- **Composability**: new technical sub-score (0–10) that detects CLI binary / library export / MCP manifest / HTTP server / workspace. Walks one level into `crates/`, `sdks/`, `packages/`, `apps/`, `services/`, `modules/` to cover monorepos.
- **Score renormalization**: skipped pillars (`--skip-*`) no longer drag the total down.

## v0.3.0 — Multi-backend LLM + badge

- **Pluggable backends**: `anthropic-api`, `claude-agent-sdk` (Pro/Max subscription), `claude-cli`, `openai-compatible` (OpenAI / OpenRouter / Groq / Ollama / vLLM / LM Studio).
- **Model in the report**: `BusinessReport.backend` and `.model` capture which backend and which model actually responded.
- **Shields.io badge**: `rubric badge` emits markdown / static URL / endpoint JSON.
- **Stop-hook awareness**: the SDK backend filters out messages injected by host hooks (Claude Code) that derail the conversation.

## v0.2.0 — Community pillar rebalance

- Bus factor leaves the score as a lever; it surfaces as a contextual finding (`high` if solo + abandoned, `info` if solo + active).
- **Agent-readiness** (0–10) detects `CLAUDE.md` / `AGENTS.md` / `.cursorrules` / `.cli/` / `mcp.json` / `examples/`.
- Reweighting: stars 25 / velocity 30 / recency 15 / agent-readiness 10 / diversity 10 / releases 5 / close-time 5.

## v0.1.0 — Initial

- ACLI-compliant CLI (`rubric`).
- Three pillars: technical (40%), LLM-driven business (35%), community (25%).
- Local SQLite storage + FastAPI web for history.
- LICENSE EUPL-1.2.
