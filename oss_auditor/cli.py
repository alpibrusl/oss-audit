"""CLI de OSS Auditor — comando `oss-audit` (ACLI-compliant)."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import typer
from acli import (
    ACLIApp,
    NotFoundError,
    OutputFormat,
    UpstreamError,
    acli_command,
    emit,
    success_envelope,
)
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .pipeline import run_audit
from .reporter.badge import to_endpoint_payload, to_markdown, to_shields_url
from .reporter.markdown import render_markdown
from .storage import DEFAULT_DB, get_audit, list_audits, save_audit

load_dotenv()

app = ACLIApp(
    name="oss-audit",
    version="0.3.0",
    help="Auditoría integral de proyectos open-source: técnico + negocio + comunidad.",
)
console = Console()


def _emit_or_render(
    envelope: dict,
    output: OutputFormat,
    render_text: Callable[[], None],
) -> None:
    """Render with Rich for text mode, delegate to the SDK for json/table."""
    if output == OutputFormat.text:
        render_text()
    else:
        emit(envelope, output)


def _render_audit_summary(report) -> None:
    grade_color = {"platinum": "magenta", "gold": "yellow", "silver": "white",
                   "bronze": "red", "fail": "bright_red"}.get(report.grade, "white")
    console.print()
    console.print(Panel.fit(
        f"[bold]{report.repo.name}[/bold]\n"
        f"Score: [bold {grade_color}]{report.overall_score}/100[/bold {grade_color}] "
        f"({report.grade.upper()})",
        title="OSS Auditor", border_style=grade_color,
    ))
    table = Table(title="Pilares", show_header=True, header_style="bold")
    table.add_column("Pilar")
    table.add_column("Score", justify="right")
    table.add_column("Peso", justify="right")
    table.add_row("🔧 Técnico", f"{report.technical.score:.1f}", "40%")
    table.add_row("💼 Negocio", f"{report.business.score:.1f}", "35%")
    table.add_row("👥 Comunidad", f"{report.community.score:.1f}", "25%")
    console.print(table)
    if report.executive_summary:
        console.print()
        console.print(Panel(report.executive_summary, title="Resumen ejecutivo",
                            border_style="cyan"))
    if report.top_recommendations:
        console.print("\n[bold]Top recomendaciones:[/bold]")
        for i, rec in enumerate(report.top_recommendations, 1):
            console.print(f"  {i}. {rec}")


@app.command()
@acli_command(
    examples=[
        ("Audit a remote GitHub repo",
         "oss-audit audit https://github.com/alpibrusl/lex-lang"),
        ("Audit a local repo, technical pillar only",
         "oss-audit audit . --skip-business --skip-community"),
        ("Get a structured envelope for an agent",
         "oss-audit audit . --skip-business --skip-community --output json"),
    ],
    idempotent=True,
    see_also=["list", "show", "serve"],
)
def audit(
    source: str = typer.Argument(..., help="GitHub URL or local path. type:string"),
    out_file: Path | None = typer.Option(
        None, "--out-file", "-f",
        help="Save the rendered report to a .md or .json file. type:path",
    ),
    skip_business: bool = typer.Option(
        False, "--skip-business", help="Skip LLM business analysis. type:bool"),
    skip_community: bool = typer.Option(
        False, "--skip-community", help="Skip GitHub community metrics. type:bool"),
    skip_technical: bool = typer.Option(
        False, "--skip-technical", help="Skip technical pillar. type:bool"),
    save: bool = typer.Option(
        True, "--save/--no-save", help="Persist to local SQLite DB. type:bool"),
    output: OutputFormat = typer.Option(
        OutputFormat.text, help="Output format. type:enum[text|json|table]"),
) -> None:
    """Audita un repositorio open-source (técnico + negocio + comunidad)."""
    start = time.time()

    def progress(label: str):
        if output == OutputFormat.text:
            console.print(f"[dim]{label}[/dim]")

    try:
        report = run_audit(
            source,
            skip_business=skip_business,
            skip_community=skip_community,
            skip_technical=skip_technical,
            progress=progress,
        )
    except FileNotFoundError as e:
        raise NotFoundError(str(e), hint="Comprueba la URL o el path local.")
    except Exception as e:  # noqa: BLE001 - surface as upstream failure
        raise UpstreamError(f"El pipeline de auditoría falló: {e}")

    rid: int | None = save_audit(report) if save else None

    if out_file is not None:
        out_file = out_file.expanduser().resolve()
        if out_file.suffix == ".json":
            out_file.write_text(report.model_dump_json(indent=2))
        else:
            out_file.write_text(render_markdown(report))

    data = report.model_dump(mode="json")
    if rid is not None:
        data["saved_id"] = rid
    if out_file is not None:
        data["report_file"] = str(out_file)

    envelope = success_envelope(
        "audit", data, version="0.3.0", start_time=start)

    def render_text():
        _render_audit_summary(report)
        if rid is not None:
            console.print(f"\n[dim]💾 Guardado con id={rid} en {DEFAULT_DB}[/dim]")
        if out_file is not None:
            console.print(f"[green]✓[/green] Reporte guardado en [bold]{out_file}[/bold]")

    _emit_or_render(envelope, output, render_text)


@app.command(name="list")
@acli_command(
    examples=[
        ("List the latest 20 audits", "oss-audit list"),
        ("List 50 audits as JSON for an agent", "oss-audit list -n 50 --output json"),
    ],
    idempotent=True,
    see_also=["audit", "show"],
)
def list_cmd(
    limit: int = typer.Option(20, "--limit", "-n", help="Max audits to return. type:int"),
    output: OutputFormat = typer.Option(
        OutputFormat.text, help="Output format. type:enum[text|json|table]"),
) -> None:
    """Lista las auditorías guardadas."""
    start = time.time()
    audits = list_audits(limit=limit)
    envelope = success_envelope(
        "list", {"audits": audits, "count": len(audits)},
        version="0.3.0", start_time=start)

    def render_text():
        if not audits:
            console.print("[yellow]No hay auditorías guardadas todavía.[/yellow]")
            return
        table = Table(title="Auditorías guardadas")
        table.add_column("ID", justify="right")
        table.add_column("Fecha")
        table.add_column("Repo")
        table.add_column("Score", justify="right")
        table.add_column("Grade")
        for a in audits:
            table.add_row(
                str(a["id"]), a["audited_at"][:19], a["repo_name"],
                f"{a['overall_score']:.1f}", a["grade"],
            )
        console.print(table)

    _emit_or_render(envelope, output, render_text)


@app.command()
@acli_command(
    examples=[
        ("Show audit #1 as markdown", "oss-audit show 1"),
        ("Get the full audit envelope as JSON", "oss-audit show 1 --output json"),
    ],
    idempotent=True,
    see_also=["list", "audit"],
)
def show(
    audit_id: int = typer.Argument(..., help="Audit ID from `oss-audit list`. type:int"),
    output: OutputFormat = typer.Option(
        OutputFormat.text, help="Output format. type:enum[text|json|table]"),
) -> None:
    """Muestra una auditoría guardada."""
    start = time.time()
    report = get_audit(audit_id)
    if report is None:
        raise NotFoundError(
            f"No existe auditoría con id={audit_id}",
            hint="Ejecuta `oss-audit list` para ver los IDs disponibles.",
        )
    envelope = success_envelope(
        "show", report.model_dump(mode="json"),
        version="0.3.0", start_time=start)

    def render_text():
        console.print(render_markdown(report))

    _emit_or_render(envelope, output, render_text)


@app.command()
@acli_command(
    examples=[
        ("Markdown snippet for the latest audit", "oss-audit badge"),
        ("Static shields.io URL for audit #3", "oss-audit badge 3 --format url"),
        ("JSON endpoint payload to commit to your repo",
         "oss-audit badge --format endpoint --output json > badge.json"),
    ],
    idempotent=True,
    see_also=["audit", "list", "show"],
)
def badge(
    audit_id: int | None = typer.Argument(
        None, help="Audit ID. Defaults to most recent. type:int"),
    format_: str = typer.Option(
        "markdown", "--format",
        help="markdown | url | endpoint. type:enum[markdown|url|endpoint]"),
    label: str = typer.Option("oss-audit", "--label", help="Badge label. type:string"),
    link: str | None = typer.Option(
        None, "--link", help="URL the badge links to (markdown only). type:string"),
    output: OutputFormat = typer.Option(
        OutputFormat.text, help="Output format. type:enum[text|json|table]"),
) -> None:
    """Genera un badge shields.io a partir de una auditoría guardada."""
    start = time.time()
    if audit_id is None:
        recent = list_audits(limit=1)
        if not recent:
            raise NotFoundError(
                "No hay auditorías guardadas todavía.",
                hint="Ejecuta `oss-audit audit <repo>` primero.",
            )
        audit_id = recent[0]["id"]
    report = get_audit(audit_id)
    if report is None:
        raise NotFoundError(
            f"No existe auditoría con id={audit_id}",
            hint="Ejecuta `oss-audit list` para ver IDs disponibles.",
        )

    if format_ == "markdown":
        rendered: str | dict = to_markdown(report, link_url=link, label=label)
    elif format_ == "url":
        rendered = to_shields_url(report, label=label)
    elif format_ == "endpoint":
        rendered = to_endpoint_payload(report, label=label)
    else:
        from acli import InvalidArgsError
        raise InvalidArgsError(
            f"Formato desconocido: {format_}",
            hint="Usa: markdown | url | endpoint",
        )

    envelope = success_envelope(
        "badge",
        {"audit_id": audit_id, "format": format_, "rendered": rendered,
         "score": report.overall_score, "grade": report.grade},
        version="0.3.0", start_time=start,
    )

    def render_text():
        if isinstance(rendered, dict):
            console.print_json(data=rendered)
        else:
            console.print(rendered)

    _emit_or_render(envelope, output, render_text)


@app.command()
@acli_command(
    examples=[
        ("Serve on default port", "oss-audit serve"),
        ("Serve on a custom host:port", "oss-audit serve --host 0.0.0.0 --port 9000"),
    ],
    idempotent=True,
)
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address. type:string"),
    port: int = typer.Option(8765, help="Bind port. type:int"),
) -> None:
    """Lanza la web local para navegar el histórico de auditorías."""
    import uvicorn

    from .web import create_app

    web_app = create_app()
    console.print(f"[green]Sirviendo en[/green] http://{host}:{port}")
    uvicorn.run(web_app, host=host, port=port, log_level="warning")


def main() -> None:
    """Entry point for the `oss-audit` script."""
    app.run()


if __name__ == "__main__":
    main()
