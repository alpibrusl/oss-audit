"""Local web UI to browse audit history + calibration panel.

No auth, no backend; reads from the local SQLite. Designed as an
internal calibration tool (v0.6) — we add comparison views,
per-repo time series, and verdict filters to spot rubric
inconsistencies.
"""
from __future__ import annotations

from collections import Counter, defaultdict

import markdown as md
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from .reporter.markdown import render_markdown
from .storage import get_audit, list_audits

PAGE_TEMPLATE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><title>OSS Auditor — {title}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 1080px;
         margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; line-height: 1.55; }}
  h1, h2, h3 {{ line-height: 1.2; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #ddd; padding: 0.4rem 0.6rem; text-align: left; }}
  th {{ background: #f4f4f4; }}
  a {{ color: #0366d6; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .grade {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px;
            font-weight: bold; font-size: 0.8rem; }}
  .platinum {{ background: #e9d8fd; color: #553c9a; }}
  .gold {{ background: #fef3c7; color: #92400e; }}
  .silver {{ background: #e5e7eb; color: #374151; }}
  .bronze {{ background: #fed7aa; color: #9a3412; }}
  .fail {{ background: #fecaca; color: #991b1b; }}
  .verdict {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px;
              font-size: 0.8rem; font-family: monospace; }}
  .v-bet-on-it {{ background: #d1fae5; color: #065f46; }}
  .v-worth-helping {{ background: #fef3c7; color: #92400e; }}
  .v-promising-prototype {{ background: #dbeafe; color: #1e40af; }}
  .v-ahead-of-its-time {{ background: #cffafe; color: #155e75; }}
  .v-solid-commodity {{ background: #f3f4f6; color: #374151; }}
  .v-skill-in-search {{ background: #fae8ff; color: #86198f; }}
  .v-incomplete-thesis {{ background: #fee2e2; color: #991b1b; }}
  .v-pass {{ background: #fecaca; color: #7f1d1d; }}
  pre {{ background: #f6f8fa; padding: 0.8rem; border-radius: 4px; overflow-x: auto; }}
  code {{ background: #f6f8fa; padding: 0.1rem 0.3rem; border-radius: 3px; }}
  .nav {{ margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid #eee;
          display: flex; gap: 1rem; flex-wrap: wrap; }}
  .nav a {{ font-size: 0.9rem; }}
  .panel {{ background: #f9fafb; padding: 1rem; border-radius: 6px; margin: 1rem 0;
            border-left: 4px solid #6366f1; }}
  .compare-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
  .compare-grid > div {{ border: 1px solid #ddd; border-radius: 4px; padding: 0.8rem; }}
  .gap-warn {{ color: #b91c1c; font-weight: bold; }}
  .stat {{ display: inline-block; padding: 0.5rem 1rem; margin-right: 0.5rem;
           background: #fff; border: 1px solid #ddd; border-radius: 4px;
           min-width: 120px; }}
  .stat-num {{ font-size: 1.4rem; font-weight: bold; }}
  .stat-label {{ font-size: 0.8rem; color: #666; }}
</style></head><body>
<div class="nav">
  <a href="/">📋 List</a>
  <a href="/dashboard">📊 Dashboard</a>
  <a href="/calibration">🔬 Calibration</a>
</div>
{body}
</body></html>"""


def _grade_html(grade: str) -> str:
    return f"<span class='grade {grade}'>{grade.upper()}</span>"


def _verdict_html(code: str, label: str = "") -> str:
    css = "v-" + code.replace("-", "-")
    return f"<span class='verdict {css}'>{code or 'n/a'}</span>"


def _row(a: dict, report=None) -> str:
    grade = a["grade"]
    verdict_html = ""
    if report and report.verdict and report.verdict.code:
        verdict_html = _verdict_html(report.verdict.code)
    return (
        f"<tr><td>{a['id']}</td>"
        f"<td>{a['audited_at'][:19]}</td>"
        f"<td><a href='/audit/{a['id']}'>{a['repo_name']}</a></td>"
        f"<td>{a['overall_score']:.1f}</td>"
        f"<td>{_grade_html(grade)}</td>"
        f"<td>{verdict_html}</td>"
        f"<td>T:{a['technical_score']:.0f} / B:{a['business_score']:.0f} / "
        f"C:{a['community_score']:.0f}</td></tr>"
    )


def create_app() -> FastAPI:
    app = FastAPI(title="OSS Auditor")

    @app.get("/", response_class=HTMLResponse)
    def index():
        audits = list_audits(limit=200)
        if not audits:
            return PAGE_TEMPLATE.format(title="List", body=(
                "<h1>OSS Auditor</h1><p>No audits stored yet. "
                "Run <code>oss-audit audit &lt;url&gt;</code> to create one.</p>"
            ))
        # To show verdicts in the list we hydrate the report (local cache).
        rows = []
        for a in audits:
            report = get_audit(a["id"])
            rows.append(_row(a, report))
        body = (
            "<h1>📋 Stored audits</h1>"
            "<table><thead><tr><th>ID</th><th>Date</th><th>Repo</th>"
            "<th>Score</th><th>Grade</th><th>Verdict</th><th>Pillars</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
        return PAGE_TEMPLATE.format(title="List", body=body)

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard():
        audits = list_audits(limit=500)
        if not audits:
            return PAGE_TEMPLATE.format(title="Dashboard",
                                        body="<h1>📊 Dashboard</h1><p>No data.</p>")

        verdicts = Counter()
        grades = Counter()
        gap_outliers: list[tuple[str, int, float]] = []  # (repo, id, gap)

        for a in audits:
            report = get_audit(a["id"])
            if report is None:
                continue
            grades[report.grade] += 1
            if report.verdict.code:
                verdicts[report.verdict.code] += 1
            # Hallucination flag: gap between LLM market_signals and community.score
            if report.business.market_signals > 0:
                gap = report.business.market_signals - report.community.score
                if gap > 40:
                    gap_outliers.append((report.repo.name, report.repo.source, a["id"], gap))

        verdict_table = "<table><thead><tr><th>Verdict</th><th>Count</th></tr></thead><tbody>"
        for v, n in verdicts.most_common():
            verdict_table += (
                f"<tr><td><a href='/verdict/{v}'>{_verdict_html(v)}</a></td>"
                f"<td>{n}</td></tr>"
            )
        verdict_table += "</tbody></table>"

        grade_table = "<table><thead><tr><th>Grade</th><th>Count</th></tr></thead><tbody>"
        for g, n in grades.most_common():
            grade_table += f"<tr><td>{_grade_html(g)}</td><td>{n}</td></tr>"
        grade_table += "</tbody></table>"

        outliers_html = "<p><em>No significant outliers.</em></p>"
        if gap_outliers:
            gap_outliers.sort(key=lambda x: -x[3])
            outliers_html = "<table><thead><tr><th>Repo</th><th>Audit</th><th>LLM market_signals - community gap</th></tr></thead><tbody>"
            for name, source, aid, gap in gap_outliers[:20]:
                outliers_html += (
                    f"<tr><td>{name}</td><td><a href='/audit/{aid}'>#{aid}</a></td>"
                    f"<td><span class='gap-warn'>+{gap:.0f}</span></td></tr>"
                )
            outliers_html += "</tbody></table>"

        body = f"""
        <h1>📊 Dashboard</h1>
        <div>
          <span class='stat'>
            <div class='stat-num'>{len(audits)}</div>
            <div class='stat-label'>total audits</div>
          </span>
          <span class='stat'>
            <div class='stat-num'>{len(set(a['repo_name'] for a in audits))}</div>
            <div class='stat-label'>unique repos</div>
          </span>
          <span class='stat'>
            <div class='stat-num'>{verdicts.get('bet-on-it', 0)}</div>
            <div class='stat-label'>bet-on-it</div>
          </span>
          <span class='stat'>
            <div class='stat-num'>{len(gap_outliers)}</div>
            <div class='stat-label'>possible hallucinations</div>
          </span>
        </div>

        <h2>Verdict distribution</h2>
        {verdict_table}

        <h2>Grade distribution</h2>
        {grade_table}

        <h2>⚠️ Possible LLM hallucination</h2>
        <div class='panel'>
          Audits where <code>business.market_signals</code> (LLM-judged)
          exceeds <code>community.score</code> (programmatic) by more
          than 40 points. Indicator that the LLM is inventing observable
          demand.
        </div>
        {outliers_html}
        """
        return PAGE_TEMPLATE.format(title="Dashboard", body=body)

    @app.get("/calibration", response_class=HTMLResponse)
    def calibration():
        """Per-repo time series + audit comparison. Useful for spotting
        inconsistency (the same repo audited differently across runs)."""
        audits = list_audits(limit=500)
        by_source: dict[str, list[dict]] = defaultdict(list)
        for a in audits:
            by_source[a["source"]].append(a)

        rows = []
        for source, items in sorted(by_source.items(), key=lambda x: -len(x[1])):
            if len(items) < 2:
                continue
            scores = [it["overall_score"] for it in items]
            spread = max(scores) - min(scores)
            grades = [it["grade"] for it in items]
            grade_changed = len(set(grades)) > 1
            ids = " ".join(f"<a href='/audit/{it['id']}'>#{it['id']}</a>" for it in items[:5])
            warn = "⚠️ " if (spread > 10 or grade_changed) else ""
            rows.append(
                f"<tr><td>{warn}<a href='/repo?source={source}'>{items[0]['repo_name']}</a></td>"
                f"<td>{len(items)}</td>"
                f"<td>{min(scores):.1f} – {max(scores):.1f}</td>"
                f"<td>spread: {spread:.1f}</td>"
                f"<td>{ids}</td></tr>"
            )

        body = """
        <h1>🔬 Calibration panel</h1>
        <div class='panel'>
          Repos with ≥2 audits. A high spread or a grade change between
          runs may indicate (a) the repo changed, (b) the rubric is
          unstable, or (c) LLM variability. Compare specific pairs to
          diagnose.
        </div>
        """
        if rows:
            body += (
                "<table><thead><tr><th>Repo</th><th>Audits</th>"
                "<th>Score range</th><th>Spread</th><th>IDs</th></tr></thead>"
                f"<tbody>{''.join(rows)}</tbody></table>"
            )
        else:
            body += "<p><em>No repos with repeated audits yet.</em></p>"

        body += "<p>Want to compare two audits directly? <code>/compare?a=ID1&b=ID2</code></p>"
        return PAGE_TEMPLATE.format(title="Calibration", body=body)

    @app.get("/repo", response_class=HTMLResponse)
    def repo_history(source: str):
        audits = [a for a in list_audits(limit=500) if a["source"] == source]
        if not audits:
            raise HTTPException(404, "No audits for that source")
        rows = "".join(_row(a, get_audit(a["id"])) for a in audits)
        body = (
            f"<h1>History: {audits[0]['repo_name']}</h1>"
            f"<p><code>{source}</code></p>"
            "<table><thead><tr><th>ID</th><th>Date</th><th>Repo</th>"
            "<th>Score</th><th>Grade</th><th>Verdict</th><th>Pillars</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
        return PAGE_TEMPLATE.format(title=f"Repo: {audits[0]['repo_name']}", body=body)

    @app.get("/verdict/{verdict}", response_class=HTMLResponse)
    def by_verdict(verdict: str):
        audits = list_audits(limit=500)
        rows = []
        for a in audits:
            r = get_audit(a["id"])
            if r and r.verdict.code == verdict:
                rows.append(_row(a, r))
        body = (
            f"<h1>Verdict: {_verdict_html(verdict)}</h1>"
            f"<p>{len(rows)} audit(s) with this verdict.</p>"
        )
        if rows:
            body += (
                "<table><thead><tr><th>ID</th><th>Date</th><th>Repo</th>"
                "<th>Score</th><th>Grade</th><th>Verdict</th><th>Pillars</th></tr></thead>"
                f"<tbody>{''.join(rows)}</tbody></table>"
            )
        return PAGE_TEMPLATE.format(title=f"Verdict {verdict}", body=body)

    @app.get("/compare", response_class=HTMLResponse)
    def compare(a: int, b: int):
        ra = get_audit(a)
        rb = get_audit(b)
        if ra is None or rb is None:
            raise HTTPException(404, "Audit not found")

        def cell(report) -> str:
            return f"""
            <h3><a href='/audit/{report.repo.name}'>{report.repo.name}</a></h3>
            <p><strong>Score:</strong> {report.overall_score} {_grade_html(report.grade)}</p>
            <p><strong>Verdict:</strong> {_verdict_html(report.verdict.code)} — {report.verdict.label}</p>
            <p><em>{report.verdict.one_liner}</em></p>
            <p>idea={report.verdict.idea_band} · exec={report.verdict.execution_band} · relevance={report.verdict.relevance_band}</p>
            <p>T={report.technical.score:.0f} · B={report.business.score:.0f} · C={report.community.score:.0f}</p>
            <p>backend={report.business.backend or 'n/a'} · model={report.business.model or 'n/a'}</p>
            """

        body = f"""
        <h1>Compare #{a} vs #{b}</h1>
        <div class='compare-grid'>
          <div>{cell(ra)}</div>
          <div>{cell(rb)}</div>
        </div>
        """
        return PAGE_TEMPLATE.format(title=f"Compare #{a}/#{b}", body=body)

    @app.get("/audit/{audit_id}", response_class=HTMLResponse)
    def view(audit_id: int):
        report = get_audit(audit_id)
        if report is None:
            raise HTTPException(404, "Audit not found")
        md_text = render_markdown(report)
        html = md.markdown(md_text, extensions=["tables", "fenced_code"])
        return PAGE_TEMPLATE.format(title=f"Audit #{audit_id}", body=html)

    @app.get("/audit/{audit_id}/json")
    def view_json(audit_id: int):
        report = get_audit(audit_id)
        if report is None:
            raise HTTPException(404, "Audit not found")
        return JSONResponse(report.model_dump(mode="json"))

    return app
