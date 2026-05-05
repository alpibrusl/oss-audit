"""LLM-driven business analysis.

The prompt is designed to produce structured JSON output and to force
the model to base every judgment on evidence from the repo, not on
generic assumptions.

The LLM backend is pluggable (see `backends.py`): direct Anthropic
API key, Claude Code CLI (subscription), or OpenAI-compatible.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..models import BusinessReport
from .backends import select_backend

# Schema to force structured output on backends that support it
# (Claude CLI with --json-schema, OpenAI with response_format).
ANALYSIS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "object",
            "properties": {
                "problem_clarity": {"type": "number"},
                "execution_vs_ambition": {"type": "number"},
                "differentiation": {"type": "number"},
                "market_signals": {"type": "number"},
                "viability_risks": {"type": "number"},
                "intellectual_contribution": {"type": "number"},
            },
            "required": [
                "problem_clarity", "execution_vs_ambition",
                "differentiation", "market_signals", "viability_risks",
            ],
        },
        "summary": {"type": "string"},
        "novelty_summary": {"type": "string"},
        "nearest_prior_art": {"type": "array", "items": {"type": "string"}},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "weaknesses": {"type": "array", "items": {"type": "string"}},
        "opportunities": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array"},
        "developer_view": {"type": "string"},
        "cto_view": {"type": "string"},
        "investor_view": {"type": "string"},
        "mind_changers": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["scores", "summary"],
}

SYSTEM_PROMPT = """You are a senior analyst evaluating open-source projects through the lens of a \
technical investor (operator-VC). Your job is to produce HONEST judgments based on EVIDENCE \
extracted from the repository, not on the README's marketing.

RULES:
1. Every claim you make must be backed by concrete evidence from the context you receive \
   (a file, a commit, a line of code, an issue). If there's no evidence, say so.
2. Distinguish between DECLARED AMBITION (what the README says) and OBSERVABLE EXECUTION \
   (what the code and commits show). The gap between the two is the most important signal.
3. Don't inflate scores out of sympathy. An early-stage project may be brilliant and still \
   carry a low traction score — that's honest, not negative.
4. Identify the REAL risk, not just the positives. If the project competes with well-funded \
   incumbents, say so. If the thesis is hard to defend, say so.

OUTPUT FORMAT (CRITICAL):
- Your response MUST start with `{` and end with `}`.
- Do NOT write prose before or after the JSON.
- Do NOT use code fences (```json).
- Do NOT say "Here's the analysis" or "I've completed the analysis".
- The first character of your output is `{`.
- If you can't produce valid JSON, return `{"error": "brief reason"}`.
"""

USER_PROMPT_TEMPLATE = """Analyze the following open-source project and return a structured \
analysis as JSON.

# Project context

## Metadata
{meta}

## Structure
```
{structure}
```

## Documentation
{docs_section}

## Manifests (deps and configuration)
{manifests_section}

## Code samples
{code_section}

## Recent commits
{commits_section}

## Recent issues
{issues_section}

---

# Your task

This is the **Thesis & Innovation** pillar. You're not just evaluating execution; \
you're evaluating how **new** and **defensible** the idea is, what priors exist, and what \
a developer / CTO / investor would do with this information.

Return **valid JSON only** with this exact structure:

```json
{{
  "scores": {{
    "problem_clarity": <0-100>,
    "execution_vs_ambition": <0-100>,
    "differentiation": <0-100>,
    "market_signals": <0-100>,
    "viability_risks": <0-100>,
    "intellectual_contribution": <0-100>
  }},
  "summary": "<2-3 sentences capturing the essence of the project and its real state>",
  "novelty_summary": "<1-2 sentences: what primitive/abstraction/technique is new here, if any>",
  "nearest_prior_art": ["<closest project/paper 1>", "<2>", "<3 if applicable>"],
  "strengths": ["<concrete strength 1>", "<strength 2>"],
  "weaknesses": ["<concrete weakness 1>", "<weakness 2>"],
  "opportunities": ["<opportunity 1>", "<opportunity 2>"],
  "risks": [
    {{"risk": "<risk>", "severity": "low|medium|high", "evidence": "<basis>"}}
  ],
  "developer_view": "<3 sentences: do I use it in prod? do I contribute? do I learn from it?>",
  "cto_view": "<3 sentences: adopt / pilot / wait / pass? stack risk. hireable team?>",
  "investor_view": "<3 sentences: fundable? stage match. main risk: technical / market / team>",
  "mind_changers": [
    "<observable signal that, if it appeared, would change your assessment; e.g. '5 external contributors in 6 months'>",
    "<another signal>",
    "<another signal>"
  ]
}}
```

# Rubric for the scores (0-100)

- **problem_clarity**: Is the problem sharp and specific? 90+ = "Solves X for Y, clear evidence". \
  50-70 = "Idea present but fuzzy". <50 = "Not clear what problem it solves".

- **execution_vs_ambition**: Does observable execution match declared ambition? 90+ = code \
  reflects the README and goes beyond. 50 = high ambition, partial execution. <30 = lots of \
  marketing, little code to back it up.

- **differentiation**: Is there anything defensible? 90+ = unique approach/algorithm with a real \
  moat. 50 = minor differences. <30 = me-too of something that already exists.

- **market_signals**: Is there evidence of demand? 90+ = visible adoption, issues with real use \
  cases, companies using it. 30-50 = niche identified but no traction yet. <30 = only the author \
  uses it.

- **intellectual_contribution**: How much does this project advance the state of the art? 90+ = \
  primitive or abstraction that's genuinely new, citable as future prior art. 50 = useful \
  combination of existing ideas. <30 = direct application of known patterns.

- **viability_risks**: How viable at 12-24 months? Evaluate risks: technical complexity, \
  competition, single-author dependency, missing monetization model, etc. 90+ = few clear \
  risks. <30 = early-death risks.

Remember: JSON ONLY, no extra text.
"""


def _truncate(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + f"\n... [truncated to {max_chars} characters]"


def _format_docs(docs: dict[str, str]) -> str:
    if not docs:
        return "(no documentation detected)"
    parts = []
    for name, content in docs.items():
        parts.append(f"### {name}\n```\n{_truncate(content, 8000)}\n```")
    return "\n\n".join(parts)


def _format_manifests(manifests: dict[str, str]) -> str:
    if not manifests:
        return "(no manifests)"
    parts = []
    for name, content in manifests.items():
        parts.append(f"### {name}\n```\n{_truncate(content, 4000)}\n```")
    return "\n\n".join(parts)


def _format_code(samples: dict[str, str]) -> str:
    if not samples:
        return "(no code samples)"
    parts = []
    for name, content in samples.items():
        parts.append(f"### {name}\n```\n{_truncate(content, 5000)}\n```")
    return "\n\n".join(parts)


def _format_commits(commits: list[dict]) -> str:
    if not commits:
        return "(no commits accessible)"
    return "\n".join(f"- {c.get('sha', '?')} ({c.get('date', '?')[:10]}): {c.get('message', '')}"
                     for c in commits)


def _format_issues(issues: list[dict]) -> str:
    if not issues:
        return "(no issues accessible)"
    parts = []
    for i in issues:
        parts.append(f"- #{i.get('number')} [{i.get('state')}] {i.get('title')} "
                     f"({i.get('comments', 0)} comments)")
    return "\n".join(parts)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract the first valid JSON object from the text.

    Conversational models (incl. Claude CLI in agent mode) sometimes
    wrap the response in prose or code fences. Strategies in order:
      1. Look for ```json ... ``` or ``` ... ``` blocks.
      2. Find the first balanced { ... }.
      3. Fallback: first { up to last }.
    """
    text = text.strip()

    # 1. fenced code blocks
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # 2. balanced braces (handles nested JSON inside prose)
    depth = 0
    start_idx: int | None = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start_idx = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start_idx is not None:
                candidate = text[start_idx : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start_idx = None

    # 3. naive fallback
    s = text.find("{")
    e = text.rfind("}")
    if s != -1 and e > s:
        try:
            return json.loads(text[s : e + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No JSON found in the response. Start: {text[:200]}")


def analyze_business(context: dict[str, Any]) -> BusinessReport:
    """Call the LLM backend with the project context and return a BusinessReport."""
    backend = select_backend()
    if backend is None:
        return BusinessReport(
            score=0.0,
            summary=(
                "No LLM backend available. Configure one of: ANTHROPIC_API_KEY, "
                "OPENAI_API_KEY, or install the `claude` CLI (Claude Code) to use "
                "your Pro/Max subscription."
            ),
            raw_analysis="",
        )

    user_prompt = USER_PROMPT_TEMPLATE.format(
        meta=json.dumps(context["meta"], indent=2, ensure_ascii=False),
        structure=context["structure"],
        docs_section=_format_docs(context["docs"]),
        manifests_section=_format_manifests(context["manifests"]),
        code_section=_format_code(context["code_samples"]),
        commits_section=_format_commits(context["recent_commits"]),
        issues_section=_format_issues(context["recent_issues"]),
    )

    try:
        raw_text, used_model = backend.complete(
            system=SYSTEM_PROMPT, user=user_prompt, max_tokens=4000,
            json_schema=ANALYSIS_SCHEMA,
        )
    except Exception as e:  # noqa: BLE001
        return BusinessReport(
            score=0.0,
            summary=f"Error calling backend `{backend.name}`: {e}",
            raw_analysis="",
            backend=backend.name,
            model=backend.model,
        )

    try:
        parsed = _extract_json(raw_text)
    except (ValueError, json.JSONDecodeError) as e:
        return BusinessReport(
            score=0.0,
            summary=f"Error parsing the LLM response ({backend.name}/{used_model}): {e}",
            raw_analysis=raw_text,
            backend=backend.name,
            model=used_model,
        )

    scores = parsed.get("scores", {})
    pc = float(scores.get("problem_clarity", 0))
    ev = float(scores.get("execution_vs_ambition", 0))
    di = float(scores.get("differentiation", 0))
    ms = float(scores.get("market_signals", 0))
    vr = float(scores.get("viability_risks", 0))
    ic = float(scores.get("intellectual_contribution", 0))
    # v0.5 formula: intellectual_contribution enters the score at weight 15%;
    # we deduct from market_signals (15 -> 10) to keep the total at 100%.
    overall = round(
        (pc * 0.20 + ev * 0.20 + di * 0.20 + ms * 0.10 + vr * 0.15 + ic * 0.15), 1
    )

    risks_text = parsed.get("risks", [])
    weaknesses = parsed.get("weaknesses", [])
    if isinstance(risks_text, list):
        for r in risks_text:
            if isinstance(r, dict) and "risk" in r:
                weaknesses.append(f"[{r.get('severity', '?')}] {r['risk']}")

    return BusinessReport(
        score=overall,
        problem_clarity=pc,
        execution_vs_ambition=ev,
        differentiation=di,
        market_signals=ms,
        viability_risks=vr,
        intellectual_contribution=ic,
        summary=parsed.get("summary", ""),
        novelty_summary=parsed.get("novelty_summary", ""),
        nearest_prior_art=parsed.get("nearest_prior_art", []),
        strengths=parsed.get("strengths", []),
        weaknesses=weaknesses,
        opportunities=parsed.get("opportunities", []),
        developer_view=parsed.get("developer_view", ""),
        cto_view=parsed.get("cto_view", ""),
        investor_view=parsed.get("investor_view", ""),
        mind_changers=parsed.get("mind_changers", []),
        raw_analysis=json.dumps(parsed, indent=2, ensure_ascii=False),
        backend=backend.name,
        model=used_model,
    )
