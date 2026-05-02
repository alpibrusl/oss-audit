"""Almacenamiento de auditorías históricas en SQLite local."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from ..models import AuditReport

DEFAULT_DB = Path.home() / ".oss-auditor" / "audits.db"


def _ensure_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audited_at TEXT NOT NULL,
            source TEXT NOT NULL,
            repo_name TEXT NOT NULL,
            overall_score REAL NOT NULL,
            grade TEXT NOT NULL,
            technical_score REAL NOT NULL,
            business_score REAL NOT NULL,
            community_score REAL NOT NULL,
            report_json TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_audits_source ON audits(source);
    """)
    conn.commit()
    return conn


def save_audit(report: AuditReport, db_path: Path = DEFAULT_DB) -> int:
    """Guarda una auditoría. Devuelve el ID asignado."""
    conn = _ensure_db(db_path)
    cur = conn.execute(
        """INSERT INTO audits (audited_at, source, repo_name, overall_score, grade,
                               technical_score, business_score, community_score, report_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            report.audited_at.isoformat(),
            report.repo.source,
            report.repo.name,
            report.overall_score,
            report.grade,
            report.technical.score,
            report.business.score,
            report.community.score,
            report.model_dump_json(),
        ),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def list_audits(db_path: Path = DEFAULT_DB, limit: int = 50) -> list[dict]:
    if not db_path.exists():
        return []
    conn = _ensure_db(db_path)
    cur = conn.execute(
        """SELECT id, audited_at, source, repo_name, overall_score, grade,
                  technical_score, business_score, community_score
           FROM audits ORDER BY audited_at DESC LIMIT ?""",
        (limit,),
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return rows


def get_audit(audit_id: int, db_path: Path = DEFAULT_DB) -> AuditReport | None:
    if not db_path.exists():
        return None
    conn = _ensure_db(db_path)
    cur = conn.execute("SELECT report_json FROM audits WHERE id = ?", (audit_id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    return AuditReport.model_validate_json(row[0])
