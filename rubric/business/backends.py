"""Pluggable LLM backends for the business pillar.

Three paths:
- `anthropic-api`: direct SDK with `ANTHROPIC_API_KEY`. Faster, no
  cache overhead. Billed via the API console.
- `claude-cli`: `claude --print` subprocess. Leverages the user's
  Pro/Max subscription auth (no separate API key needed). Trade-off:
  ~22k cache-creation tokens per call.
- `openai-compatible`: any endpoint that speaks the OpenAI API
  (OpenAI, Ollama, OpenRouter, Groq, vLLM, LM Studio, etc.).

Selected via env: RUBRIC_BACKEND override, or auto-detect.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Protocol

import httpx


class LLMBackend(Protocol):
    """Minimal contract: given system + user prompts, return (text, model_used).

    `json_schema` is optional; a hint for backends that support
    structured output (Claude CLI with --json-schema, OpenAI with
    response_format).
    """
    name: str
    model: str

    def complete(
        self, system: str, user: str, max_tokens: int,
        json_schema: dict | None = None,
    ) -> tuple[str, str]: ...


# ---------- Anthropic API key ----------

@dataclass
class AnthropicAPIBackend:
    name: str = "anthropic-api"
    api_key: str = ""
    model: str = "claude-opus-4-7"

    def complete(
        self, system: str, user: str, max_tokens: int,
        json_schema: dict | None = None,
    ) -> tuple[str, str]:
        from anthropic import Anthropic
        client = Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        return text, getattr(response, "model", self.model)


# ---------- Claude CLI (subscription) ----------

@dataclass
class ClaudeCLIBackend:
    name: str = "claude-cli"
    model: str = "claude-opus-4-7"
    timeout: int = 600

    def complete(
        self, system: str, user: str, max_tokens: int,
        json_schema: dict | None = None,
    ) -> tuple[str, str]:
        # Claude Code is trained as a conversational agent: without
        # --json-schema it tends to wrap the response in prose ("I've
        # completed the analysis..."). With --json-schema it forces
        # structured output.
        cmd = [
            "claude", "--print",
            "--output-format", "json",
            "--model", self.model,
            "--system-prompt", system,
            "--no-session-persistence",
            "--disable-slash-commands",
        ]
        if json_schema is not None:
            cmd += ["--json-schema", json.dumps(json_schema)]
        cmd.append(user)
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout,
            )
        except FileNotFoundError as e:
            raise RuntimeError("`claude` CLI not found in PATH") from e

        if proc.returncode != 0:
            raise RuntimeError(
                f"claude CLI failed (rc={proc.returncode}): {proc.stderr[:500]}"
            )
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"claude CLI didn't return JSON: {proc.stdout[:300]}") from e

        if payload.get("is_error"):
            raise RuntimeError(f"claude CLI error: {payload.get('result', 'unknown')}")

        text = payload.get("result", "")
        # `modelUsage` contains the model actually invoked (e.g.
        # "claude-haiku-4-5-20251001" when you asked for "haiku").
        used_model = next(iter(payload.get("modelUsage", {}).keys()), self.model)
        return text, used_model


# ---------- Claude Agent SDK (subscription, programmatic) ----------

@dataclass
class ClaudeAgentSDKBackend:
    """Official path for programmatic use of Claude Code.

    Unlike `claude --print` (conversational agent mode), here we disable
    every tool and force `max_turns=1` to get raw model text, not an
    agentic "task". Inherits Pro/Max subscription auth — no API key
    needed.
    """
    name: str = "claude-agent-sdk"
    model: str = "claude-opus-4-7"
    timeout: float = 600.0

    def complete(
        self, system: str, user: str, max_tokens: int,
        json_schema: dict | None = None,
    ) -> tuple[str, str]:
        import asyncio

        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            TextBlock,
            query,
        )

        options = ClaudeAgentOptions(
            system_prompt=system,
            model=self.model,
            allowed_tools=[],
            max_turns=1,
        )

        async def _run() -> tuple[str, str]:
            # We capture only the FIRST assistant turn. In environments
            # with Stop hooks (like Claude Code itself), the host can
            # inject UserMessages from hooks after the model
            # ("commit your changes!"), derailing the conversation.
            # We keep the first message_id and drop the rest.
            chunks: list[str] = []
            used_model = self.model
            first_message_id: str | None = None
            async for msg in query(prompt=user, options=options):
                if isinstance(msg, AssistantMessage):
                    mid = getattr(msg, "message_id", None)
                    if first_message_id is None:
                        first_message_id = mid
                    elif mid != first_message_id:
                        # derived turn (post-hook) — ignore
                        continue
                    if getattr(msg, "model", None):
                        used_model = msg.model
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            chunks.append(block.text)
                elif isinstance(msg, ResultMessage):
                    # If we already have text, we don't care if the
                    # ResultMessage flags an error caused by hooks
                    # injected later.
                    if not chunks and getattr(msg, "is_error", False):
                        raise RuntimeError(
                            f"Claude Agent SDK error: {getattr(msg, 'result', None) or 'unknown'}"
                        )
            return "".join(chunks), used_model

        try:
            return asyncio.run(asyncio.wait_for(_run(), timeout=self.timeout))
        except asyncio.TimeoutError as e:
            raise RuntimeError(f"Claude Agent SDK: timeout after {self.timeout}s") from e


# ---------- OpenAI-compatible ----------

@dataclass
class OpenAICompatibleBackend:
    name: str = "openai-compatible"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    timeout: float = 300.0

    def complete(
        self, system: str, user: str, max_tokens: int,
        json_schema: dict | None = None,
    ) -> tuple[str, str]:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        body: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
        }
        if json_schema is not None:
            # response_format with JSON Schema (OpenAI 4o+, Groq, OpenRouter, ...)
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "analysis", "schema": json_schema, "strict": False},
            }
        r = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"]
        used_model = data.get("model", self.model)
        return text, used_model


# ---------- Selection ----------

def select_backend() -> LLMBackend | None:
    """Pick a backend based on env vars. Returns None if none available."""
    explicit = os.environ.get("RUBRIC_BACKEND", "").strip().lower()
    model = os.environ.get("RUBRIC_MODEL")

    has_anthropic_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_claude_cli = shutil.which("claude") is not None
    try:
        import claude_agent_sdk  # noqa: F401
        has_agent_sdk = True
    except ImportError:
        has_agent_sdk = False
    has_openai_key = bool(os.environ.get("OPENAI_API_KEY"))

    pick = explicit
    if not pick:
        if has_anthropic_key:
            pick = "anthropic-api"
        elif has_agent_sdk and has_claude_cli:
            # The SDK uses the claude binary under the hood, with auth + programmatic control.
            pick = "claude-agent-sdk"
        elif has_claude_cli:
            pick = "claude-cli"
        elif has_openai_key:
            pick = "openai-compatible"
        else:
            return None

    if pick == "anthropic-api":
        if not has_anthropic_key:
            return None
        return AnthropicAPIBackend(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            model=model or "claude-opus-4-7",
        )
    if pick == "claude-agent-sdk":
        if not (has_agent_sdk and has_claude_cli):
            return None
        return ClaudeAgentSDKBackend(model=model or "claude-opus-4-7")
    if pick == "claude-cli":
        if not has_claude_cli:
            return None
        return ClaudeCLIBackend(model=model or "claude-opus-4-7")
    if pick == "openai-compatible":
        if not has_openai_key:
            return None
        return OpenAICompatibleBackend(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=model or "gpt-4o",
        )
    return None
