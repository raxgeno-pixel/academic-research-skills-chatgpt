from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = PACKAGE_ROOT / "skills"
SCRIPTS_ROOT = SKILLS_ROOT / "scripts"
SCREENER_ROOT = SKILLS_ROOT / "sr-screener" / "scripts"

if str(SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILLS_ROOT))
if str(SCREENER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCREENER_ROOT))

MAX_TEXT_CHARS = 300_000
MAX_EXPORT_FILES = 10
MAX_EXPORT_FILE_BYTES = 2_000_000
MAX_EXPORT_TOTAL_BYTES = 8_000_000
MAX_PROJECT_FILES = 500
MAX_PROJECT_TOTAL_BYTES = 8_000_000


def backend_status() -> dict[str, Any]:
    """Describe available deterministic tools without implying remote deployment."""
    required = {
        "acronym_checker": SCRIPTS_ROOT / "check_acronyms.py",
        "draft_anchorizer": SCRIPTS_ROOT / "ars_anchorize_draft.py",
        "screening_importer": SCREENER_ROOT / "prepare_records.py",
        "pipeline_integrity_checker": SCRIPTS_ROOT / "check_pipeline_integrity.py",
    }
    available = {name: path.is_file() for name, path in required.items()}
    return {
        "backend": "academic-research-skills-mcp",
        "backend_version": "0.2.4",
        "upstream_source": "Academic Research Skills v3.24.0",
        "available_tools": available,
        "all_required_sources_present": all(available.values()),
        "storage_policy": "temporary work directories are removed after each call; pipeline metadata/state are persisted in SQLite",
        "workflow_state_store": "SQLite; configure ARS_STATE_DB and mount a durable protected volume",
        "external_services": ["Crossref REST API"],
        "not_implemented": [
            "OAuth 2.1 resource-server authentication",
            "automatic full-text retrieval",
            "independent model-agent dispatch",
            "Claude Code hooks and slash commands",
        ],
    }


def _safe_text(value: str, *, name: str, max_chars: int = MAX_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    if len(value) > max_chars:
        raise ValueError(f"{name} exceeds the {max_chars:,}-character limit")
    if "\x00" in value:
        raise ValueError(f"{name} contains a NUL character")
    return value


def _safe_relative_path(value: str) -> str:
    path = PurePosixPath(str(value).replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"unsafe relative path: {value!r}")
    if re.match(r"^[A-Za-z]:", str(value)):
        raise ValueError(f"drive-qualified paths are not allowed: {value!r}")
    return str(path)


def _crossref_date(item: dict[str, Any]) -> str | None:
    for key in ("published-print", "published-online", "published", "created", "issued"):
        date = item.get(key, {}).get("date-parts")
        if date and date[0]:
            parts = date[0]
            if len(parts) >= 3:
                return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
            if len(parts) == 2:
                return f"{int(parts[0]):04d}-{int(parts[1]):02d}"
            return f"{int(parts[0]):04d}"
    return None


def _crossref_item(item: dict[str, Any]) -> dict[str, Any]:
    authors = []
    for author in item.get("author", [])[:12]:
        if not isinstance(author, dict):
            continue
        name = " ".join(x for x in [author.get("given"), author.get("family")] if x)
        if name:
            authors.append(name)
    title = next(iter(item.get("title", []) or []), "")
    container = next(iter(item.get("container-title", []) or []), "")
    doi = item.get("DOI")
    return {
        "title": title,
        "authors": authors,
        "year_or_date": _crossref_date(item),
        "journal_or_container": container,
        "volume": item.get("volume"),
        "issue": item.get("issue"),
        "page": item.get("page"),
        "type": item.get("type"),
        "publisher": item.get("publisher"),
        "doi": doi,
        "doi_url": f"https://doi.org/{doi}" if doi else item.get("URL"),
        "cited_by_count": item.get("is-referenced-by-count"),
        "source": "Crossref REST API",
        "source_record_url": item.get("URL"),
        "quality_note": "Crossref registration is metadata evidence, not proof of peer review, research quality, or current retraction status.",
    }


def _crossref_request(url: str) -> dict[str, Any]:
    mailto = os.getenv("CROSSREF_MAILTO", "")
    separator = "&" if "?" in url else "?"
    if mailto:
        url = f"{url}{separator}mailto={urllib.parse.quote(mailto)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AcademicResearchSkillsMCP/0.2.4 (mailto: " + (mailto or "not-specified") + ")",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = response.read(4_000_001)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Crossref returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Crossref connection failed: {exc.reason}") from exc
    if len(data) > 4_000_000:
        raise RuntimeError("Crossref response exceeded the 4 MB safety limit")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Crossref returned invalid JSON") from exc
    if not isinstance(payload, dict) or "message" not in payload:
        raise RuntimeError("Crossref response has an unexpected shape")
    return payload


def crossref_search(query: str, limit: int = 10) -> dict[str, Any]:
    query = _safe_text(query.strip(), name="query", max_chars=300)
    if not query:
        raise ValueError("query cannot be empty")
    if not 1 <= int(limit) <= 20:
        raise ValueError("limit must be between 1 and 20")
    params = urllib.parse.urlencode({"query.bibliographic": query, "rows": int(limit)})
    payload = _crossref_request("https://api.crossref.org/works?" + params)
    message = payload.get("message", {})
    items = message.get("items", []) if isinstance(message, dict) else []
    return {
        "query": query,
        "returned": len(items),
        "total_results_reported": message.get("total-results"),
        "items": [_crossref_item(item) for item in items if isinstance(item, dict)],
        "source": "Crossref REST API",
        "limitations": [
            "Metadata discovery only; no automatic peer-review, methodological-quality, or retraction determination.",
            "Search ranking is supplied by Crossref and should not be treated as a systematic-search strategy by itself.",
        ],
    }


def crossref_lookup_doi(doi: str) -> dict[str, Any]:
    doi = _safe_text(doi.strip(), name="doi", max_chars=500)
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    doi = doi.removeprefix("doi:").strip()
    if not re.fullmatch(r"10\.\d{4,9}/[^\s<>\"{}|\\^`]+", doi, flags=re.IGNORECASE):
        raise ValueError("doi is not in a valid DOI form (expected 10.xxxx/...) ")
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    payload = _crossref_request(url)
    item = payload.get("message")
    if not isinstance(item, dict):
        raise RuntimeError("Crossref DOI response has an unexpected shape")
    return _crossref_item(item)


def check_acronyms(manuscript_text: str, scopes: list[str] | None = None, allowlist: list[str] | None = None) -> dict[str, Any]:
    text = _safe_text(manuscript_text, name="manuscript_text")
    from scripts import check_acronyms as checker

    valid_scopes = set(checker.SCOPES)
    chosen_scopes = tuple(scopes or checker.SCOPES)
    if not chosen_scopes or any(scope not in valid_scopes for scope in chosen_scopes):
        raise ValueError(f"scopes must be drawn from: {', '.join(checker.SCOPES)}")
    allow = frozenset(allowlist or [])
    if any(not isinstance(token, str) or len(token) > 20 for token in allow):
        raise ValueError("allowlist must contain acronym strings of at most 20 characters")
    report = checker.check(text.replace("\r\n", "\n"), chosen_scopes, checker.DEFAULT_ALLOWLIST | allow)
    raw = text.encode("utf-8")
    return {
        "checker": checker.CHECKER,
        "status": report["status"],
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "input_characters": len(text),
        "coverage": report["coverage"],
        "scope_lines": report["scope_lines"],
        "findings": report["findings"],
        "coverage_limits": report["coverage_limits"],
        "unread_sections": report["unread_sections"],
        "interpretation": "Deterministic acronym-definition check. A partial status means some input regions or patterns were outside the checker's coverage; manually review those limits.",
    }


def anchorize_draft(manuscript_text: str) -> dict[str, Any]:
    text = _safe_text(manuscript_text, name="manuscript_text")
    from scripts import ars_anchorize_draft as anchorizer
    from scripts import _block_parser

    anchored, newly_labeled = anchorizer._anchorize(text)
    parsed = _block_parser.parse_document(anchored)
    manifest = anchorizer.build_manifest(anchored.encode("utf-8"), parsed)
    repeat = anchorizer.anchorize_text(anchored)
    return {
        "anchored_draft": anchored,
        "manifest": manifest,
        "new_blocks": newly_labeled,
        "idempotent": repeat == anchored,
        "original_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "anchored_sha256": hashlib.sha256(anchored.encode("utf-8")).hexdigest(),
        "warning": "Block IDs and hashes are generated by the upstream deterministic parser. Review the anchored draft before using it as the baseline for revision patches.",
    }


def _normalize_export_name(filename: str) -> str:
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("each input requires a filename")
    name = Path(filename.replace("\\", "/")).name
    if name in ("", ".", "..") or name.startswith("."):
        raise ValueError(f"invalid export filename: {filename!r}")
    if Path(name).suffix.lower() not in {".ris", ".nbib", ".txt", ".csv", ".tsv"}:
        raise ValueError(f"unsupported export format for {filename!r}; use RIS, NBIB, TXT, CSV, or TSV")
    return name


def prepare_screening_records(
    inputs: list[dict[str, str]],
    database_labels: dict[str, str] | None = None,
    start: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    if not isinstance(inputs, list) or not inputs or len(inputs) > MAX_EXPORT_FILES:
        raise ValueError(f"inputs must contain between 1 and {MAX_EXPORT_FILES} export files")
    if start < 0 or not 1 <= limit <= 100:
        raise ValueError("start must be non-negative and limit must be between 1 and 100")
    normalized: list[tuple[str, str]] = []
    total_bytes = 0
    seen: set[str] = set()
    for item in inputs:
        if not isinstance(item, dict):
            raise ValueError("each input must be an object with filename and content")
        name = _normalize_export_name(item.get("filename", ""))
        if name.lower() in seen:
            raise ValueError(f"duplicate input filename: {name}")
        seen.add(name.lower())
        content = _safe_text(item.get("content", ""), name=f"content for {name}", max_chars=MAX_EXPORT_FILE_BYTES)
        size = len(content.encode("utf-8"))
        if not size:
            raise ValueError(f"input file {name} is empty")
        if size > MAX_EXPORT_FILE_BYTES:
            raise ValueError(f"input file {name} exceeds the 2 MB limit")
        total_bytes += size
        normalized.append((name, content))
    if total_bytes > MAX_EXPORT_TOTAL_BYTES:
        raise ValueError("combined export content exceeds the 8 MB limit")

    db_labels = database_labels or {}
    allowed_keys = {name for name, _ in normalized}
    if any(key not in allowed_keys for key in db_labels):
        raise ValueError("database_labels keys must exactly match supplied filenames")

    script = SCREENER_ROOT / "prepare_records.py"
    if not script.is_file():
        raise RuntimeError("upstream screening preparation script is missing from this package")
    with tempfile.TemporaryDirectory(prefix="ars-screen-") as tmp:
        root = Path(tmp)
        source_dir = root / "inputs"
        work_dir = root / "work"
        source_dir.mkdir()
        work_dir.mkdir()
        paths = []
        for name, content in normalized:
            path = source_dir / name
            path.write_text(content, encoding="utf-8", newline="\n")
            paths.append(str(path))
        cmd = [sys.executable, str(script), "--inputs", *paths, "--work", str(work_dir)]
        for name, database in db_labels.items():
            db = str(database).strip()
            if not db or len(db) > 100:
                raise ValueError(f"database label for {name} must be 1–100 characters")
            cmd.extend(["--db", f"{name}={db}"])
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(PACKAGE_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=90,
                check=False,
                env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("screening import timed out after 90 seconds; reduce the export size") from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout)[-4000:]
            raise RuntimeError(f"screening import failed (exit {proc.returncode}): {detail}")
        records_payload = json.loads((work_dir / "records.json").read_text(encoding="utf-8"))
        identification = json.loads((work_dir / "identification.json").read_text(encoding="utf-8"))
        manifest = json.loads((work_dir / "manifest.json").read_text(encoding="utf-8"))
        records = records_payload.get("unique", [])
        preview = []
        for row in records[start : start + limit]:
            preview.append({
                "id": row.get("id"),
                "title": row.get("title"),
                "authors": row.get("authors", [])[:8],
                "year": row.get("year"),
                "journal": row.get("journal"),
                "doi": row.get("doi"),
                "pmid": row.get("pmid"),
                "sources": row.get("sources", []),
                "abstract": (row.get("abstract") or "")[:2000],
                "batch": row.get("batch"),
            })
        duplicates = []
        dup_path = work_dir / "duplicates.csv"
        with dup_path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if len(duplicates) < 200:
                    duplicates.append(row)
        return {
            "status": "prepared",
            "tool": identification.get("tool"),
            "review_id": records_payload.get("review_id"),
            "identification": identification,
            "manifest": [{"batch": x.get("batch"), "ids": x.get("ids", [])} for x in manifest],
            "records": preview,
            "records_total": len(records),
            "records_returned": len(preview),
            "records_omitted_from_response": max(0, len(records) - len(preview)),
            "duplicates_preview": duplicates,
            "duplicates_omitted_from_response": max(0, identification.get("duplicates_removed", 0) - len(duplicates)),
            "decision_boundary": "This tool imports, normalizes, and de-duplicates records only. It does not make inclusion/exclusion decisions; title/abstract screening requires a confirmed protocol and human-reviewed criteria.",
            "process_log": proc.stdout[-4000:],
        }


def check_pipeline_integrity(files: list[dict[str, str]], strict: bool = False) -> dict[str, Any]:
    if not isinstance(files, list) or len(files) > MAX_PROJECT_FILES:
        raise ValueError(f"files must be a list with no more than {MAX_PROJECT_FILES} entries")
    total = 0
    cleaned: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("each file must be an object with path and content")
        rel = _safe_relative_path(item.get("path", ""))
        if rel in seen:
            raise ValueError(f"duplicate file path: {rel}")
        seen.add(rel)
        content = _safe_text(item.get("content", ""), name=f"content for {rel}", max_chars=MAX_PROJECT_TOTAL_BYTES)
        total += len(content.encode("utf-8"))
        cleaned.append((rel, content))
    if total > MAX_PROJECT_TOTAL_BYTES:
        raise ValueError("combined project content exceeds the 8 MB limit")
    script = SCRIPTS_ROOT / "check_pipeline_integrity.py"
    if not script.is_file():
        raise RuntimeError("upstream pipeline integrity checker is missing from this package")
    with tempfile.TemporaryDirectory(prefix="ars-integrity-") as tmp:
        root = Path(tmp)
        for rel, content in cleaned:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        cmd = [sys.executable, str(script), "--json", str(root)]
        if strict:
            cmd.insert(2, "--strict")
        proc = subprocess.run(
            cmd, cwd=str(PACKAGE_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30, check=False,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if proc.returncode != 0:
            raise RuntimeError(f"pipeline integrity checker failed (exit {proc.returncode}): {(proc.stderr or proc.stdout)[-3000:]}")
        try:
            report = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("pipeline integrity checker returned invalid JSON") from exc
        report["tool_return_code"] = proc.returncode
        report["strict_heuristic_enabled"] = bool(strict)
        report["interpretation"] = "Advisory only. It does not prove independent agents ran; it inspects phase-directory structure and optional timestamp heuristics. Review findings manually."
        return report
