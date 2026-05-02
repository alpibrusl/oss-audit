"""Web mínima para ver auditorías históricas."""
from __future__ import annotations

import markdown as md
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from .reporter.markdown import render_markdown
from .storage import get_audit, list_audits

PAGE_TEMPLATE = """<!doctype html>
<html lang="es"><head>
<meta charset="utf-8"><title>OSS Auditor</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 920px;
         margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; line-height: 1.55; }}
  h1, h2, h3 {{ line-height: 1.2; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #ddd; padding: 0.4rem 0.6rem; text-align: left; }}
  th {{ background: #f4f4f4; }}
  a {{ color: #0366d6; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .grade {{ display: inline-block; padding: 0.2rem 0.5rem; border-radius: 4px;
            font-weight: bold; font-size: 0.85rem; }}
  .platinum {{ background: #e9d8fd; color: #553c9a; }}
  .gold {{ background: #fef3c7; color: #92400e; }}
  .silver {{ background: #e5e7eb; color: #374151; }}
  .bronze {{ background: #fed7aa; color: #9a3412; }}
  .fail {{ background: #fecaca; color: #991b1b; }}
  pre {{ background: #f6f8fa; padding: 0.8rem; border-radius: 4px; overflow-x: auto; }}
  code {{ background: #f6f8fa; padding: 0.1rem 0.3rem; border-radius: 3px; }}
  .nav {{ margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid #eee; }}
</style></head><body>
<div class="nav"><a href="/">← Lista de auditorías</a></div>
{body}
</body></html>"""


def create_app() -> FastAPI:
    app = FastAPI(title="OSS Auditor")

    @app.get("/", response_class=HTMLResponse)
    def index():
        audits = list_audits(limit=100)
        if not audits:
            return PAGE_TEMPLATE.format(body=(
                "<h1>OSS Auditor</h1><p>No hay auditorías guardadas. "
                "Ejecuta <code>oss-audit &lt;url&gt;</code> para crear una.</p>"
            ))
        rows = []
        for a in audits:
            grade = a["grade"]
            rows.append(
                f"<tr><td>{a['id']}</td>"
                f"<td>{a['audited_at'][:19]}</td>"
                f"<td><a href='/audit/{a['id']}'>{a['repo_name']}</a></td>"
                f"<td>{a['overall_score']:.1f}</td>"
                f"<td><span class='grade {grade}'>{grade.upper()}</span></td>"
                f"<td>T:{a['technical_score']:.0f} / B:{a['business_score']:.0f} / "
                f"C:{a['community_score']:.0f}</td></tr>"
            )
        body = (
            "<h1>OSS Auditor</h1>"
            "<table><thead><tr><th>ID</th><th>Fecha</th><th>Repo</th>"
            "<th>Score</th><th>Grade</th><th>Pilares</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
        return PAGE_TEMPLATE.format(body=body)

    @app.get("/audit/{audit_id}", response_class=HTMLResponse)
    def view(audit_id: int):
        report = get_audit(audit_id)
        if report is None:
            raise HTTPException(404, "Auditoría no encontrada")
        md_text = render_markdown(report)
        html = md.markdown(md_text, extensions=["tables", "fenced_code"])
        return PAGE_TEMPLATE.format(body=html)

    @app.get("/audit/{audit_id}/json")
    def view_json(audit_id: int):
        report = get_audit(audit_id)
        if report is None:
            raise HTTPException(404, "Auditoría no encontrada")
        return JSONResponse(report.model_dump(mode="json"))

    return app
