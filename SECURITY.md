# Security policy

OSS Auditor is alpha (`v0.5.x`); there's no private disclosure channel yet. If you find a vulnerability:

- **Private / sensitive** (e.g. arbitrary code execution when auditing a malicious repo, environment-variable leaks, etc.): open an **empty** issue and mention `@alpibrusl` so we can reach you privately by email. Don't post the details in the issue.
- **Public / low severity** (a secret pattern that misses, a false positive in `agent_readiness`, etc.): a regular issue with the `security` label.

## Known risk areas

- `ingestion.py` runs `git clone --depth 1` against arbitrary URLs supplied by the user. It doesn't run git hooks, but a malicious repo could still attempt to abuse bugs in git itself.
- The technical pillar **does not execute** code from the audited repo, except for explicit tools (cargo audit, ruff, npm audit, govulncheck) that do parse the dependency tree. If you don't trust the repo, audit it inside a sandbox.
- `business/analyzer.py` sends repo content (README, manifests, code samples, commits, issues) to the configured LLM backend. If you audit private repos, make sure your backend respects confidentiality (no `openai-compatible` with a public base URL for sensitive data).

## What we do NOT do

- Process repos larger than 1 GB without explicit truncation.
- Run the audited repo's tests (that needs its own sandboxing).
- Recurse into `node_modules`, `target/`, `.git/`, etc.
