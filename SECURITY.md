# Política de seguridad

OSS Auditor está en alpha (`v0.5.x`); no hay un canal privado de divulgación todavía. Si encontrás una vulnerabilidad:

- **Privada / sensible** (p. ej. ejecución arbitraria al auditar un repo malicioso, leak de variables de entorno, etc.): abre una issue **vacía** y mencioná `@alpibrusl` para que te contactemos en privado por mail. No publiques los detalles en la issue.
- **Pública / baja severidad** (un secret pattern que no detecta, un falso positivo en `agent_readiness`, etc.): issue normal con label `security`.

## Áreas de riesgo conocidas

- `ingestion.py` ejecuta `git clone --depth 1` contra URLs arbitrarias provistas por el usuario. No ejecuta hooks de git pero un repo malicioso podría intentar abusar de bugs de git mismo.
- El pilar técnico **no ejecuta** código del repo auditado salvo herramientas explícitas (cargo audit, ruff, npm audit, govulncheck) que sí parsean el árbol de dependencias. Si no confías en el repo, audita en sandbox.
- `business/analyzer.py` envía contenido del repo (README, manifests, muestras de código, commits, issues) al backend LLM configurado. Si auditás repos privados, asegúrate de que tu backend respete la confidencialidad (no `openai-compatible` con base URL público para datos sensibles).

## Lo que NO hacemos

- Procesar repos de >1GB sin truncado explícito.
- Ejecutar tests del repo auditado (eso requiere su propio sandboxing).
- Recursar en `node_modules`, `target/`, `.git/`, etc.
