"""Análisis de negocio impulsado por LLM.

El prompt está diseñado para producir output estructurado (JSON) y para
forzar al modelo a basar cada juicio en evidencia del repo, no en
suposiciones genéricas.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from anthropic import Anthropic

from ..models import BusinessReport

CLAUDE_MODEL = os.environ.get("OSS_AUDITOR_MODEL", "claude-opus-4-7")

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
5. Output debe ser JSON válido con la estructura exacta especificada. Nada de texto fuera del JSON.
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
    """Extrae el primer bloque JSON válido del texto."""
    # quitar fences ```json ... ```
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    # encontrar primer { y último }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No se encontró JSON en la respuesta. Inicio: {text[:200]}")
    return json.loads(text[start:end + 1])


def analyze_business(context: dict[str, Any]) -> BusinessReport:
    """Llama a Claude con el contexto del proyecto y devuelve un BusinessReport."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return BusinessReport(
            score=0.0,
            summary="ANTHROPIC_API_KEY no configurada — análisis de negocio omitido.",
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

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw_text = "".join(b.text for b in response.content if hasattr(b, "text"))

    try:
        parsed = _extract_json(raw_text)
    except (ValueError, json.JSONDecodeError) as e:
        return BusinessReport(
            score=0.0,
            summary=f"Error parseando respuesta del LLM: {e}",
            raw_analysis=raw_text,
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
    )
