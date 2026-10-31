"""Official MCP SDK in-process integration tests.

These use the real ``mcp.Client`` and ``MCPServer`` dispatcher, not the
registry shim used by test_tool_handlers_smoke.py. They exercise MCP initialize,
list_tools and tools/call semantics without opening a network port.
"""
from __future__ import annotations

import hashlib
import importlib
import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(PACKAGE_ROOT / "skills"))

EXPECTED_TOOLS = {
    "ars_backend_status", "ars_crossref_search", "ars_crossref_lookup_doi",
    "ars_check_acronyms", "ars_anchorize_draft", "ars_prepare_screening_records",
    "ars_check_pipeline_integrity", "ars_pipeline_status", "ars_pipeline_create",
    "ars_pipeline_get", "ars_pipeline_add_artifact", "ars_pipeline_finish_stage",
    "ars_pipeline_decide", "ars_pipeline_pause", "ars_pipeline_resume",
    "ars_pipeline_delete",
}


def _payload(result):
    assert not result.is_error, [getattr(item, "text", repr(item)) for item in result.content]
    payload = result.structured_content
    if payload is None:
        raise AssertionError("MCP tool did not return structured content")
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    while isinstance(payload, dict) and set(payload) == {"result"}:
        payload = payload["result"]
    return payload


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mcp_server(monkeypatch, tmp_path):
    try:
        from mcp import Client as _OfficialClient  # noqa: F401
    except ImportError:
        pytest.skip("official MCP SDK is not installed in this test environment")
    monkeypatch.setenv("ARS_STATE_DB", str(tmp_path / "mcp-sdk-test.sqlite3"))
    import ars_mcp.server as server_module
    server_module = importlib.reload(server_module)
    core_module = importlib.import_module("ars_mcp.core")
    return server_module.mcp, core_module


@pytest.mark.anyio
async def test_real_sdk_client_initializes_and_lists_all_tools(mcp_server):
    try:
        from mcp import Client
    except ImportError:
        pytest.skip("official MCP SDK is not installed in this test environment")

    server, _ = mcp_server
    async with Client(server, raise_exceptions=True) as client:
        assert client.server_info is not None
        assert client.protocol_version
        listed = await client.list_tools()
        names = {tool.name for tool in listed.tools}
        assert names == EXPECTED_TOOLS
        assert all(tool.input_schema.get("type") == "object" for tool in listed.tools)


@pytest.mark.anyio
async def test_real_sdk_client_calls_all_sixteen_tools(mcp_server, monkeypatch):
    try:
        from mcp import Client
    except ImportError:
        pytest.skip("official MCP SDK is not installed in this test environment")

    server, core = mcp_server
    item = {
        "DOI": "10.5555/ars.sdk-smoke",
        "title": ["MCP SDK integration fixture"],
        "author": [{"given": "Ada", "family": "Lovelace"}],
        "published": {"date-parts": [[2024, 1, 1]]},
        "container-title": ["Journal of Protocol Tests"],
        "URL": "https://api.crossref.org/works/10.5555/ars.sdk-smoke",
    }

    def fake_crossref(url):
        if "10.5555%2Fars.sdk-smoke" in url or url.endswith("10.5555/ars.sdk-smoke"):
            return {"message": item}
        return {"message": {"total-results": 1, "items": [item]}}

    monkeypatch.setattr(core, "_crossref_request", fake_crossref)
    async with Client(server, raise_exceptions=True) as client:
        status = _payload(await client.call_tool("ars_backend_status", {}))
        assert status["all_required_sources_present"] is True

        search = _payload(await client.call_tool("ars_crossref_search", {"query": "MCP integration", "limit": 1}))
        assert search["returned"] == 1

        doi = _payload(await client.call_tool("ars_crossref_lookup_doi", {"doi": "10.5555/ars.sdk-smoke"}))
        assert doi["doi"] == "10.5555/ars.sdk-smoke"

        acronym = _payload(await client.call_tool("ars_check_acronyms", {
            "manuscript_text": "# Example\n\n## Abstract\nRandomized controlled trial (RCT) methods were used.\n"
        }))
        assert acronym["status"] in {"checked", "partial"}

        anchored = _payload(await client.call_tool("ars_anchorize_draft", {
            "manuscript_text": "# Example\n\nA short test paragraph.\n"
        }))
        assert anchored["idempotent"] is True

        ris = (
            "TY  - JOUR\nTI  - SDK screening fixture\nAU  - Doe, Jane\n"
            "PY  - 2022\nDO  - 10.5555/ars.sdk-screen\nER  -\n"
        )
        screen = _payload(await client.call_tool("ars_prepare_screening_records", {
            "inputs": [{"filename": "sdk.ris", "content": ris}],
            "database_labels": {"sdk.ris": "SDK Fixture"}, "start": 0, "limit": 10,
        }))
        assert screen["records_total"] == 1

        integrity = _payload(await client.call_tool("ars_check_pipeline_integrity", {
            "files": [{"path": "phase5_review/review.md", "content": "Review fixture."}],
            "strict": False,
        }))
        assert "findings" in integrity

        pipeline_status = _payload(await client.call_tool("ars_pipeline_status", {}))
        assert len(pipeline_status["stages"]) == 10

        created = _payload(await client.call_tool("ars_pipeline_create", {
            "title": "MCP SDK integration project",
            "workflow_type": "full",
            "research_question": "Does the MCP SDK client call all registered tools?",
        }))
        project_id = created["project"]["project_id"]
        token = created["access_token"]

        fetched = _payload(await client.call_tool("ars_pipeline_get", {
            "project_id": project_id, "access_token": token,
        }))
        assert fetched["current_stage"] == "research"

        artifact = _payload(await client.call_tool("ars_pipeline_add_artifact", {
            "project_id": project_id, "access_token": token, "stage_id": "research",
            "name": "protocol.md", "artifact_type": "protocol",
            "sha256": hashlib.sha256(b"protocol").hexdigest(), "byte_count": 8,
            "locator": "test://protocol", "provenance_note": "SDK test fixture",
        }))
        assert artifact["sha256"] == hashlib.sha256(b"protocol").hexdigest()

        finished = _payload(await client.call_tool("ars_pipeline_finish_stage", {
            "project_id": project_id, "access_token": token, "stage_id": "research",
            "outcome": "complete", "summary": "SDK protocol integration test completed",
            "flagged_issues": [],
        }))
        assert finished["state"]["decision_required"] is True

        continued = _payload(await client.call_tool("ars_pipeline_decide", {
            "project_id": project_id, "access_token": token, "decision": "continue",
            "rationale": "SDK integration fixture",
        }))
        assert continued["current_stage"] == "write"

        paused = _payload(await client.call_tool("ars_pipeline_pause", {
            "project_id": project_id, "access_token": token, "reason": "SDK test pause",
        }))
        assert paused["status"] == "paused"

        resumed = _payload(await client.call_tool("ars_pipeline_resume", {
            "project_id": project_id, "access_token": token,
        }))
        assert resumed["status"] == "active"

        deleted = _payload(await client.call_tool("ars_pipeline_delete", {
            "project_id": project_id, "access_token": token,
            "confirmation": f"DELETE {project_id}",
        }))
        assert deleted["deleted"] is True
