from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PIPELINE_VERSION = "0.2.4"
MAX_SUMMARY_CHARS = 8_000
MAX_NOTES_CHARS = 2_000
MAX_ARTIFACTS_PER_PROJECT = 500
MAX_ARTIFACT_BYTES = 100_000_000

STAGES: dict[str, dict[str, str]] = {
    "research": {"label": "Research", "description": "Research question, protocol, search, evidence synthesis"},
    "write": {"label": "Write", "description": "Plan, structure, and draft the manuscript"},
    "pre_review_integrity": {"label": "Pre-review integrity", "description": "Verify source, claim, citation, and manuscript integrity"},
    "peer_review": {"label": "Peer review", "description": "Evaluate the manuscript and produce an editorial recommendation"},
    "revise": {"label": "Revise", "description": "Revise the manuscript and prepare responses to reviewers"},
    "re_review": {"label": "Re-review", "description": "Verify whether reviewer concerns have been addressed"},
    "re_revise": {"label": "Re-revise", "description": "Perform a further revision or correct final-integrity findings"},
    "final_integrity": {"label": "Final integrity", "description": "Run final integrity checks before finalization"},
    "finalize": {"label": "Finalize", "description": "Prepare and verify final deliverables"},
    "process_summary": {"label": "Process summary", "description": "Create the auditable research-process record"},
}

START_MODES = {
    "full": "research",
    "existing_paper": "pre_review_integrity",
    "revision_only": "revise",
    "systematic_review": "research",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_string(value: Any, field: str, maximum: int, *, required: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{field} cannot be empty")
    if len(value) > maximum:
        raise ValueError(f"{field} exceeds {maximum} characters")
    if "\x00" in value:
        raise ValueError(f"{field} contains a NUL character")
    return value


def _db_path() -> Path:
    override = os.getenv("ARS_STATE_DB", "").strip()
    if override:
        path = Path(override).expanduser()
    else:
        path = Path.home() / ".local" / "share" / "ars-mcp" / "ars_state.sqlite3"
    parent_existed = path.parent.exists()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Only tighten permissions on a directory this function created. Never
    # chmod a caller-supplied shared directory.
    if os.name != "nt" and not parent_existed:
        try:
            path.parent.chmod(0o700)
        except OSError:
            pass
    return path


def _connect() -> sqlite3.Connection:
    db_path = _db_path()
    conn = sqlite3.connect(db_path, timeout=15, isolation_level=None)
    # The database contains private research-project metadata and capability
    # token digests. Keep the main DB private on POSIX systems.
    if os.name != "nt":
        try:
            db_path.chmod(0o600)
        except OSError:
            conn.close()
            raise
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def _database():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            token_hash TEXT NOT NULL,
            title TEXT NOT NULL,
            workflow_type TEXT NOT NULL,
            current_stage TEXT NOT NULL,
            status TEXT NOT NULL,
            state_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            stage_id TEXT,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id, event_id);
        CREATE TABLE IF NOT EXISTS artifacts (
            artifact_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            stage_id TEXT NOT NULL,
            name TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            byte_count INTEGER NOT NULL,
            locator TEXT,
            provenance_note TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(project_id, created_at);
        """
    )


def _append_event(conn: sqlite3.Connection, project_id: str, event_type: str, stage_id: str | None, payload: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO events(project_id,event_type,stage_id,payload_json,created_at) VALUES(?,?,?,?,?)",
        (project_id, event_type, stage_id, json.dumps(payload, ensure_ascii=False), _now()),
    )


def _load_owned(conn: sqlite3.Connection, project_id: str, access_token: str) -> sqlite3.Row:
    project_id = _safe_string(project_id, "project_id", 64)
    access_token = _safe_string(access_token, "access_token", 256)
    if len(access_token) < 32:
        raise ValueError("access_token is invalid")
    row = conn.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
    candidate = hashlib.sha256(access_token.encode("utf-8")).hexdigest()
    if row is None or not secrets.compare_digest(row["token_hash"], candidate):
        raise PermissionError("project not found or access token invalid")
    return row


def _save_state(conn: sqlite3.Connection, row: sqlite3.Row, state: dict[str, Any]) -> None:
    conn.execute(
        "UPDATE projects SET current_stage=?,status=?,state_json=?,updated_at=?,version=version+1 WHERE project_id=?",
        (state["current_stage"], state["status"], json.dumps(state, ensure_ascii=False), _now(), row["project_id"]),
    )


def _read_project(conn: sqlite3.Connection, row: sqlite3.Row, *, include_history: bool = True) -> dict[str, Any]:
    state = json.loads(row["state_json"])
    artifact_rows = conn.execute(
        "SELECT artifact_id,stage_id,name,artifact_type,sha256,byte_count,locator,provenance_note,created_at FROM artifacts WHERE project_id=? ORDER BY created_at, artifact_id",
        (row["project_id"],),
    ).fetchall()
    result = {
        "project_id": row["project_id"],
        "title": row["title"],
        "workflow_type": row["workflow_type"],
        "current_stage": row["current_stage"],
        "status": row["status"],
        "state": state,
        "artifacts": [dict(a) for a in artifact_rows],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "version": row["version"],
    }
    if include_history:
        events = conn.execute(
            "SELECT event_id,event_type,stage_id,payload_json,created_at FROM events WHERE project_id=? ORDER BY event_id DESC LIMIT 50",
            (row["project_id"],),
        ).fetchall()
        result["history"] = [
            {"event_id": e["event_id"], "event_type": e["event_type"], "stage_id": e["stage_id"], "payload": json.loads(e["payload_json"]), "created_at": e["created_at"]}
            for e in reversed(events)
        ]
    return result


def create_project(title: str, workflow_type: str = "full", research_question: str = "", starting_stage: str | None = None) -> dict[str, Any]:
    title = _safe_string(title, "title", 200)
    if workflow_type not in START_MODES:
        raise ValueError(f"workflow_type must be one of: {', '.join(START_MODES)}")
    research_question = _safe_string(research_question, "research_question", 2_000, required=False)
    stage = starting_stage or START_MODES[workflow_type]
    if stage not in STAGES:
        raise ValueError(f"starting_stage must be one of: {', '.join(STAGES)}")
    project_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)
    now = _now()
    states = {key: {"status": "pending", "attempts": 0, "outcome": None} for key in STAGES}
    states[stage]["status"] = "in_progress"
    states[stage]["attempts"] = 1
    state = {
        "schema_version": 1,
        "pipeline_version": PIPELINE_VERSION,
        "status": "active",
        "current_stage": stage,
        "current_stage_status": "in_progress",
        "research_question": research_question,
        "stage_states": states,
        "integrity_failure_rounds": {"pre_review": 0, "final": 0},
        "decision_required": False,
        "last_decision": None,
        "closed_reason": None,
        "privacy": {
            "document_contents_persisted": False,
            "stored_data": "project metadata, research question, bounded stage summaries, issue labels, stage states, artifact hashes/metadata, and event ledger; no uploaded document bodies",
        },
    }
    with _database() as conn:
        _init_db(conn)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO projects(project_id,token_hash,title,workflow_type,current_stage,status,state_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (project_id, hashlib.sha256(token.encode("utf-8")).hexdigest(), title, workflow_type, stage, "active", json.dumps(state, ensure_ascii=False), now, now),
        )
        _append_event(conn, project_id, "project_created", stage, {"title": title, "workflow_type": workflow_type, "starting_stage": stage})
        row = conn.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        result = _read_project(conn, row, include_history=True)
    return {"project": result, "access_token": token, "token_warning": "Save this access token securely. It is shown only at project creation and cannot be recovered. Do not publish it."}


def get_project(project_id: str, access_token: str) -> dict[str, Any]:
    with _database() as conn:
        _init_db(conn)
        row = _load_owned(conn, project_id, access_token)
        return _read_project(conn, row)


def add_artifact(
    project_id: str,
    access_token: str,
    stage_id: str,
    name: str,
    artifact_type: str,
    sha256: str,
    byte_count: int,
    locator: str = "",
    provenance_note: str = "",
) -> dict[str, Any]:
    if stage_id not in STAGES:
        raise ValueError("stage_id is not a recognized pipeline stage")
    name = _safe_string(name, "name", 200)
    if name in {".", ".."} or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError("artifact name must be a plain filename, not a path")
    if artifact_type not in {"manuscript", "protocol", "dataset", "bibliography", "review", "report", "response_letter", "figure", "other"}:
        raise ValueError("artifact_type is not supported")
    if not isinstance(sha256, str) or len(sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in sha256):
        raise ValueError("sha256 must be a 64-character hexadecimal digest")
    if not isinstance(byte_count, int) or not 0 <= byte_count <= MAX_ARTIFACT_BYTES:
        raise ValueError(f"byte_count must be between 0 and {MAX_ARTIFACT_BYTES}")
    locator = _safe_string(locator, "locator", 500, required=False)
    provenance_note = _safe_string(provenance_note, "provenance_note", MAX_NOTES_CHARS, required=False)
    artifact_id = str(uuid.uuid4())
    now = _now()
    with _database() as conn:
        _init_db(conn)
        conn.execute("BEGIN IMMEDIATE")
        row = _load_owned(conn, project_id, access_token)
        state = json.loads(row["state_json"])
        if state["status"] != "active" or state["current_stage"] != stage_id or state["current_stage_status"] != "in_progress":
            raise ValueError("artifacts can only be registered for the active, in-progress stage")
        count = conn.execute("SELECT COUNT(*) FROM artifacts WHERE project_id=?", (project_id,)).fetchone()[0]
        if count >= MAX_ARTIFACTS_PER_PROJECT:
            raise ValueError(f"project artifact limit ({MAX_ARTIFACTS_PER_PROJECT}) reached")
        conn.execute(
            "INSERT INTO artifacts(artifact_id,project_id,stage_id,name,artifact_type,sha256,byte_count,locator,provenance_note,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (artifact_id, project_id, stage_id, name, artifact_type, sha256.lower(), byte_count, locator, provenance_note, now),
        )
        _append_event(conn, project_id, "artifact_registered", stage_id, {"artifact_id": artifact_id, "name": name, "artifact_type": artifact_type, "sha256": sha256.lower(), "byte_count": byte_count})
        result = {"artifact_id": artifact_id, "stage_id": stage_id, "name": name, "artifact_type": artifact_type, "sha256": sha256.lower(), "hash_validation": "format_only; digest was not recomputed against file bytes", "byte_count": byte_count, "created_at": now}
    return result


def finish_stage(project_id: str, access_token: str, stage_id: str, outcome: str, summary: str, flagged_issues: list[str] | None = None) -> dict[str, Any]:
    if stage_id not in STAGES:
        raise ValueError("stage_id is not a recognized pipeline stage")
    summary = _safe_string(summary, "summary", MAX_SUMMARY_CHARS)
    flags = flagged_issues or []
    if not isinstance(flags, list) or len(flags) > 50:
        raise ValueError("flagged_issues must be a list containing at most 50 items")
    flags = [_safe_string(x, "flagged issue", 500) for x in flags]
    allowed = {
        "research": {"complete"}, "write": {"complete"},
        "pre_review_integrity": {"pass", "fail"},
        "peer_review": {"accept", "minor_revision", "major_revision", "reject"},
        "revise": {"complete"}, "re_review": {"accept", "minor_revision", "major_revision"},
        "re_revise": {"complete"}, "final_integrity": {"pass", "fail"},
        "finalize": {"complete"}, "process_summary": {"complete"},
    }
    if outcome not in allowed[stage_id]:
        raise ValueError(f"outcome for {stage_id} must be one of: {', '.join(sorted(allowed[stage_id]))}")
    with _database() as conn:
        _init_db(conn)
        conn.execute("BEGIN IMMEDIATE")
        row = _load_owned(conn, project_id, access_token)
        state = json.loads(row["state_json"])
        if state["status"] != "active" or state["current_stage"] != stage_id or state["current_stage_status"] != "in_progress":
            raise ValueError("only the active, in-progress stage can be completed")
        stage_state = state["stage_states"][stage_id]
        stage_state.update({"status": "awaiting_decision", "outcome": outcome, "summary": summary, "flagged_issues": flags, "finished_at": _now()})
        if stage_id == "pre_review_integrity" and outcome == "fail":
            state["integrity_failure_rounds"]["pre_review"] += 1
        if stage_id == "final_integrity" and outcome == "fail":
            state["integrity_failure_rounds"]["final"] += 1
        state["current_stage_status"] = "awaiting_decision"
        state["decision_required"] = True
        _save_state(conn, row, state)
        _append_event(conn, project_id, "stage_finished", stage_id, {"outcome": outcome, "flagged_issues": flags, "summary": summary})
        updated = conn.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        return _read_project(conn, updated)


def _activate_stage(state: dict[str, Any], stage_id: str) -> None:
    state["current_stage"] = stage_id
    state["current_stage_status"] = "in_progress"
    stage_state = state["stage_states"][stage_id]
    stage_state["status"] = "in_progress"
    stage_state["outcome"] = None
    for stale_key in ("summary", "flagged_issues", "finished_at", "risk_accepted"):
        stage_state.pop(stale_key, None)
    stage_state["attempts"] += 1
    state["decision_required"] = False


def decide(project_id: str, access_token: str, decision: str, rationale: str = "") -> dict[str, Any]:
    decision = _safe_string(decision, "decision", 40)
    rationale = _safe_string(rationale, "rationale", MAX_NOTES_CHARS, required=False)
    with _database() as conn:
        _init_db(conn)
        conn.execute("BEGIN IMMEDIATE")
        row = _load_owned(conn, project_id, access_token)
        state = json.loads(row["state_json"])
        if state["status"] != "active" or not state["decision_required"] or state["current_stage_status"] != "awaiting_decision":
            raise ValueError("there is no pending stage decision")
        stage = state["current_stage"]
        outcome = state["stage_states"][stage]["outcome"]
        next_stage: str | None = None
        close_status: str | None = None

        if decision == "pause":
            state["status"] = "paused"
        elif stage in {"research", "write", "revise", "re_revise"} and decision == "continue":
            next_stage = {"research": "write", "write": "pre_review_integrity", "revise": "re_review", "re_revise": "final_integrity"}[stage]
        elif stage in {"pre_review_integrity", "final_integrity"}:
            is_pre = stage == "pre_review_integrity"
            rounds = state["integrity_failure_rounds"]["pre_review" if is_pre else "final"]
            passed = outcome == "pass"
            if passed and decision == "continue":
                next_stage = "peer_review" if is_pre else "finalize"
            elif not passed and decision == "revise":
                next_stage = "write" if is_pre else "re_revise"
            elif not passed and rounds >= 3 and decision == "bypass_with_risk":
                next_stage = "peer_review" if is_pre else "finalize"
                state["stage_states"][stage]["risk_accepted"] = True
            else:
                raise ValueError("integrity decision is invalid for the recorded outcome; FAIL requires revise, or bypass_with_risk after 3 failed rounds; PASS requires continue")
        elif stage == "peer_review":
            if outcome == "accept" and decision == "accept":
                next_stage = "final_integrity"
            elif outcome in {"minor_revision", "major_revision"} and decision == "revise":
                next_stage = "revise"
            elif outcome == "reject" and decision == "restart_writing":
                next_stage = "write"
            elif outcome == "reject" and decision == "end":
                close_status = "closed"
                state["closed_reason"] = "editorial_rejection_user_ended_pipeline"
            else:
                raise ValueError("peer-review decision must correspond to the recorded editorial outcome")
        elif stage == "re_review":
            if outcome in {"accept", "minor_revision"} and decision == "accept":
                next_stage = "final_integrity"
            elif outcome == "major_revision" and decision == "revise":
                next_stage = "re_revise"
            else:
                raise ValueError("re-review decision must be accept for ACCEPT/MINOR, or revise for MAJOR")
        elif stage == "finalize":
            if decision == "continue":
                next_stage = "process_summary"
            elif decision == "skip_summary":
                close_status = "completed"
                state["closed_reason"] = "process_summary_skipped_by_user"
            else:
                raise ValueError("finalize decision must be continue or skip_summary")
        elif stage == "process_summary" and decision == "finish" and outcome == "complete":
            close_status = "completed"
            state["closed_reason"] = "process_summary_completed"
        else:
            raise ValueError("decision is not valid for the current stage")

        state["last_decision"] = {"stage_id": stage, "decision": decision, "rationale": rationale, "created_at": _now()}
        if next_stage:
            if stage in {"pre_review_integrity", "final_integrity"} and outcome == "fail":
                state["stage_states"][stage]["status"] = "waived_with_risk" if decision == "bypass_with_risk" else "resolved_after_failure"
            else:
                state["stage_states"][stage]["status"] = "completed"
            _activate_stage(state, next_stage)
        elif close_status:
            state["stage_states"][stage]["status"] = "completed" if close_status == "completed" else "closed"
            state["status"] = close_status
            state["current_stage_status"] = "completed" if close_status == "completed" else "closed"
            state["decision_required"] = False
        _save_state(conn, row, state)
        _append_event(conn, project_id, "decision_recorded", stage, {"decision": decision, "rationale": rationale, "next_stage": next_stage, "project_status": state["status"]})
        updated = conn.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        return _read_project(conn, updated)


def pause_project(project_id: str, access_token: str, reason: str = "") -> dict[str, Any]:
    reason = _safe_string(reason, "reason", MAX_NOTES_CHARS, required=False)
    with _database() as conn:
        _init_db(conn)
        conn.execute("BEGIN IMMEDIATE")
        row = _load_owned(conn, project_id, access_token)
        state = json.loads(row["state_json"])
        if state["status"] != "active":
            raise ValueError("only an active project can be paused")
        state["status"] = "paused"
        state["pause_reason"] = reason
        _save_state(conn, row, state)
        _append_event(conn, project_id, "project_paused", state["current_stage"], {"reason": reason})
        updated = conn.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        return _read_project(conn, updated)


def resume_project(project_id: str, access_token: str) -> dict[str, Any]:
    with _database() as conn:
        _init_db(conn)
        conn.execute("BEGIN IMMEDIATE")
        row = _load_owned(conn, project_id, access_token)
        state = json.loads(row["state_json"])
        if state["status"] != "paused":
            raise ValueError("only a paused project can be resumed")
        state["status"] = "active"
        state.pop("pause_reason", None)
        _save_state(conn, row, state)
        _append_event(conn, project_id, "project_resumed", state["current_stage"], {"decision_required": state["decision_required"], "current_stage_status": state["current_stage_status"]})
        updated = conn.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        return _read_project(conn, updated)


def pipeline_status() -> dict[str, Any]:
    return {
        "pipeline_version": PIPELINE_VERSION,
        "storage": "SQLite transactional state and immutable event ledger",
        "database_path_configured": bool(os.getenv("ARS_STATE_DB")),
        "stages": [{"id": key, **value} for key, value in STAGES.items()],
        "start_modes": START_MODES,
        "stage_contracts": {
            "research": {"outcomes": ["complete"], "decisions": {"complete": ["continue"]}},
            "write": {"outcomes": ["complete"], "decisions": {"complete": ["continue"]}},
            "pre_review_integrity": {"outcomes": ["pass", "fail"], "decisions": {"pass": ["continue"], "fail": ["revise"], "fail_after_three_rounds": ["revise", "bypass_with_risk"]}},
            "peer_review": {"outcomes": ["accept", "minor_revision", "major_revision", "reject"], "decisions": {"accept": ["accept"], "minor_revision": ["revise"], "major_revision": ["revise"], "reject": ["restart_writing", "end"]}},
            "revise": {"outcomes": ["complete"], "decisions": {"complete": ["continue"]}},
            "re_review": {"outcomes": ["accept", "minor_revision", "major_revision"], "decisions": {"accept": ["accept"], "minor_revision": ["accept"], "major_revision": ["revise"]}},
            "re_revise": {"outcomes": ["complete"], "decisions": {"complete": ["continue"]}},
            "final_integrity": {"outcomes": ["pass", "fail"], "decisions": {"pass": ["continue"], "fail": ["revise"], "fail_after_three_rounds": ["revise", "bypass_with_risk"]}},
            "finalize": {"outcomes": ["complete"], "decisions": {"complete": ["continue", "skip_summary"]}},
            "process_summary": {"outcomes": ["complete"], "decisions": {"complete": ["finish"]}},
        },
        "privacy": "No manuscript or full-text file upload/storage is implemented. The caller-supplied research question, bounded stage summaries, issue labels, hashes, artifact metadata, and event history are stored; do not put full document text or secrets in summaries.",
        "security_boundary": "Project access uses a high-entropy capability token. This is not a substitute for OAuth 2.1 or a per-user authenticated deployment. Use a private single-tenant deployment until an authenticated resource-server layer is configured.",
        "integrity_fail_policy": "A failed integrity stage cannot advance normally. After three recorded failed rounds, the user may explicitly bypass with risk acceptance; the risk is written to the stage ledger.",
    }


def delete_project(project_id: str, access_token: str, confirmation: str) -> dict[str, Any]:
    project_id = _safe_string(project_id, "project_id", 64)
    confirmation = _safe_string(confirmation, "confirmation", 80)
    if confirmation != f"DELETE {project_id}":
        raise ValueError("confirmation must exactly equal 'DELETE <project_id>'")
    with _database() as conn:
        _init_db(conn)
        conn.execute("BEGIN IMMEDIATE")
        row = _load_owned(conn, project_id, access_token)
        conn.execute("DELETE FROM projects WHERE project_id=?", (project_id,))
        return {
            "deleted": True,
            "project_id": project_id,
            "title": row["title"],
            "deleted_at": _now(),
            "retained_project_data": False,
        }
