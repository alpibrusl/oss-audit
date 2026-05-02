"""Verdict layer: el "qué hago con esta info" del reporte.

Tres ejes a partir de los pilares:
- idea = (problem_clarity + differentiation + intellectual_contribution) / 3
- execution = report.technical.score
- relevance = (business.market_signals + community.score) / 2

Cada eje cae en {low, medium, high} (umbrales 40 y 70) y la
combinación elige uno de 8 veredictos. Cada veredicto trae acciones
concretas para developer / CTO / investor.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models import AuditReport


@dataclass
class Verdict:
    code: str
    label: str
    one_liner: str
    idea_band: str
    execution_band: str
    relevance_band: str
    actions: dict[str, str] = field(default_factory=dict)


def _band(score: float) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _idea_score(report: AuditReport) -> float:
    b = report.business
    parts = [b.problem_clarity, b.differentiation]
    if b.intellectual_contribution > 0:
        parts.append(b.intellectual_contribution)
    return sum(parts) / len(parts) if parts else 0.0


def _execution_score(report: AuditReport) -> float:
    if report.repo.repo_type == "proposal":
        # En proposal-mode no hay ejecución de código. La "ejecución"
        # son: claridad del spec + commits del autor (mantenimiento).
        return (report.business.execution_vs_ambition + report.community.score) / 2
    return report.technical.score


def _relevance_score(report: AuditReport) -> float:
    return (report.business.market_signals + report.community.score) / 2


VERDICTS: dict[tuple[str, str, str], tuple[str, str, str]] = {
    # (idea, execution, relevance) -> (code, label, one_liner)
    ("high", "high", "high"): (
        "bet-on-it", "Bet on it",
        "Buena idea, buena ejecución, demanda real. Adopta, contribuye o invierte."),
    ("high", "high", "medium"): (
        "bet-on-it", "Bet on it",
        "Buena idea, buena ejecución, demanda creciente. Adopta o contribuye."),
    ("high", "low", "high"): (
        "worth-helping", "Worth helping",
        "Buena idea con ejecución débil y demanda clara. Aporta, forkea, "
        "o financia al equipo para cerrar la brecha."),
    ("high", "low", "medium"): (
        "worth-helping", "Worth helping",
        "Buena idea, ejecución incipiente. Riesgo alto pero upside grande."),
    ("high", "medium", "medium"): (
        "promising-prototype", "Promising prototype",
        "Idea sólida, ejecución a medio camino. Volver en 3 meses."),
    ("high", "medium", "low"): (
        "promising-prototype", "Promising prototype",
        "Buena idea ejecutándose ok pero sin demanda visible aún."),
    ("high", "high", "low"): (
        "ahead-of-its-time", "Ahead of its time",
        "Trabajo brillante sin mercado todavía. Sigue de cerca; no apuestes hoy."),
    ("low", "high", "high"): (
        "solid-commodity", "Solid commodity",
        "Resuelve un problema real con buena ejecución, pero sin "
        "diferenciación. Adopta si lo necesitas; no esperes upside."),
    ("low", "high", "medium"): (
        "solid-commodity", "Solid commodity",
        "Buena ejecución de un problema conocido. Útil, no novedoso."),
    ("low", "high", "low"): (
        "skill-in-search", "Skill in search of a problem",
        "Builder fuerte resolviendo un problema irrelevante. El talento "
        "podría ser reutilizable; el proyecto no."),
    ("medium", "low", "low"): (
        "incomplete-thesis", "Incomplete thesis",
        "No hay suficiente señal. Vuelve cuando tenga más código o tracción."),
    ("medium", "medium", "medium"): (
        "promising-prototype", "Promising prototype",
        "Todo a medio camino. Si te gusta el espacio, vale la pena seguirlo."),
}


_DEFAULT = (
    "pass", "Pass",
    "Sin señales suficientes en ningún eje. Pasar.",
)

_INDETERMINATE = (
    "indeterminate", "Indeterminate",
    "Faltan datos en al menos 2 de los 3 ejes (idea / ejecución / "
    "relevancia). Veredicto suspendido hasta tener más señal.",
)


ACTIONS_TEMPLATE: dict[str, dict[str, str]] = {
    "bet-on-it": {
        "developer": "Adopta en producción si el caso de uso encaja. Considera contribuir.",
        "cto": "Adopta o pilota seriamente. Equipo hireable. Stack risk bajo.",
        "investor": "Fundable. Stage según madurez observable. Riesgo principal: ejecución sostenida.",
    },
    "worth-helping": {
        "developer": "Vale la pena forkear o aportar PRs. No usar en prod aún.",
        "cto": "Pilota si el problema es estratégico. Considera contratar al maintainer.",
        "investor": "Posible inversión talent-first; el equipo > el proyecto actual. Acquihire posible.",
    },
    "promising-prototype": {
        "developer": "Watch. Marca con star, revisa en 3 meses.",
        "cto": "No adoptar todavía. Considera para roadmap futuro.",
        "investor": "Pre-seed signal. Track el progreso, no commitear aún.",
    },
    "ahead-of-its-time": {
        "developer": "Aprende de la tecnología. Demasiado nicho para producción.",
        "cto": "Track. Útil si el mercado se mueve hacia este modelo.",
        "investor": "Riesgo de timing. No fundable hoy salvo deep-tech con tesis larga.",
    },
    "solid-commodity": {
        "developer": "Adopta si necesitas la funcionalidad. Sin upside técnico.",
        "cto": "Stack risk muy bajo. Bueno para llenar un hueco táctico.",
        "investor": "No fundable como diferenciado. Posible target de adquisición operativa.",
    },
    "skill-in-search": {
        "developer": "Skip el proyecto. El autor podría ser interesante de seguir.",
        "cto": "Considera al maintainer para tu equipo, no al proyecto.",
        "investor": "Talent-acquihire. El proyecto en sí no es la inversión.",
    },
    "incomplete-thesis": {
        "developer": "Demasiado pronto. Sin acción.",
        "cto": "No adoptar. Sin información para decidir.",
        "investor": "Pre-pre-seed. Sin tesis articulada todavía.",
    },
    "pass": {
        "developer": "Skip.",
        "cto": "Pass.",
        "investor": "Pass.",
    },
    "indeterminate": {
        "developer": "Datos insuficientes. Re-audita con todos los pilares activos.",
        "cto": "No hay base para decidir adopción. Requiere análisis completo.",
        "investor": "Sin tesis articulable. Cierra los gaps de datos antes de evaluar.",
    },
}


def _axes_with_data(report: AuditReport) -> dict[str, bool]:
    """¿Qué ejes del verdict tienen datos reales detrás?

    - idea: requiere el pilar de negocio (problem_clarity, differentiation,
      intellectual_contribution).
    - execution: el técnico (implementation) o negocio+comunidad (proposal).
    - relevance: requiere comunidad (señal primaria de demanda).
    """
    biz_ok = report.business.data_status == "available"
    tech_ok = report.technical.data_status == "available"
    com_ok = report.community.data_status == "available"
    is_proposal = report.repo.repo_type == "proposal"
    return {
        "idea": biz_ok,
        "execution": (biz_ok and com_ok) if is_proposal else tech_ok,
        "relevance": com_ok,
    }


def compute_verdict(report: AuditReport) -> Verdict:
    idea = _idea_score(report)
    execution = _execution_score(report)
    relevance = _relevance_score(report)

    axes = _axes_with_data(report)
    bands = {
        "idea": _band(idea) if axes["idea"] else "n/a",
        "execution": _band(execution) if axes["execution"] else "n/a",
        "relevance": _band(relevance) if axes["relevance"] else "n/a",
    }

    if sum(axes.values()) < 2:
        code, label, one_liner = _INDETERMINATE
    else:
        key = (bands["idea"], bands["execution"], bands["relevance"])
        code, label, one_liner = VERDICTS.get(key, _DEFAULT)

    return Verdict(
        code=code,
        label=label,
        one_liner=one_liner,
        idea_band=bands["idea"],
        execution_band=bands["execution"],
        relevance_band=bands["relevance"],
        actions=dict(ACTIONS_TEMPLATE.get(code, ACTIONS_TEMPLATE["pass"])),
    )


def compute_counterfactuals(report: AuditReport) -> list[str]:
    """¿Qué hipotéticos cambios moverían el veredicto? Programáticos, baratos.

    Solo simulamos +30 al pilar más débil y reportamos si el band sube.
    """
    out: list[str] = []
    current = compute_verdict(report)

    pillars = [
        ("technical", report.technical.score, "el pilar técnico"),
        ("business", report.business.score, "el pilar de tesis & innovación"),
        ("community", report.community.score, "el pilar de comunidad"),
    ]
    weakest = min(pillars, key=lambda p: p[1])
    if weakest[1] >= 70:
        return out  # nada que mejorar dramáticamente

    target = min(weakest[1] + 30, 100)
    # Construir un report hipotético. El pilar mejorado también pasa a
    # estar `available` — un score más alto sin datos detrás no es
    # reportable como counterfactual.
    cloned = report.model_copy(deep=True)
    if weakest[0] == "technical":
        cloned.technical.score = target
        cloned.technical.data_status = "available"
    elif weakest[0] == "business":
        cloned.business.score = target
        cloned.business.problem_clarity = max(cloned.business.problem_clarity, 70)
        cloned.business.differentiation = max(cloned.business.differentiation, 70)
        cloned.business.data_status = "available"
    else:
        cloned.community.score = target
        cloned.community.data_status = "available"

    new_verdict = compute_verdict(cloned)
    if new_verdict.code != current.code:
        out.append(
            f"Si {weakest[2]} pasara de {weakest[1]:.0f} a {target:.0f}, "
            f"el veredicto cambiaría de `{current.code}` a `{new_verdict.code}`."
        )
    return out
