# Contribuir a OSS Auditor

Estamos en `v0.5.x` (alpha). El feedback más útil ahora mismo no es código — es **auditorías que creas que dan veredictos erróneos**. Esos casos son los que calibran el rubric.

## Setup

```bash
git clone https://github.com/alpibrusl/oss-audit
cd oss-audit
pip install -e .

# Sanity check
python tests/smoke_test.py
oss-audit audit . --skip-business --skip-community --no-save
```

## Tipos de PR bienvenidos (ordenados por valor)

### 1. Reportes de "verdict erróneo"

Si auditás un repo y el veredicto te parece claramente mal, abre una issue con el template **"False verdict report"** indicando: URL del repo, veredicto que dio, qué veredicto crees correcto, y por qué. Esos casos guían la calibración v0.6.

### 2. Detectores de agent-readiness

`oss_auditor/community/agent_readiness.py` detecta archivos como `CLAUDE.md`, `AGENTS.md`, `.cli/`, `mcp.json`. Si conocés otra convención del ecosistema (p. ej. `.devin/`, `.aider.conf`, `.copilot/`...), añadí una categoría siguiendo el patrón existente.

### 3. Detectores de composabilidad

`oss_auditor/technical/composability.py` reconoce CLI / library / MCP / HTTP server / workspace en Python, Rust, Node, Go. Falta cobertura en Java, Kotlin, Swift, Ruby, Elixir.

### 4. Language runners

`oss_auditor/technical/lang_runners.py` define el patrón. Necesitamos runners para Java (Maven + spotbugs), Kotlin (gradle + ktlint), Swift (swiftlint), Ruby (bundler-audit + rubocop), Elixir (mix audit + credo).

### 5. Bug fixes y refactors

Antes de un refactor grande, abre una issue para discutir — los pesos del scoring y la rúbrica del verdict son frágiles y todavía sin calibrar.

## Workflow

1. Forkeá y creá una rama: `git checkout -b feat/mi-feature`.
2. Code → tests → smoke (`python tests/smoke_test.py`).
3. Auto-audita: `oss-audit audit . --skip-business --no-save` debería seguir scoreando ≥ silver en técnico tras tu cambio.
4. PR con descripción concreta de qué cambia y por qué. Si añadís un detector, incluí 1-2 ejemplos de repos donde dispara.

## Lo que NO buscamos ahora

- Reescritura de la rúbrica entera. Hay calibración pendiente con datos reales.
- PyPI publish. Después de v0.6.
- Más backends LLM hasta tener métrica real de cuál usa la gente.

## Licencia

Todos los PRs se aceptan bajo [EUPL-1.2](LICENSE) — la licencia del proyecto.
