from __future__ import annotations

from typing import Any

import os
from mcp.server import MCPServer

from ars_mcp import __version__
from ars_mcp import core, pipeline

DEFAULT_ALLOWED_HOSTS = ("127.0.0.1:*", "localhost:*", "[::1]:*")
DEFAULT_ALLOWED_ORIGINS = ("http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*")
DEFAULT_MAX_MCP_REQUEST_BYTES = 12 * 1024 * 1024
MAX_MCP_REQUEST_BYTES = 64 * 1024 * 1024


def _csv_env(name: str, defaults: tuple[str, ...]) -> list[str]:
    raw = os.getenv(name)
    if raw is None:
        return list(defaults)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _transport_security_values() -> dict[str, object]:
    hosts = _csv_env("ARS_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS)
    origins = _csv_env("ARS_ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS)
    if not hosts:
        raise ValueError("ARS_ALLOWED_HOSTS must contain at least one allowed host")
    # An empty origin list intentionally denies browser-origin requests while
    # allowing non-browser clients that omit the Origin header.
    return {
        "enable_dns_rebinding_protection": True,
        "allowed_hosts": hosts,
        "allowed_origins": origins,
    }


def _transport_security():
    from mcp.server.transport_security import TransportSecuritySettings

    return TransportSecuritySettings(**_transport_security_values())


def _max_request_body_size() -> int:
    raw = os.getenv("ARS_MAX_MCP_REQUEST_BYTES", str(DEFAULT_MAX_MCP_REQUEST_BYTES))
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("ARS_MAX_MCP_REQUEST_BYTES must be an integer") from exc
    if not 1_048_576 <= value <= MAX_MCP_REQUEST_BYTES:
        raise ValueError(f"ARS_MAX_MCP_REQUEST_BYTES must be between 1048576 and {MAX_MCP_REQUEST_BYTES}")
    return value

mcp = MCPServer(
    "Academic Research Skills",
    instructions=(
        "Deterministic research utilities and a transactional project-workflow ledger for Academic Research Skills. "
        "Use Crossref for bibliographic metadata discovery, not as proof of quality. "
        "Screening tools prepare records but never decide inclusion/exclusion. "
        "Acronym and integrity checks report their actual coverage and limitations. "
        "The workflow ledger persists metadata, stage decisions, hashes, and event history in SQLite; it does not store manuscript bodies."
    ),
)


@mcp.tool()
def ars_backend_status() -> dict[str, Any]:
    """Report backend version and which deterministic upstream utility sources are available."""
    return core.backend_status()


@mcp.tool()
def ars_crossref_search(query: str, limit: int = 10) -> dict[str, Any]:
    """Search Crossref bibliographic metadata for scholarly works. Metadata discovery only."""
    return core.crossref_search(query, limit)


@mcp.tool()
def ars_crossref_lookup_doi(doi: str) -> dict[str, Any]:
    """Resolve a DOI against Crossref and return its registered bibliographic metadata."""
    return core.crossref_lookup_doi(doi)


@mcp.tool()
def ars_check_acronyms(manuscript_text: str, scopes: list[str] | None = None, allowlist: list[str] | None = None) -> dict[str, Any]:
    """Run the upstream deterministic acronym checker on manuscript text without modifying it."""
    return core.check_acronyms(manuscript_text, scopes, allowlist)


@mcp.tool()
def ars_anchorize_draft(manuscript_text: str) -> dict[str, Any]:
    """Add stable block markers to a draft and produce its deterministic block manifest."""
    return core.anchorize_draft(manuscript_text)


@mcp.tool()
def ars_prepare_screening_records(
    inputs: list[dict[str, str]],
    database_labels: dict[str, str] | None = None,
    start: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """Import RIS, PubMed NBIB, Web of Science TXT, CSV, or TSV exports; normalize and de-duplicate records. No screening decisions are made."""
    return core.prepare_screening_records(inputs, database_labels, start, limit)


@mcp.tool()
def ars_check_pipeline_integrity(files: list[dict[str, str]], strict: bool = False) -> dict[str, Any]:
    """Run the upstream advisory phase-integrity checker over a supplied project file list. Findings are not hard gates."""
    return core.check_pipeline_integrity(files, strict)


@mcp.tool()
def ars_pipeline_status() -> dict[str, Any]:
    """Describe the pipeline state machine, persistent storage, and security boundary."""
    return pipeline.pipeline_status()


@mcp.tool()
def ars_pipeline_create(
    title: str,
    workflow_type: str = "full",
    research_question: str = "",
    starting_stage: str | None = None,
) -> dict[str, Any]:
    """Create a durable research workflow. Returns a one-time project access token; store it securely."""
    return pipeline.create_project(title, workflow_type, research_question, starting_stage)


@mcp.tool()
def ars_pipeline_get(project_id: str, access_token: str) -> dict[str, Any]:
    """Read current pipeline state, registered artifact metadata, and recent decision history."""
    return pipeline.get_project(project_id, access_token)


@mcp.tool()
def ars_pipeline_add_artifact(
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
    """Register artifact metadata and a caller-supplied SHA-256 digest; format is checked but the digest is not recomputed because file bytes are not uploaded."""
    return pipeline.add_artifact(project_id, access_token, stage_id, name, artifact_type, sha256, byte_count, locator, provenance_note)


@mcp.tool()
def ars_pipeline_finish_stage(
    project_id: str,
    access_token: str,
    stage_id: str,
    outcome: str,
    summary: str,
    flagged_issues: list[str] | None = None,
) -> dict[str, Any]:
    """Record a stage result and place the project at a mandatory user-decision checkpoint."""
    return pipeline.finish_stage(project_id, access_token, stage_id, outcome, summary, flagged_issues)


@mcp.tool()
def ars_pipeline_decide(project_id: str, access_token: str, decision: str, rationale: str = "") -> dict[str, Any]:
    """Record the user's explicit checkpoint decision and advance only along a valid state transition."""
    return pipeline.decide(project_id, access_token, decision, rationale)


@mcp.tool()
def ars_pipeline_pause(project_id: str, access_token: str, reason: str = "") -> dict[str, Any]:
    """Pause an active project without discarding the current stage or pending decision."""
    return pipeline.pause_project(project_id, access_token, reason)


@mcp.tool()
def ars_pipeline_resume(project_id: str, access_token: str) -> dict[str, Any]:
    """Resume a paused project at the same stage and decision checkpoint."""
    return pipeline.resume_project(project_id, access_token)


@mcp.tool()
def ars_pipeline_delete(project_id: str, access_token: str, confirmation: str) -> dict[str, Any]:
    """Permanently delete a project, its artifact metadata, and its event history after exact confirmation."""
    return pipeline.delete_project(project_id, access_token, confirmation)


if __name__ == "__main__":
    transport = os.getenv("ARS_MCP_TRANSPORT", "stdio").strip().lower()
    if transport not in {"stdio", "streamable-http"}:
        raise SystemExit("ARS_MCP_TRANSPORT must be stdio or streamable-http")
    if transport == "stdio":
        mcp.run()
    else:
        host = os.getenv("ARS_HOST", "127.0.0.1")
        port = int(os.getenv("PORT", os.getenv("ARS_PORT", "8000")))
        mcp.run(
            transport="streamable-http",
            host=host,
            port=port,
            stateless_http=True,
            max_request_body_size=_max_request_body_size(),
            transport_security=_transport_security(),
        )
