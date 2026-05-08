"""Cross-check the Python pipeline against the lex POC implementation.

Two layers are checked:

1. **Rubric** (`lex_verdict` / `compare`): scoring + verdict from
   `lex-poc/src/adapter.lex::cross_check`. Disagreement surfaces
   ambiguity in the rubric itself — the v0.6 calibration signal.
2. **Universal detectors** (`lex_universal` / `compare_universal`):
   license classification and SECURITY.md presence from
   `lex-poc/src/universal.lex::cross_check_universal`. Validates the
   subprocess + JSON boundary for `[fs_walk, io]` code, not just
   pure rubric.

Both layers opt-in via `RUBRIC_LEX_CROSS_CHECK=1`. If the `lex`
binary isn't on `$PATH`, both silently no-op.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .models import AuditReport

LEX_BINARY = "lex"
LEX_POC_ROOT = Path(__file__).resolve().parent.parent / "lex-poc" / "src"
ADAPTER_PATH = LEX_POC_ROOT / "adapter.lex"
UNIVERSAL_PATH = LEX_POC_ROOT / "universal.lex"
INGESTION_PATH       = LEX_POC_ROOT / "ingestion.lex"
INGESTION_IO_PATH    = LEX_POC_ROOT / "ingestion_io.lex"
TECH_SCORE_PATH      = LEX_POC_ROOT / "tech_score.lex"
COMMUNITY_SCORE_PATH = LEX_POC_ROOT / "community_score.lex"
COMPOSABILITY_PATH   = LEX_POC_ROOT / "composability.lex"
LENS_SCORER_PATH     = LEX_POC_ROOT / "lens_scorer.lex"
AGENT_READINESS_PATH = LEX_POC_ROOT / "agent_readiness.lex"
HN_SOURCE_PATH       = LEX_POC_ROOT / "hn_source.lex"
TIMEOUT_SECONDS = 10


def _variant(name: str) -> dict:
    """Encode a unit variant per lex's CLI JSON convention (since #94)."""
    return {"$variant": name, "args": []}


_STATUS_VARIANTS = {
    "available":   _variant("Available"),
    "skipped":     _variant("Skipped"),
    "unavailable": _variant("Unavailable"),
}

_REPO_TYPE_VARIANTS = {
    "implementation": _variant("Implementation"),
    "proposal":       _variant("Proposal"),
}


def _report_to_lex_json(report: AuditReport) -> dict:
    """Build the Report record in the shape lex's compute_verdict expects."""
    return {
        "repo_type": _REPO_TYPE_VARIANTS[report.repo.repo_type],
        "technical": {
            "score":       float(report.technical.score),
            "data_status": _STATUS_VARIANTS[report.technical.data_status],
        },
        "business": {
            "score":                     float(report.business.score),
            "data_status":               _STATUS_VARIANTS[report.business.data_status],
            "problem_clarity":           float(report.business.problem_clarity),
            "differentiation":           float(report.business.differentiation),
            "intellectual_contribution": float(report.business.intellectual_contribution),
            "market_signals":            float(report.business.market_signals),
            "execution_vs_ambition":     float(report.business.execution_vs_ambition),
        },
        "community": {
            "score":       float(report.community.score),
            "data_status": _STATUS_VARIANTS[report.community.data_status],
        },
    }


def is_available() -> bool:
    """Return True if lex is installed and the adapter file is present."""
    return shutil.which(LEX_BINARY) is not None and ADAPTER_PATH.exists()


def lex_verdict(report: AuditReport) -> dict | None:
    """Return {'code', 'grade', 'score'} from the lex POC, or None on any failure."""
    if not is_available():
        return None
    payload = json.dumps(_report_to_lex_json(report))
    try:
        result = subprocess.run(
            [LEX_BINARY, "run", str(ADAPTER_PATH), "cross_check", payload],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or not {"code", "grade", "score"} <= parsed.keys():
        return None
    return {
        "code":  parsed["code"],
        "grade": parsed["grade"],
        "score": float(parsed["score"]),
    }


def compare(report: AuditReport, lex_result: dict) -> list[str]:
    """Return a list of human-readable disagreements between the two implementations."""
    diffs: list[str] = []
    if report.verdict.code != lex_result["code"]:
        diffs.append(
            f"verdict code: python={report.verdict.code!r} lex={lex_result['code']!r}"
        )
    if report.grade != lex_result["grade"]:
        diffs.append(f"grade: python={report.grade!r} lex={lex_result['grade']!r}")
    if abs(report.overall_score - lex_result["score"]) > 0.05:
        diffs.append(f"score: python={report.overall_score} lex={lex_result['score']}")
    return diffs


# ---------- universal-detector cross-check (pilot) ---------------

def lex_universal(repo_path: Path | str) -> dict | None:
    """Run lex's `cross_check_universal` over the repo.

    Returns a dict with these keys, or None on failure:
      license            (str)        — classified from LICENSE file
      has_security_md    (bool)       — SECURITY.md presence
      manifest_license   (str)        — from pyproject.toml/Cargo.toml ("None" if absent)
      ci_security_tools  (list[str])  — security tools mentioned in .github/workflows/*.yml
    """
    if shutil.which(LEX_BINARY) is None or not UNIVERSAL_PATH.exists():
        return None
    repo = str(Path(repo_path).resolve())
    try:
        result = subprocess.run(
            [
                LEX_BINARY, "run",
                "--allow-effects", "fs_walk,io",
                "--allow-fs-read", repo,
                str(UNIVERSAL_PATH), "cross_check_universal",
                json.dumps(repo),
            ],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    required = {"license", "has_security_md", "manifest_license", "ci_security_tools"}
    if not isinstance(parsed, dict) or not required <= parsed.keys():
        return None
    return {
        "license":           parsed["license"],
        "has_security_md":   bool(parsed["has_security_md"]),
        "manifest_license":  parsed["manifest_license"],
        "ci_security_tools": list(parsed["ci_security_tools"]),
    }


def compare_universal(
    py_license: str | None, py_has_security_md: bool, lex_result: dict,
) -> list[str]:
    """Return human-readable disagreements between the Python detectors and lex.

    Notes:
    - Python returns `None` when no LICENSE file exists; lex returns `"None"`.
      Both paths normalize to the string `"None"` for comparison.
    """
    diffs: list[str] = []
    py_lic = py_license if py_license is not None else "None"
    if py_lic != lex_result["license"]:
        diffs.append(f"license: python={py_lic!r} lex={lex_result['license']!r}")
    if py_has_security_md != lex_result["has_security_md"]:
        diffs.append(
            f"has_security_md: python={py_has_security_md} lex={lex_result['has_security_md']}"
        )
    return diffs


# ---------- pure-ingestion cross-check (pilot) -------------------

def lex_ingest(
    url: str, total_loc: int, doc_chars: int, has_traction: bool,
) -> dict | None:
    """Run lex's `cross_check_ingest` over the same inputs Python sees.

    Pure (no fs / no proc effects), so this is a fast subprocess
    roundtrip — just URL parsing + classify decision logic.

    Returns a dict with these keys, or None on failure:
      github_owner   (str)  — "" if URL isn't a GitHub repo
      github_repo    (str)
      gist_owner     (str)  — "" if URL isn't a gist
      gist_id        (str)
      classified     (str)  — "implementation" | "proposal"
      reason         (str)  — human-readable
    """
    if shutil.which(LEX_BINARY) is None or not INGESTION_PATH.exists():
        return None
    try:
        result = subprocess.run(
            [
                LEX_BINARY, "run", str(INGESTION_PATH), "cross_check_ingest",
                json.dumps(url),
                json.dumps(int(total_loc)),
                json.dumps(int(doc_chars)),
                json.dumps(bool(has_traction)),
            ],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    required = {
        "github_owner", "github_repo", "gist_owner", "gist_id",
        "classified", "reason",
    }
    if not isinstance(parsed, dict) or not required <= parsed.keys():
        return None
    return {k: parsed[k] for k in required}


def lex_ingest_io(repo_path: Path | str, has_traction: bool) -> dict | None:
    """Run lex's `cross_check_ingest_io` over the repo on disk.

    Walks the repo with `[fs_walk, io]` to compute the language
    breakdown + doc-chars + classify decision. Compared against
    Python's `detect_languages` and `classify_repo_type` outputs.

    Returns a dict with these keys, or None on failure:
      total_files (int)
      total_loc   (int)
      per_lang    (list[tuple[str, int, float]])  — sorted by lang
      doc_chars   (int)
      classified  (str)  — "implementation" | "proposal"
      reason      (str)
    """
    if shutil.which(LEX_BINARY) is None or not INGESTION_IO_PATH.exists():
        return None
    repo = str(Path(repo_path).resolve())
    try:
        result = subprocess.run(
            [
                LEX_BINARY, "run",
                "--allow-effects", "fs_walk,io",
                "--allow-fs-read", repo,
                str(INGESTION_IO_PATH), "cross_check_ingest_io",
                json.dumps(repo),
                json.dumps(bool(has_traction)),
            ],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    required = {
        "total_files", "total_loc", "per_lang",
        "doc_chars", "classified", "reason",
    }
    if not isinstance(parsed, dict) or not required <= parsed.keys():
        return None
    return {
        "total_files": int(parsed["total_files"]),
        "total_loc":   int(parsed["total_loc"]),
        "per_lang":    [tuple(x) for x in parsed["per_lang"]],
        "doc_chars":   int(parsed["doc_chars"]),
        "classified":  parsed["classified"],
        "reason":      parsed["reason"],
    }


def compare_ingest_io(
    py_total_files: int, py_total_loc: int,
    py_per_lang: dict[str, float], py_repo_type: str,
    lex_result: dict,
) -> list[str]:
    """Diff Python's detect_languages + classify_repo_type vs lex.

    Python returns percentages directly (`{lang: pct}`); lex returns
    `(lang, loc, pct)` triples. Compare on the (lang, pct) projection
    after sorting both alphabetically. The `reason` field embeds the
    LOC count, which already drops out of the loc/files comparison —
    no value comparing it character-by-character.
    """
    diffs: list[str] = []
    if py_total_files != lex_result["total_files"]:
        diffs.append(
            f"total_files: python={py_total_files} lex={lex_result['total_files']}"
        )
    if py_total_loc != lex_result["total_loc"]:
        diffs.append(
            f"total_loc: python={py_total_loc} lex={lex_result['total_loc']}"
        )
    py_pct = sorted(py_per_lang.items())
    lex_pct = sorted((lang, pct) for (lang, _, pct) in lex_result["per_lang"])
    if py_pct != lex_pct:
        diffs.append(f"per_lang_pct: python={py_pct} lex={lex_pct}")
    if py_repo_type != lex_result["classified"]:
        diffs.append(
            f"repo_type: python={py_repo_type!r} lex={lex_result['classified']!r}"
        )
    return diffs


# ---------- technical-score cross-check (pilot) -----------------

def lex_tech_score(signals: dict) -> float | None:
    """Run lex's `cross_check_tech_score` over Python's tech signals.

    Pure (no fs / no proc effects). Validates that the per-axis
    weights + thresholds + 100-cap + round-to-1 logic match between
    the two implementations — this is the calibration-sensitive
    surface that drifts as we tune.

    `signals` must contain the 13 keys from the lex `TechSignals`
    record. Returns the lex-computed score, or None on any failure.
    """
    if shutil.which(LEX_BINARY) is None or not TECH_SCORE_PATH.exists():
        return None
    try:
        result = subprocess.run(
            [
                LEX_BINARY, "run", str(TECH_SCORE_PATH),
                "cross_check_tech_score", json.dumps(signals),
            ],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or "score" not in parsed:
        return None
    return float(parsed["score"])


def compare_tech_score(py_score: float, lex_score: float) -> list[str]:
    """Diff Python's technical score against lex's, with 0.05 tolerance.

    Same threshold the report-level cross-check uses — accommodates
    1e-12-class float-arithmetic drift while still catching real
    weight changes.
    """
    if abs(py_score - lex_score) > 0.05:
        return [f"score: python={py_score} lex={lex_score}"]
    return []


# ---------- community-score cross-check (pilot) -----------------

def _opt(value):
    """Encode a Python `int | float | None` as lex `Option`."""
    if value is None:
        return {"$variant": "None", "args": []}
    return {"$variant": "Some", "args": [value]}


_OPTIONAL_FIELDS = {"last_commit_days", "avg_issue_close_days"}


def lex_community_score(signals: dict, mode: str) -> float | None:
    """Run lex's `cross_check_community_score_*` over Python's signals.

    `mode` selects between the public-mode (GitHub API) and internal-mode
    (local clone) scorers — they have different weights and inputs.
    Returns the lex-computed score, or None on any failure.

    Optional Python fields (`int | None`, `float | None`) are auto-wrapped
    into the lex `Option` encoding here so callers can stash plain values
    on `CommunityReport.raw` without thinking about marshaling.
    """
    if shutil.which(LEX_BINARY) is None or not COMMUNITY_SCORE_PATH.exists():
        return None
    if mode == "public":
        entry = "cross_check_community_score_public"
    elif mode == "private":
        entry = "cross_check_community_score_internal"
    else:
        return None
    encoded = {
        k: (_opt(v) if k in _OPTIONAL_FIELDS else v)
        for k, v in signals.items()
    }
    try:
        result = subprocess.run(
            [
                LEX_BINARY, "run", str(COMMUNITY_SCORE_PATH),
                entry, json.dumps(encoded),
            ],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or "score" not in parsed:
        return None
    return float(parsed["score"])


def compare_community_score(py_score: float, lex_score: float) -> list[str]:
    """Diff Python's community score against lex's, with 0.05 tolerance."""
    if abs(py_score - lex_score) > 0.05:
        return [f"score: python={py_score} lex={lex_score}"]
    return []


# ---------- composability cross-check (pilot) -------------------

def lex_composability(repo_path: Path | str) -> dict | None:
    """Run lex's `cross_check_composability` over the repo on disk.

    Walks pyproject.toml / Cargo.toml / package.json / etc. with
    `[fs_walk, io]` and returns the detected surfaces + capped score.

    Returns a dict with these keys, or None on failure:
      score    (int)        — `min(len(surfaces) * 2, 10)`
      surfaces (list[str])  — same order Python produces
    """
    if shutil.which(LEX_BINARY) is None or not COMPOSABILITY_PATH.exists():
        return None
    repo = str(Path(repo_path).resolve())
    try:
        result = subprocess.run(
            [
                LEX_BINARY, "run",
                "--allow-effects", "fs_walk,io",
                "--allow-fs-read", repo,
                str(COMPOSABILITY_PATH), "cross_check_composability",
                json.dumps(repo),
            ],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or "score" not in parsed or "surfaces" not in parsed:
        return None
    return {
        "score":    int(parsed["score"]),
        "surfaces": list(parsed["surfaces"]),
    }


# ---------- lens-aware scoring cross-check (pilot) --------------

def lex_lens_score(report: AuditReport, lens_name: str) -> dict | None:
    """Run lex's `cross_check_lens_score` for the given lens.

    Returns `{grade: str, score: float}`, or None on any failure.
    Pure (no fs / no proc / no net effects) — the Report record is
    serialized in the same shape `lex_verdict` uses.
    """
    if shutil.which(LEX_BINARY) is None or not LENS_SCORER_PATH.exists():
        return None
    payload = json.dumps(_report_to_lex_json(report))
    try:
        result = subprocess.run(
            [
                LEX_BINARY, "run", str(LENS_SCORER_PATH),
                "cross_check_lens_score", payload, json.dumps(lens_name),
            ],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or not {"grade", "score"} <= parsed.keys():
        return None
    return {"grade": parsed["grade"], "score": float(parsed["score"])}


def compare_lens_score(
    py_score: float, py_grade: str, lex_result: dict,
) -> list[str]:
    """Diff Python's lens-applied (overall_score, grade) vs lex's.

    Same 0.05 score tolerance the rubric cross-check uses; grade
    must match exactly (string compare).
    """
    diffs: list[str] = []
    if abs(py_score - lex_result["score"]) > 0.05:
        diffs.append(f"score: python={py_score} lex={lex_result['score']}")
    if py_grade != lex_result["grade"]:
        diffs.append(f"grade: python={py_grade!r} lex={lex_result['grade']!r}")
    return diffs


def lex_lens_guard(
    verdict_code: str, has_critical: bool, lens_name: str,
) -> str | None:
    """Run lex's `cross_check_lens_guard` to compute the post-guard verdict code.

    Pure (no fs / proc / net effects). Inputs are exactly what Python's
    `apply_lens_guard` looks at — base verdict code, the boolean
    `has_critical` over technical findings, and the lens name. The
    label / one_liner / actions rewrites in Python aren't compared
    (presentation, not calibration).
    """
    if shutil.which(LEX_BINARY) is None or not LENS_SCORER_PATH.exists():
        return None
    try:
        result = subprocess.run(
            [
                LEX_BINARY, "run", str(LENS_SCORER_PATH),
                "cross_check_lens_guard",
                json.dumps(verdict_code),
                json.dumps(bool(has_critical)),
                json.dumps(lens_name),
            ],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or "code" not in parsed:
        return None
    return str(parsed["code"])


def compare_lens_guard(py_code: str, lex_code: str) -> list[str]:
    """Diff Python's post-guard verdict code vs lex's."""
    if py_code != lex_code:
        return [f"code: python={py_code!r} lex={lex_code!r}"]
    return []


# ---------- agent-readiness cross-check (pilot) -----------------

def lex_agent_readiness(repo_path: Path | str) -> dict | None:
    """Run lex's `cross_check_agent_readiness` over the repo on disk.

    Walks the same files Python's `score_agent_readiness` looks at
    (CLAUDE.md / AGENTS.md / .cursorrules / .cli / mcp.json /
    examples/) plus the recursive examples-runnable check. Effect
    surface is `[fs_walk]` only — no file content is read, just
    sizes + listings.

    Returns `{score: int, signals: list[str]}`, or None on failure.
    """
    if shutil.which(LEX_BINARY) is None or not AGENT_READINESS_PATH.exists():
        return None
    repo = str(Path(repo_path).resolve())
    try:
        result = subprocess.run(
            [
                LEX_BINARY, "run",
                "--allow-effects", "fs_walk",
                "--allow-fs-read", repo,
                str(AGENT_READINESS_PATH), "cross_check_agent_readiness",
                json.dumps(repo),
            ],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or "score" not in parsed or "signals" not in parsed:
        return None
    return {
        "score":   int(parsed["score"]),
        "signals": list(parsed["signals"]),
    }


# ---------- HN-source URL-extractor cross-check (pilot) ---------

def lex_extract_gh_url(item_url: str, item_text: str) -> str | None:
    """Run lex's `cross_check_extract_gh_url` over the same inputs.

    Pure (no fs / proc / net effects). Returns the extracted URL,
    or None if the lex side reported no match (encoded as `""`).
    Returns None on any subprocess / parse failure too — callers
    can't distinguish "no match" from "failure" but the test suite
    asserts both lex and Python agree, which catches drift either way.
    """
    if shutil.which(LEX_BINARY) is None or not HN_SOURCE_PATH.exists():
        return None
    try:
        result = subprocess.run(
            [
                LEX_BINARY, "run", str(HN_SOURCE_PATH),
                "cross_check_extract_gh_url",
                json.dumps(item_url),
                json.dumps(item_text),
            ],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or "match_url" not in parsed:
        return None
    s = parsed["match_url"]
    return s if s else None


def compare_extract_gh_url(py_url: str | None, lex_url: str | None) -> list[str]:
    """Diff Python's `_extract_gh_url` output vs lex's."""
    if py_url != lex_url:
        return [f"match: python={py_url!r} lex={lex_url!r}"]
    return []


def compare_agent_readiness(
    py_score: int, py_signals: list[str], lex_result: dict,
) -> list[str]:
    """Diff Python's agent-readiness output vs lex's. Order matters."""
    diffs: list[str] = []
    if py_score != lex_result["score"]:
        diffs.append(f"score: python={py_score} lex={lex_result['score']}")
    if py_signals != lex_result["signals"]:
        diffs.append(f"signals: python={py_signals!r} lex={lex_result['signals']!r}")
    return diffs


def compare_composability(
    py_score: int, py_surfaces: list[str], lex_result: dict,
) -> list[str]:
    """Diff Python's composability output vs lex's.

    Compares both the score and the surface list. Order matters —
    both sides walk the same detector list in the same order, so a
    diff in order is real signal (likely a candidate-roots traversal
    bug).
    """
    diffs: list[str] = []
    if py_score != lex_result["score"]:
        diffs.append(f"score: python={py_score} lex={lex_result['score']}")
    if py_surfaces != lex_result["surfaces"]:
        diffs.append(f"surfaces: python={py_surfaces!r} lex={lex_result['surfaces']!r}")
    return diffs


def compare_ingest(url: str, lex_result: dict) -> list[str]:
    """Diff Python's URL parsers against lex's, on the same input.

    Both implementations are called directly (not through the meta
    fallback logic in `ingest()`, which adds a basename fallback for
    non-GitHub / non-gist URLs that the parsers themselves don't
    produce). Python's `parse_github_url` happens to match `gist.*`
    URLs because the regex isn't anchored against `gist.` — lex
    behaves the same way, so both parsers agree per-call even though
    `ingest()` orchestrates around it.

    The classify result in `lex_result` ("implementation" / "proposal")
    is NOT compared here — Python's classify reads doc-chars from the
    filesystem inside `ingest()`, and exposing that input through the
    cross-check would mean duplicating the probe. Lands in the next
    porting PR when classify gains its own [io] entry point.
    """
    # Imported lazily so this module stays importable when ingestion's
    # transitive deps aren't on the path (it isn't, in practice — but
    # keeps the cross-check's surface symmetric with the other helpers).
    from .ingestion import parse_github_url, parse_gist_url

    gh = parse_github_url(url)
    gi = parse_gist_url(url)
    py_gh_owner = gh[0] if gh else ""
    py_gh_repo  = gh[1] if gh else ""
    py_gist_owner = gi[0] if gi else ""
    py_gist_id    = gi[1] if gi else ""

    diffs: list[str] = []
    if py_gh_owner != lex_result["github_owner"]:
        diffs.append(
            f"github_owner: python={py_gh_owner!r} lex={lex_result['github_owner']!r}"
        )
    if py_gh_repo != lex_result["github_repo"]:
        diffs.append(
            f"github_repo: python={py_gh_repo!r} lex={lex_result['github_repo']!r}"
        )
    if py_gist_owner != lex_result["gist_owner"]:
        diffs.append(
            f"gist_owner: python={py_gist_owner!r} lex={lex_result['gist_owner']!r}"
        )
    if py_gist_id != lex_result["gist_id"]:
        diffs.append(f"gist_id: python={py_gist_id!r} lex={lex_result['gist_id']!r}")
    return diffs
