# OSS Auditor

Auditoría integral para proyectos open-source: **técnico + negocio + comunidad** en un solo CLI.

## Por qué

Las herramientas existentes (Snyk, OpenSSF Scorecard, Sonar) se quedan en lo técnico. Este auditor añade:

- **Análisis de negocio basado en evidencia**: no solo el README, sino estructura del proyecto, manifests, código de entry points, commits recientes, issues — todo el dossier le llega a Claude para que evalúe la *ejecución observable* vs la *ambición declarada*.
- **Pilar de comunidad**: bus factor real, velocity, retención, recencia.
- **Pilar técnico polilingüe**: corre las herramientas nativas de cada lenguaje (cargo audit/clippy para Rust, ruff/pip-audit para Python, npm audit para JS/TS, govulncheck para Go) más detección universal de secretos, CI, tests, licencias.

## Instalación

```bash
cd oss-auditor
pip install -e .
```

Variables de entorno (en `.env` o exportadas):

```bash
ANTHROPIC_API_KEY=sk-ant-...   # requerido para análisis de negocio
GITHUB_TOKEN=ghp_...           # opcional; sin él, GitHub API limita a 60 req/h
```

Herramientas opcionales (mejoran el análisis técnico si están instaladas):

- `gitleaks` (secretos)
- `cargo` + `cargo-audit` (Rust)
- `ruff`, `pip-audit` (Python)
- `npm` (JS/TS)
- `govulncheck` (Go)

## Uso

```bash
# Audita un repo remoto
oss-audit audit https://github.com/alpibrusl/lex-lang

# Audita un repo local
oss-audit audit ~/code/mi-proyecto

# Guarda reporte en markdown
oss-audit audit https://github.com/alpibrusl/lex-lang -o lex-lang-audit.md

# Solo el pilar técnico (rápido, sin coste de LLM)
oss-audit audit https://github.com/alpibrusl/lex-lang --skip-business --skip-community

# Solo JSON a stdout (para scripting)
oss-audit audit https://github.com/alpibrusl/lex-lang --json

# Listar auditorías guardadas
oss-audit list

# Ver una auditoría guardada
oss-audit show 1 --markdown

# Lanzar la web local para navegar el histórico
oss-audit serve
```

## Arquitectura

```
oss_auditor/
├── cli.py                      # Comando oss-audit
├── pipeline.py                 # Orquestador end-to-end
├── ingestion.py                # Clone/local + detección de lenguajes
├── models.py                   # Pydantic schemas
├── technical/
│   ├── runner.py               # Score técnico
│   ├── universal.py            # Secretos, CI, tests, licencia
│   └── lang_runners.py         # cargo, ruff, npm, govulncheck...
├── business/
│   ├── context_builder.py      # Dossier rico (NO solo README)
│   └── analyzer.py             # Llama a Claude con rúbrica estructurada
├── community/
│   └── github_metrics.py       # Bus factor, velocity, etc.
├── reporter/
│   ├── scorer.py               # Score agregado y grades
│   └── markdown.py             # Render de reportes
├── storage/db.py               # SQLite local
└── web.py                      # FastAPI para histórico
```

## Pesos del score global

- 40% Técnico
- 35% Negocio
- 25% Comunidad

Grades: 90+ Platinum, 75+ Gold, 60+ Silver, 40+ Bronze, <40 Fail.
