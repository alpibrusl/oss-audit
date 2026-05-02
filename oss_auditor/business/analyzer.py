"""Análisis de negocio impulsado por LLM.

El prompt está diseñado para producir output estructurado (JSON) y para
forzar al modelo a basar cada juicio en evidencia del repo, no en
suposiciones genéricas.

El backend LLM es intercambiable (ver `backends.py`): API key directa de
Anthropic, CLI de Claude Code (suscripción), u OpenAI-compatible.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..models import BusinessReport
from .backends import select_backend

# Schema para forzar output estructurado en backends que lo soporten
# (Claude CLI con --json-schema, OpenAI con response_format).
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
            },
            "required": [
                "problem_clarity", "execution_vs_ambition",
                "differentiation", "market_signals", "viability_risks",
            ],
        },
        "summary": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "weaknesses": {"type": "array", "items": {"type": "string"}},
        "opportunities": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array"},
    },
    "required": ["scores", "summary"],
}

SYSTEM_PROMPT = """Eres un analista senior que evalúa proyectos open-source con la lente de un \
inversor técnico (operator-VC). Tu trabajo es producir juicios HONESTOS basados en EVIDENCIA \
extraída del repositorio, no en marketing del README.

REGLAS:
1. Cada afirmación que hagas debe estar respaldada por evidencia concreta del contexto que recibes \
   (un archivo, un commit, una línea de código, una issue). Si no hay evidencia, dilo.
2. Distingue entre AMBICIÓN DECLARADA (lo que dice el README) y EJECUCIÓN OBSERVABLE (lo que el \
   código y los commits muestran). El gap entre ambas es la señal más importante.
3. No infles scores por simpatía. Un proyecto en fase temprana puede ser brillante pero seguir \
   teniendo un score de tracción bajo — eso es honesto, no negativo.
4. Identifica el RIESGO REAL, no solo lo positivo. Si el proyecto compite con incumbents bien \
   financiados, dilo. Si la tesis es difícil de defender, dilo.

FORMATO DE OUTPUT (CRÍTICO):
- Tu respuesta DEBE empezar con `{` y terminar con `}`.
- NO escribas prosa antes ni después del JSON.
- NO uses code fences (```json).
- NO digas "Aquí está el análisis" ni "He completado el análisis".
- El primer carácter de tu output es `{`.
- Si no puedes producir JSON válido, devuelve `{"error": "razón breve"}`.
"""

USER_PROMPT_TEMPLATE = """Analiza el siguiente proyecto open-source y devuelve un análisis \
estructurado en JSON.

# Contexto del proyecto

## Metadata
{meta}

## Estructura
```
{structure}
```

## Documentación
{docs_section}

## Manifests (deps y configuración)
{manifests_section}

## Muestras de código
{code_section}

## Commits recientes
{commits_section}

## Issues recientes
{issues_section}

---

# Tu tarea

Devuelve **solo JSON válido** con esta estructura exacta:

```json
{{
  "scores": {{
    "problem_clarity": <0-100>,
    "execution_vs_ambition": <0-100>,
    "differentiation": <0-100>,
    "market_signals": <0-100>,
    "viability_risks": <0-100>
  }},
  "summary": "<2-3 frases que capturen la esencia del proyecto y su estado real>",
  "problem": {{
    "description": "<qué problema resuelve, según evidencia>",
    "target_users": "<quiénes son los usuarios objetivo>",
    "evidence": "<archivo/sección que respalda esto>"
  }},
  "execution": {{
    "ambition_declared": "<lo que el proyecto DICE ser>",
    "execution_observed": "<lo que el código/commits MUESTRAN>",
    "gap_analysis": "<discrepancia y qué significa>"
  }},
  "differentiation": {{
    "unique_aspects": ["<aspecto 1>", "<aspecto 2>"],
    "competitors": ["<competidor real con razón>"],
    "moat_assessment": "<qué tan defensible es>"
  }},
  "market_signals": {{
    "demand_evidence": "<señales de demanda real>",
    "adoption_indicators": "<stars, forks, menciones, etc.>"
  }},
  "risks": [
    {{"risk": "<riesgo>", "severity": "low|medium|high", "evidence": "<base>"}}
  ],
  "strengths": ["<fortaleza concreta 1>", "<fortaleza 2>"],
  "weaknesses": ["<debilidad concreta 1>", "<debilidad 2>"],
  "opportunities": ["<oportunidad 1>", "<oportunidad 2>"]
}}
```

# Rúbrica para los scores (0-100)

- **problem_clarity**: ¿El problema es nítido y específico? 90+ = "Resuelve X para Y, evidencia clara". \
  50-70 = "Idea presente pero difusa". <50 = "No está claro qué problema resuelve".

- **execution_vs_ambition**: ¿La ejecución observable matchea la ambición declarada? 90+ = código \
  refleja el README y va más allá. 50 = ambición alta, ejecución parcial. <30 = mucho marketing, \
  poco código que lo respalde.

- **differentiation**: ¿Hay algo defensible? 90+ = enfoque/algoritmo único con barrera real. \
  50 = diferencias menores. <30 = me-too de algo existente.

- **market_signals**: ¿Hay evidencia de demanda? 90+ = adopción visible, issues con casos reales, \
  empresas usándolo. 30-50 = nicho identificado pero sin tracción aún. <30 = solo el autor lo usa.

- **viability_risks**: ¿Qué tan viable es a 12-24 meses? Evalúa riesgos: complejidad técnica, \
  competencia, dependencia de un solo autor, modelo de monetización ausente, etc. 90+ = pocos \
  riesgos claros. <30 = riesgos de muerte temprana.

Recuerda: SOLO JSON, sin texto adicional.
"""


def _truncate(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + f"\n... [truncado a {max_chars} caracteres]"


def _format_docs(docs: dict[str, str]) -> str:
    if not docs:
        return "(sin documentación detectada)"
    parts = []
    for name, content in docs.items():
        parts.append(f"### {name}\n```\n{_truncate(content, 8000)}\n```")
    return "\n\n".join(parts)


def _format_manifests(manifests: dict[str, str]) -> str:
    if not manifests:
        return "(sin manifests)"
    parts = []
    for name, content in manifests.items():
        parts.append(f"### {name}\n```\n{_truncate(content, 4000)}\n```")
    return "\n\n".join(parts)


def _format_code(samples: dict[str, str]) -> str:
    if not samples:
        return "(sin muestras de código)"
    parts = []
    for name, content in samples.items():
        parts.append(f"### {name}\n```\n{_truncate(content, 5000)}\n```")
    return "\n\n".join(parts)


def _format_commits(commits: list[dict]) -> str:
    if not commits:
        return "(sin commits accesibles)"
    return "\n".join(f"- {c.get('sha', '?')} ({c.get('date', '?')[:10]}): {c.get('message', '')}"
                     for c in commits)


def _format_issues(issues: list[dict]) -> str:
    if not issues:
        return "(sin issues accesibles)"
    parts = []
    for i in issues:
        parts.append(f"- #{i.get('number')} [{i.get('state')}] {i.get('title')} "
                     f"({i.get('comments', 0)} comments)")
    return "\n".join(parts)


def _extract_json(text: str) -> dict[str, Any]:
    """Extrae el primer objeto JSON válido del texto.

    Modelos conversacionales (incl. Claude CLI en modo agente) a veces
    envuelven la respuesta en prosa o code fences. Estrategias en orden:
      1. Buscar bloques ```json ... ``` o ``` ... ```.
      2. Buscar el primer { ... } balanceado.
      3. Fallback: primer { hasta último }.
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

    raise ValueError(f"No se encontró JSON en la respuesta. Inicio: {text[:200]}")


def analyze_business(context: dict[str, Any]) -> BusinessReport:
    """Llama al backend LLM con el contexto del proyecto y devuelve un BusinessReport."""
    backend = select_backend()
    if backend is None:
        return BusinessReport(
            score=0.0,
            summary=(
                "Sin backend LLM disponible. Configura una de: ANTHROPIC_API_KEY, "
                "OPENAI_API_KEY, o instala el CLI `claude` (Claude Code) para usar "
                "tu suscripción Pro/Max."
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
            summary=f"Error llamando al backend `{backend.name}`: {e}",
            raw_analysis="",
            backend=backend.name,
            model=backend.model,
        )

    try:
        parsed = _extract_json(raw_text)
    except (ValueError, json.JSONDecodeError) as e:
        return BusinessReport(
            score=0.0,
            summary=f"Error parseando respuesta del LLM ({backend.name}/{used_model}): {e}",
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
    overall = round((pc * 0.25 + ev * 0.25 + di * 0.20 + ms * 0.15 + vr * 0.15), 1)

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
        summary=parsed.get("summary", ""),
        strengths=parsed.get("strengths", []),
        weaknesses=weaknesses,
        opportunities=parsed.get("opportunities", []),
        raw_analysis=json.dumps(parsed, indent=2, ensure_ascii=False),
        backend=backend.name,
        model=used_model,
    )
