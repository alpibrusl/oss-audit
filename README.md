# OSS Auditor

[![OSS Audit](https://img.shields.io/badge/oss--audit-46.3%2F100_bronze-yellow)](.)
[![License: EUPL-1.2](https://img.shields.io/badge/license-EUPL--1.2-blue)](LICENSE)

Una herramienta de auditoría que no se limita a darte un número: te dice **qué hacer** con la información — adoptar, contribuir, financiar, esperar o pasar.

> ⚠️ **Estado: alpha (v0.5.x).** API y rúbrica pueden cambiar entre versiones menores. Se busca feedback de auditorías reales para calibrar.

## Por qué otra herramienta de "OSS quality"

Las herramientas existentes (OpenSSF Scorecard, Snyk, Sonar) miden **calidad de proceso** — bien para detectar abandono y vulnerabilidades, mal para distinguir un proyecto innovador de uno derivado. Su rúbrica asume implícitamente que "buen OSS = equipo grande + historia larga", lo cual penaliza injustamente a la categoría que más está creciendo: **proyectos solo-autor + agentes IA**.

OSS Auditor está construido alrededor de tres convicciones:

1. **La era post-LLM cambió el juego.** Una persona + agentes IA puede shipear al ritmo de un equipo de 5. Bus factor `94% de un autor` no es señal de baja calidad si los commits son diarios — es señal de continuidad, no de ejecución.
2. **Medir ejecución no basta.** Un repo con 92/100 en métricas técnicas puede ser un clon irrelevante. La pregunta importante es **idea × ejecución × relevancia**, no solo ejecución.
3. **Un score sin acción es ruido.** El reporte tiene que responder a "¿lo uso? ¿lo adopto? ¿lo financio?" en función de la audiencia que lee.

## Demo: `lex-lang` auditado por OSS Auditor

```
╭───────────────── OSS Auditor ──────────────────╮
│ lex-lang                                       │
│ Score: 62.4/100 (SILVER)                       │
╰────────────────────────────────────────────────╯

Pilares:
  🔧 Técnico             98.0    40%
  💡 Tesis & innovación  64.9    35%
  👥 Comunidad            2.0    25%

╭──── Veredicto: ahead-of-its-time ──────────────╮
│ Ahead of its time                              │
│ (idea: high · exec: high · relevance: low)     │
│ Trabajo brillante sin mercado todavía. Sigue   │
│ de cerca; no apuestes hoy.                     │
╰────────────────────────────────────────────────╯
```

Vista por audiencia (extracto):
- **Developer**: "Si sos contributor, el código es limpio y la arquitectura instructiva, pero no hay usuarios que validen si tu trabajo importa todavía."
- **CTO**: "Stack risk medio-alto. Esperaría hasta 1.0+ + 2-3 contribuidores externos + un case study real."
- **Investor**: "Fundable conceptualmente. Pre-seed máximo. Riesgo principal: mercado."

Mind-changers (qué cambiaría la evaluación):
1. Adopción por ≥1 agente IA mainstream (Claude, ChatGPT, Gemini) usándolo como sandbox por defecto.
2. 5+ contribuidores externos con commits meaningful en 6 meses.
3. Paper en PLDI/ICFP o citas en research de AI safety / code-gen.
4. Compiler de Lex reescrito en Lex mismo (dogfooding).

## Instalación

```bash
git clone https://github.com/alpibrusl/oss-audit
cd oss-audit
pip install -e .
```

Herramientas externas opcionales (mejoran el pilar técnico si están en `$PATH`):

| Tool | Para |
|------|------|
| `gitleaks` | escaneo de secretos más completo |
| `cargo` + `cargo-audit` | Rust |
| `ruff`, `pip-audit` | Python |
| `npm` | JS / TS |
| `govulncheck` | Go |

## Backend LLM

El pilar de tesis & innovación necesita un LLM. Tres caminos, auto-detectados o forzados con `OSS_AUDITOR_BACKEND`:

| Opción | Cómo | Auth |
|--------|------|------|
| `claude-agent-sdk` | Tienes el CLI `claude` instalado | **Tu suscripción Pro/Max** (sin API key) |
| `anthropic-api` | `ANTHROPIC_API_KEY=sk-ant-…` | Console billing (separado de tu sub) |
| `openai-compatible` | `OPENAI_API_KEY=…` + `OPENAI_BASE_URL=…` | OpenAI / OpenRouter / Groq / Ollama / vLLM / LM Studio |

```bash
# Override explícito
export OSS_AUDITOR_BACKEND=openai-compatible
export OPENAI_BASE_URL=http://localhost:11434/v1   # Ollama local
export OSS_AUDITOR_MODEL=llama3.1:70b
```

GitHub token recomendado pero opcional (sin él, el ratelimit es 60 req/h):

```bash
GITHUB_TOKEN=ghp_…
```

## Uso

```bash
# Audit completo (técnico + tesis + comunidad)
oss-audit audit https://github.com/alpibrusl/lex-lang

# Solo señales locales, sin LLM ni GitHub API
oss-audit audit ~/code/mi-proyecto --skip-business --skip-community

# JSON envelope para agentes / scripts
oss-audit audit https://github.com/alpibrusl/lex-lang --output json

# Repos tipo "proposal" (gists, RFC, specs)
oss-audit audit https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

# Listar / ver auditorías guardadas
oss-audit list
oss-audit show 1

# Generar badge shields.io para README
oss-audit badge                            # markdown del último audit
oss-audit badge 1 --format url             # URL estática
oss-audit badge 1 --format endpoint        # JSON para img.shields.io/endpoint?url=…

# Web local para navegar el histórico
oss-audit serve

# Auto-descubrimiento para agentes
oss-audit introspect    # árbol completo de comandos como JSON
```

## Conceptos clave

### Tipo de artefacto
Antes de scorear, OSS Auditor clasifica el repo:
- **`implementation`** — código es el artefacto (la mayoría).
- **`proposal`** — el spec / idea es el artefacto (gists, RFCs, "ideas con tracción"). Auto-detectado por URL de gist o por low-LOC + heavy README + traction. En modo proposal el pilar técnico se **omite** y los pesos se renormalizan.

### Tres pilares
| Pilar | Peso | Qué mide |
|-------|------|----------|
| 🔧 Técnico | 40% | Tests, densidad de tests, fuzz / property tests, CI, secretos, vulns, lint, licencia, **composabilidad** (CLI / library / MCP / HTTP / workspace) |
| 💡 Tesis & innovación | 35% | Claridad del problema, gap ambición vs ejecución, diferenciación, señales de mercado, **contribución intelectual** (¿cita-able como prior art futura?) |
| 👥 Comunidad | 25% | Stars / forks / contribuidores, **velocity-per-author** (señal AI-era), recencia, agent-readiness (CLAUDE.md, .cli/, mcp.json, …), bus factor (como contexto, no como castigo) |

### Veredicto (capa de advisor)
Combinación de tres ejes (idea × ejecución × relevancia, cada uno `low`/`medium`/`high`) → uno de 8 veredictos:

| Verdict | Cuándo | Acción |
|---------|--------|--------|
| `bet-on-it` | high / high / high | Adopta, contribuye, invierte |
| `worth-helping` | high / low / high+ | Buena idea, ejecución débil → forkear, financiar |
| `promising-prototype` | high / med / med | Watch, revisar en 3 meses |
| `ahead-of-its-time` | high / high / **low** | Track, no apostar hoy |
| `solid-commodity` | low / high / high+ | Adopta si lo necesitas, sin upside |
| `skill-in-search` | low / high / low | Talento reutilizable; proyecto no |
| `incomplete-thesis` | medium / low / low | Sin señal suficiente |
| `pass` | (default) | Skip |

Cada veredicto trae acciones pre-bakead para developer / CTO / investor.

### Vistas por audiencia
Cada audit (con LLM) emite tres párrafos cortos basados en la **misma evidencia** pero framed para quién lee:
- **Developer**: ¿lo uso en prod? ¿contribuyo? ¿aprendo de él?
- **CTO / VP-Eng**: adopt / pilot / wait / pass + stack risk + ¿equipo hireable?
- **Investor**: fundable / stage match + riesgo (técnico / mercado / equipo)

### Counterfactuals — "qué cambiaría mi opinión"
Dos tipos:
- **Programáticos**: simulan +30 al pilar más débil; si el veredicto cambia, lo reportan.
- **LLM `mind_changers`**: señales observables falsables — *"si X aparece en N meses, mi evaluación cambia."*

## Arquitectura

```
oss_auditor/
├── cli.py                      # `oss-audit` (ACLI-compliant)
├── pipeline.py                 # Orquestador end-to-end
├── ingestion.py                # Clone/local + detección de lenguajes + clasificador
├── models.py                   # Pydantic schemas
├── technical/
│   ├── runner.py               # Score técnico
│   ├── universal.py            # Secretos, CI, tests, fuzz, property, licencia
│   ├── composability.py        # CLI / library / MCP / HTTP / workspace
│   └── lang_runners.py         # cargo, ruff, npm, govulncheck, ...
├── business/
│   ├── context_builder.py      # Dossier rico (NO solo README)
│   ├── analyzer.py             # Prompt + JSON schema + parser
│   └── backends.py             # Anthropic API / Claude SDK / OpenAI-compatible
├── community/
│   ├── github_metrics.py       # Stars / forks / velocity / bus factor
│   └── agent_readiness.py      # CLAUDE.md / AGENTS.md / .cli/ / mcp.json / ...
├── reporter/
│   ├── scorer.py               # Score agregado (renormaliza pilares activos)
│   ├── verdict.py              # 8 veredictos + counterfactuals programáticos
│   ├── badge.py                # Shields.io static / endpoint / markdown
│   └── markdown.py             # Render de reportes
├── storage/db.py               # SQLite local
└── web.py                      # FastAPI para histórico
```

## Roadmap

- **v0.6 — Calibración con datos reales.** Ajustar umbrales y pesos contra ≥10 auditorías de proyectos diversos. Hasta entonces los thresholds del verdict son aproximaciones razonables, no verdad calibrada.
- **v0.7 — Más backends + más lenguajes.** Bedrock, Vertex, Cohere; runners para Java / Kotlin / Swift.
- **v0.8 — Comparación temporal.** Diff entre dos auditorías del mismo repo (¿mejoró? ¿se estancó?).
- **v0.9 — Modo "monitor".** Auditar en CI cada PR; alertar cuando el verdict cambia.

## Contribuir

Primer mejor primer PR: añadir un detector a `oss_auditor/community/agent_readiness.py` o `oss_auditor/technical/composability.py`. Son módulos auto-contenidos, fácil de testear.

```bash
pip install -e .
python tests/smoke_test.py
oss-audit audit . --skip-business --skip-community  # eat your own dogfood
```

Issues bienvenidas para:
- Falsos positivos / negativos en clasificación de tipo (`implementation` vs `proposal`).
- Calibración de thresholds del verdict (40 / 70).
- Repos donde el rubric da un veredicto que sentís claramente erróneo — esos son oro.

## Licencia

[EUPL-1.2](LICENSE) — short-form notice según el Article 12 de la licencia.
