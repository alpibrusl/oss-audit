# Contributing to OSS Auditor

We're at `v0.5.x` (alpha). The most useful feedback right now isn't code — it's **audits where you think the verdict is wrong**. Those cases are what calibrate the rubric.

## Setup

```bash
git clone https://github.com/alpibrusl/oss-audit
cd oss-audit
pip install -e .

# Sanity check
python tests/smoke_test.py
oss-audit audit . --skip-business --skip-community --no-save
```

## Welcome PR types (ranked by value)

### 1. "Wrong verdict" reports

If you audit a repo and the verdict feels clearly wrong, open an issue with the **"False verdict report"** template stating: repo URL, the verdict the tool returned, the verdict you believe is correct, and why. Those cases drive the v0.6 calibration.

### 2. Agent-readiness detectors

`oss_auditor/community/agent_readiness.py` detects files like `CLAUDE.md`, `AGENTS.md`, `.cli/`, `mcp.json`. If you know another ecosystem convention (e.g. `.devin/`, `.aider.conf`, `.copilot/`...), add a category following the existing pattern.

### 3. Composability detectors

`oss_auditor/technical/composability.py` recognizes CLI / library / MCP / HTTP server / workspace in Python, Rust, Node, and Go. Coverage is missing for Java, Kotlin, Swift, Ruby, and Elixir.

### 4. Language runners

`oss_auditor/technical/lang_runners.py` defines the pattern. We need runners for Java (Maven + spotbugs), Kotlin (gradle + ktlint), Swift (swiftlint), Ruby (bundler-audit + rubocop), and Elixir (mix audit + credo).

### 5. Bug fixes and refactors

Before a large refactor, open an issue to discuss — the scoring weights and the verdict rubric are fragile and not yet calibrated.

## Workflow

1. Fork and create a branch: `git checkout -b feat/my-feature`.
2. Code → tests → smoke (`python tests/smoke_test.py`).
3. Self-audit: `oss-audit audit . --skip-business --no-save` should still score ≥ silver on the technical pillar after your change.
4. PR with a concrete description of what changes and why. If you add a detector, include 1–2 sample repos where it fires.

## What we're NOT looking for right now

- Rewriting the entire rubric. Calibration with real data is still pending.
- Publishing to PyPI. Post-v0.6.
- More LLM backends until we have real data on which ones people actually use.

## License

Every PR is accepted under [EUPL-1.2](LICENSE) — the project's license.
