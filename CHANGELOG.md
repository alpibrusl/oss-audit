# Changelog

Todas las versiones siguen [SemVer](https://semver.org). API y rúbrica son inestables hasta `1.0.0`.

## v0.5.0 — Advisor layer

- **Verdict layer** programático con 8 veredictos (bet-on-it, worth-helping, ahead-of-its-time, solid-commodity, skill-in-search, promising-prototype, incomplete-thesis, pass) basado en idea × ejecución × relevancia.
- **Audience views**: el LLM produce párrafos separados para developer / CTO / investor desde la misma evidencia.
- **Counterfactuals**: programáticos ("si X subiera a Y, el verdict cambia") + LLM `mind_changers` (señales falsables que cambiarían la evaluación).
- **Tesis & innovación**: pilar de "negocio" renombrado, con sub-score `intellectual_contribution` y nuevos campos `novelty_summary` y `nearest_prior_art`.
- Verdict + audience views + counterfactuals serializan en el envelope JSON y se renderizan en markdown.

## v0.4.0 — AI-era signals

- **Repo type classifier** (`implementation` vs `proposal`). Gist URLs se detectan automáticamente como proposal; el pilar técnico se omite.
- **Velocity-per-author** en el pilar de comunidad — solo+IA shipping ya no scoredea igual que un equipo grande con la misma cadencia.
- **Test density + fuzz / property tests**: detección de `cargo-fuzz`, `atheris`, `proptest`, `hypothesis`, etc., con bonus dedicado.
- **Composability**: nuevo sub-score técnico (0–10) que detecta CLI binary / library export / MCP manifest / HTTP server / workspace. Walks one level into `crates/`, `sdks/`, `packages/`, `apps/`, `services/`, `modules/` para cubrir monorepos.
- **Score renormalization**: pilares saltados (`--skip-*`) ya no arrastran el total.

## v0.3.0 — Multi-backend LLM + badge

- **Backends intercambiables**: `anthropic-api`, `claude-agent-sdk` (suscripción Pro/Max), `claude-cli`, `openai-compatible` (OpenAI / OpenRouter / Groq / Ollama / vLLM / LM Studio).
- **Modelo en el reporte**: `BusinessReport.backend` y `.model` capturan qué backend y qué modelo realmente respondió.
- **Badge shields.io**: `oss-audit badge` emite markdown / static URL / endpoint JSON.
- **Stop-hook awareness**: el SDK backend filtra mensajes inyectados por hooks del host (Claude Code) que derailan la conversación.

## v0.2.0 — Community pillar rebalance

- Bus factor sale del score como lever; aparece como finding contextual (`high` si solo + abandonado, `info` si solo + activo).
- **Agent-readiness** (0–10) detecta `CLAUDE.md` / `AGENTS.md` / `.cursorrules` / `.cli/` / `mcp.json` / `examples/`.
- Reweighting: stars 25 / velocity 30 / recency 15 / agent-readiness 10 / diversity 10 / releases 5 / close-time 5.

## v0.1.0 — Initial

- CLI ACLI-compliant (`oss-audit`).
- Tres pilares: técnico (40%), negocio LLM-driven (35%), comunidad (25%).
- Storage SQLite local + web FastAPI para histórico.
- LICENSE EUPL-1.2.
