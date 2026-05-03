"""Shared data models for the audit pipeline."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RepoMeta(BaseModel):
    """Basic metadata for the audited repo."""
    source: str  # URL or local path
    is_remote: bool
    is_gist: bool = False
    owner: str | None = None
    name: str
    local_path: str
    languages: dict[str, float] = Field(default_factory=dict)  # lang -> % LOC
    primary_language: str | None = None
    total_files: int = 0
    total_loc: int = 0
    repo_type: Literal["implementation", "proposal"] = "implementation"
    repo_type_reason: str = ""


class Finding(BaseModel):
    """Individual finding from any pillar."""
    severity: Literal["info", "low", "medium", "high", "critical"]
    category: str
    title: str
    detail: str
    location: str | None = None
    recommendation: str | None = None


DataStatus = Literal["available", "skipped", "unavailable"]


class TechnicalReport(BaseModel):
    """Result of the technical pillar."""
    score: float = 0.0  # 0-100
    data_status: DataStatus = "unavailable"
    test_coverage: float | None = None
    has_ci: bool = False
    has_tests: bool = False
    test_density: float = 0.0  # test_files / source_files
    has_fuzz_tests: bool = False
    has_property_tests: bool = False
    secrets_found: int = 0
    vulnerabilities: int = 0
    lint_issues: int = 0
    complexity_avg: float | None = None
    composability_score: int = 0  # 0-10
    composability_surfaces: list[str] = Field(default_factory=list)
    tools_run: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class BusinessReport(BaseModel):
    """Result of the business pillar (LLM-driven)."""
    score: float = 0.0
    data_status: DataStatus = "unavailable"
    problem_clarity: float = 0.0
    execution_vs_ambition: float = 0.0
    differentiation: float = 0.0
    market_signals: float = 0.0
    viability_risks: float = 0.0
    intellectual_contribution: float = 0.0  # NEW (v0.5): technical novelty 0-100
    summary: str = ""
    novelty_summary: str = ""               # NEW (v0.5): what's new, in 1-2 sentences
    nearest_prior_art: list[str] = Field(default_factory=list)  # NEW (v0.5)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    developer_view: str = ""                # NEW (v0.5): "do I use it?"
    cto_view: str = ""                      # NEW (v0.5): "do I adopt it?"
    investor_view: str = ""                 # NEW (v0.5): "do I fund it?"
    mind_changers: list[str] = Field(default_factory=list)  # NEW (v0.5)
    raw_analysis: str = ""
    backend: str = ""  # anthropic-api | claude-cli | openai-compatible
    model: str = ""    # the model actually invoked


class CommunityReport(BaseModel):
    """Result of the community pillar."""
    score: float = 0.0
    data_status: DataStatus = "unavailable"
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    closed_issues: int = 0
    contributors: int = 0
    bus_factor_top1_pct: float = 0.0
    bus_factor_top3_pct: float = 0.0
    commits_last_90d: int = 0
    avg_issue_close_days: float | None = None
    last_commit_days_ago: int | None = None
    has_releases: bool = False
    agent_readiness_score: int = 0  # 0-10, see community/agent_readiness.py
    agent_readiness_signals: list[str] = Field(default_factory=list)
    is_solo_active: bool = False  # solo author + recent commits -> not abandoned
    commits_per_author_90d: float = 0.0  # velocity-per-author (AI-era signal)
    findings: list[Finding] = Field(default_factory=list)


class VerdictPayload(BaseModel):
    """Top-level verdict — what to do with this audit."""
    code: str = "pass"   # bet-on-it | worth-helping | promising-prototype | ...
    label: str = "Pass"
    one_liner: str = ""
    idea_band: str = "low"           # low | medium | high
    execution_band: str = "low"
    relevance_band: str = "low"
    actions: dict[str, str] = Field(default_factory=dict)  # developer/cto/investor


class AuditReport(BaseModel):
    """Full audit report — the final output."""
    audited_at: datetime = Field(default_factory=datetime.utcnow)
    repo: RepoMeta
    overall_score: float = 0.0
    grade: Literal["bronze", "silver", "gold", "platinum", "fail"] = "fail"
    verdict: VerdictPayload = Field(default_factory=VerdictPayload)
    counterfactuals: list[str] = Field(default_factory=list)
    technical: TechnicalReport = Field(default_factory=TechnicalReport)
    business: BusinessReport = Field(default_factory=BusinessReport)
    community: CommunityReport = Field(default_factory=CommunityReport)
    executive_summary: str = ""
    top_recommendations: list[str] = Field(default_factory=list)
    lens: str = "general"  # active perspective (general | developer | cto | investor | security | maintainer)
    mode: Literal["public", "private"] = "public"  # public: GitHub-API community pillar; private: local git+process docs
