"""CLI de OSS Auditor — comando `oss-audit`."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .pipeline import run_audit
from .reporter.markdown import render_markdown
from .storage import DEFAULT_DB, get_audit, list_audits, save_audit

load_dotenv()

app = typer.Typer(
    name="oss-audit",
    help="Auditoría integral de proyectos open-source: técnico + negocio + comunidad.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def audit(
    source: str = typer.Argument(..., help="URL de GitHub o path local al repo"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Guardar reporte en archivo (.md o .json)"),
    skip_business: bool = typer.Option(False, "--skip-business", help="Omitir análisis con LLM"),
    skip_community: bool = typer.Option(False, "--skip-community", help="Omitir métricas de GitHub"),
    skip_technical: bool = typer.Option(False, "--skip-technical", help="Omitir análisis técnico"),
    save: bool = typer.Option(True, "--save/--no-save", help="Guardar en DB local"),
    json_out: bool = typer.Option(False, "--json", help="Solo emitir JSON a stdout"),
):
    """Audita un repositorio open-source."""
    def progress(label: str):
        if not json_out:
            console.print(f"[dim]{label}[/dim]")

    try:
        report = run_audit(
            source,
            skip_business=skip_business,
            skip_community=skip_community,
            skip_technical=skip_technical,
            progress=progress,
        )
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    if save:
        rid = save_audit(report)
        if not json_out:
            console.print(f"[dim]💾 Guardado con id={rid} en {DEFAULT_DB}[/dim]")

    if json_out:
        print(report.model_dump_json(indent=2))
        return

    # Render bonito
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

    if output:
        output = output.expanduser().resolve()
        if output.suffix == ".json":
            output.write_text(report.model_dump_json(indent=2))
        else:
            output.write_text(render_markdown(report))
        console.print(f"\n[green]✓[/green] Reporte guardado en [bold]{output}[/bold]")


@app.command(name="list")
def list_cmd(limit: int = typer.Option(20, "--limit", "-n")):
    """Lista las auditorías guardadas."""
    audits = list_audits(limit=limit)
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
            str(a["id"]),
            a["audited_at"][:19],
            a["repo_name"],
            f"{a['overall_score']:.1f}",
            a["grade"],
        )
    console.print(table)


@app.command()
def show(audit_id: int = typer.Argument(...),
         markdown: bool = typer.Option(False, "--markdown", "-m"),
         json_out: bool = typer.Option(False, "--json")):
    """Muestra una auditoría guardada."""
    report = get_audit(audit_id)
    if report is None:
        console.print(f"[red]No existe auditoría con id={audit_id}[/red]")
        raise typer.Exit(1)
    if json_out:
        print(report.model_dump_json(indent=2))
    elif markdown:
        print(render_markdown(report))
    else:
        console.print(render_markdown(report))


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8765):
    """Lanza la web para ver auditorías históricas."""
    import uvicorn
    from .web import create_app
    web_app = create_app()
    console.print(f"[green]Sirviendo en[/green] http://{host}:{port}")
    uvicorn.run(web_app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    app()
