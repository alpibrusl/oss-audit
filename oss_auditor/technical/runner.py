"""Orquestador del pilar técnico — ensambla universal + per-language en un score."""
from __future__ import annotations

from pathlib import Path

from ..models import Finding, RepoMeta, TechnicalReport
from .lang_runners import run_for_languages
from .universal import universal_checks


def audit_technical(meta: RepoMeta, repo_path: Path) -> TechnicalReport:
    """Ejecuta todo el pilar técnico y produce un TechnicalReport con score 0-100.

    Score = ponderación de:
      - Tests presentes (15)
      - CI configurado (10)
      - Sin secretos (20)
      - Vulnerabilidades pocas (20)
      - Lint warnings bajo control (15)
      - Política de seguridad (5)
      - Licencia identificada (5)
      - Penalización por errores de compilación (10)
    """
    universal = universal_checks(repo_path)
    lang_results = run_for_languages(repo_path, meta.languages)

    findings: list[Finding] = list(universal.get("secret_findings", []))
    tools_run: list[str] = []
    total_vulns = 0
    total_lint_warnings = 0
    total_lint_errors = 0

    for lang, result in lang_results.items():
        if "skipped" in result or "error" in result:
            continue
        for tool_name, tool_data in result.get("tools", {}).items():
            if not isinstance(tool_data, dict) or not tool_data.get("available"):
                continue
            tools_run.append(f"{tool_name} ({lang})")
            v = tool_data.get("vulnerabilities", 0) or 0
            total_vulns += v
            total_lint_warnings += tool_data.get("warnings", 0) or 0
            total_lint_errors += tool_data.get("errors", 0) or 0
            total_lint_warnings += tool_data.get("issues", 0) or 0

            if v > 0:
                findings.append(Finding(
                    severity="high" if v > 5 else "medium",
                    category="dependencies",
                    title=f"{v} vulnerabilidades en dependencias ({tool_name})",
                    detail=f"Detectadas por {tool_name} en stack {lang}.",
                    recommendation="Actualizar dependencias afectadas o evaluar mitigaciones.",
                ))

    # ----- Scoring -----
    score = 0.0

    # Tests: 15
    if universal["has_tests"]:
        score += 15
    else:
        findings.append(Finding(
            severity="medium", category="testing",
            title="No se detectaron archivos de tests",
            detail="Heurística por nombres de archivo no encontró tests.",
            recommendation="Añadir suite de tests aumenta confianza y empleabilidad del repo.",
        ))

    # CI: 10
    if universal["has_ci"]:
        score += 10
    else:
        findings.append(Finding(
            severity="low", category="process",
            title="Sin CI configurado",
            detail="No se detectaron workflows de GitHub Actions u otros CI providers.",
            recommendation="Añadir CI básico (build + test) reduce regresiones.",
        ))

    # Secretos: 20 puntos a perder
    secrets = universal["secrets_count"]
    if secrets == 0:
        score += 20
    elif secrets <= 2:
        score += 10
    # >2: 0 puntos

    # Vulnerabilidades: 20
    if total_vulns == 0:
        score += 20
    elif total_vulns <= 3:
        score += 12
    elif total_vulns <= 10:
        score += 5

    # Lint: 15
    if total_lint_errors == 0 and total_lint_warnings < 20:
        score += 15
    elif total_lint_errors == 0 and total_lint_warnings < 100:
        score += 10
    elif total_lint_errors == 0:
        score += 5
    else:
        findings.append(Finding(
            severity="high", category="quality",
            title=f"{total_lint_errors} errores de lint/compilación",
            detail="Errores que impiden o degradan la build.",
            recommendation="Resolver errores antes de añadir features.",
        ))

    # Security policy: 5
    if universal["has_security_policy"]:
        score += 5

    # Licencia: 5
    if universal["license"] and universal["license"] != "Unknown":
        score += 5
    else:
        findings.append(Finding(
            severity="medium", category="legal",
            title="Licencia no identificada o ausente",
            detail=f"Licencia detectada: {universal['license']}",
            recommendation="Añadir LICENSE explícito (MIT, Apache-2.0, etc.).",
        ))

    # Reportes que corrieron: bonus de cobertura de análisis (hasta 10)
    coverage_bonus = min(len(tools_run) * 2, 10)
    score += coverage_bonus

    score = min(round(score, 1), 100.0)

    return TechnicalReport(
        score=score,
        has_tests=universal["has_tests"],
        has_ci=universal["has_ci"],
        secrets_found=secrets,
        vulnerabilities=total_vulns,
        lint_issues=total_lint_warnings + total_lint_errors,
        tools_run=tools_run,
        findings=findings,
        raw={
            "universal": {k: v for k, v in universal.items() if k != "secret_findings"},
            "languages": lang_results,
        },
    )
