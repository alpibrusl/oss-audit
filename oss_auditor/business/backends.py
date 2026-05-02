"""Backends LLM intercambiables para el pilar de negocio.

Tres caminos:
- `anthropic-api`: SDK directo con `ANTHROPIC_API_KEY`. Más rápido, sin
  overhead de cache. Facturación por API console.
- `claude-cli`: subprocess `claude --print`. Aprovecha la auth de la
  suscripción Pro/Max del usuario (no requiere API key separada).
  Trade-off: ~22k tokens de cache creation por llamada.
- `openai-compatible`: cualquier endpoint con la API de OpenAI
  (OpenAI, Ollama, OpenRouter, Groq, vLLM, LM Studio, etc).

Selección por env: OSS_AUDITOR_BACKEND override, o auto-detect.
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
    """Contrato mínimo: dado system + user prompts, devolver (texto, modelo_usado).

    `json_schema` es opcional y pista para backends que soporten structured
    output (Claude CLI con --json-schema, OpenAI con response_format).
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
        # Claude Code se entrena como agente conversacional: sin --json-schema
        # tiende a envolver la respuesta en prosa ("I've completed the
        # analysis..."). Con --json-schema fuerza output estructurado.
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
            raise RuntimeError("`claude` CLI no encontrado en PATH") from e

        if proc.returncode != 0:
            raise RuntimeError(
                f"claude CLI falló (rc={proc.returncode}): {proc.stderr[:500]}"
            )
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"claude CLI no devolvió JSON: {proc.stdout[:300]}") from e

        if payload.get("is_error"):
            raise RuntimeError(f"claude CLI error: {payload.get('result', 'unknown')}")

        text = payload.get("result", "")
        # `modelUsage` contiene el modelo realmente invocado (e.g.
        # "claude-haiku-4-5-20251001" cuando pediste "haiku").
        used_model = next(iter(payload.get("modelUsage", {}).keys()), self.model)
        return text, used_model


# ---------- Claude Agent SDK (subscription, programmatic) ----------

@dataclass
class ClaudeAgentSDKBackend:
    """Vía oficial para uso programático de Claude Code.

    A diferencia de `claude --print` (modo agente conversacional), aquí
    desactivamos todas las tools y forzamos `max_turns=1` para obtener un
    texto crudo del modelo, no una "tarea" agentica. Hereda la auth de la
    suscripción Pro/Max sin necesidad de API key.
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
            # Capturamos solo la respuesta del PRIMER turno del asistente.
            # En entornos con Stop hooks (como Claude Code mismo), después
            # del modelo el host puede inyectar UserMessages de hooks
            # ("commit your changes!"), lo que derailia la conversación.
            # Nos quedamos con el primer message_id y descartamos el resto.
            chunks: list[str] = []
            used_model = self.model
            first_message_id: str | None = None
            async for msg in query(prompt=user, options=options):
                if isinstance(msg, AssistantMessage):
                    mid = getattr(msg, "message_id", None)
                    if first_message_id is None:
                        first_message_id = mid
                    elif mid != first_message_id:
                        # turno derivado (post-hook) — ignorar
                        continue
                    if getattr(msg, "model", None):
                        used_model = msg.model
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            chunks.append(block.text)
                elif isinstance(msg, ResultMessage):
                    # Si ya tenemos texto, no nos importa si el ResultMessage
                    # marca error por culpa de hooks que se metieron después.
                    if not chunks and getattr(msg, "is_error", False):
                        raise RuntimeError(
                            f"Claude Agent SDK error: {getattr(msg, 'result', None) or 'unknown'}"
                        )
            return "".join(chunks), used_model

        try:
            return asyncio.run(asyncio.wait_for(_run(), timeout=self.timeout))
        except asyncio.TimeoutError as e:
            raise RuntimeError(f"Claude Agent SDK: timeout tras {self.timeout}s") from e


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
            # response_format con JSON Schema (OpenAI 4o+, Groq, OpenRouter, ...)
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
    """Elige un backend según env vars. Devuelve None si ninguno disponible."""
    explicit = os.environ.get("OSS_AUDITOR_BACKEND", "").strip().lower()
    model = os.environ.get("OSS_AUDITOR_MODEL")

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
            # SDK usa el binario claude por debajo, pero con auth + control programático.
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
