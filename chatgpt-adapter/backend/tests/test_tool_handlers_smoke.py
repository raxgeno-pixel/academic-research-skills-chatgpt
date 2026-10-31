"""Handler-level smoke tests with a registry shim; not an MCP wire-protocol test."""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(PLUGIN_ROOT / "skills"))


class _RegistryServer:
    def __init__(self, name: str, instructions: str = "") -> None:
        self.name = name
        self.instructions = instructions
        self.tools = {}

    def tool(self):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register

    def run(self, *args, **kwargs):  # pragma: no cover - not used by handler tests
        raise RuntimeError("Registry shim does not implement MCP transport")


# Inject a deliberately small SDK-shaped shim only when the official SDK is
# absent. When the SDK is installed, the real Client integration suite is used.
SDK_AVAILABLE = importlib.util.find_spec("mcp") is not None
if not SDK_AVAILABLE:
    _fake_mcp = types.ModuleType("mcp")
    _fake_server = types.ModuleType("mcp.server")
    _fake_mcpserver = types.ModuleType("mcp.server.mcpserver")
    _fake_mcpserver.MCPServer = _RegistryServer
    _fake_server.MCPServer = _RegistryServer
    sys.modules.setdefault("mcp", _fake_mcp)
    sys.modules.setdefault("mcp.server", _fake_server)
    sys.modules.setdefault("mcp.server.mcpserver", _fake_mcpserver)


class ToolHandlerSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ars-handler-smoke-")
        os.environ["ARS_STATE_DB"] = str(Path(cls.tmp.name) / "state.sqlite3")
        cls.server_module = importlib.import_module("ars_mcp.server")
        cls.tools = getattr(cls.server_module.mcp, "tools", {})
        cls.core = importlib.import_module("ars_mcp.core")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        os.environ.pop("ARS_STATE_DB", None)

    @unittest.skipIf(SDK_AVAILABLE, "registry-shim assertion is superseded by the official SDK integration suite")
    def test_all_sixteen_handlers_registered(self):
        self.assertEqual(len(self.tools), 16)
        expected = {
            "ars_backend_status", "ars_crossref_search", "ars_crossref_lookup_doi",
            "ars_check_acronyms", "ars_anchorize_draft", "ars_prepare_screening_records",
            "ars_check_pipeline_integrity", "ars_pipeline_status", "ars_pipeline_create",
            "ars_pipeline_get", "ars_pipeline_add_artifact", "ars_pipeline_finish_stage",
            "ars_pipeline_decide", "ars_pipeline_pause", "ars_pipeline_resume",
            "ars_pipeline_delete",
        }
        self.assertEqual(set(self.tools), expected)

    def test_http_security_defaults_are_localhost_only(self):
        values = self.server_module._transport_security_values()
        self.assertTrue(values["enable_dns_rebinding_protection"])
        self.assertIn("127.0.0.1:*", values["allowed_hosts"])
        self.assertIn("localhost:*", values["allowed_hosts"])
        self.assertIn("http://localhost:*", values["allowed_origins"])

    def test_http_security_can_be_configured_for_deployment(self):
        os.environ["ARS_ALLOWED_HOSTS"] = "mcp.example.org,mcp.example.org:*"
        os.environ["ARS_ALLOWED_ORIGINS"] = "https://app.example.org"
        try:
            values = self.server_module._transport_security_values()
            self.assertEqual(values["allowed_hosts"], ["mcp.example.org", "mcp.example.org:*"])
            self.assertEqual(values["allowed_origins"], ["https://app.example.org"])
        finally:
            os.environ.pop("ARS_ALLOWED_HOSTS", None)
            os.environ.pop("ARS_ALLOWED_ORIGINS", None)

    def test_request_body_size_is_bounded_and_defaults_to_twelve_mib(self):
        self.assertEqual(self.server_module._max_request_body_size(), 12 * 1024 * 1024)
        os.environ["ARS_MAX_MCP_REQUEST_BYTES"] = str(16 * 1024 * 1024)
        try:
            self.assertEqual(self.server_module._max_request_body_size(), 16 * 1024 * 1024)
        finally:
            os.environ.pop("ARS_MAX_MCP_REQUEST_BYTES", None)
        os.environ["ARS_MAX_MCP_REQUEST_BYTES"] = "999"
        try:
            with self.assertRaises(ValueError):
                self.server_module._max_request_body_size()
        finally:
            os.environ.pop("ARS_MAX_MCP_REQUEST_BYTES", None)

    @unittest.skipIf(SDK_AVAILABLE, "registry-shim assertion is superseded by the official SDK integration suite")
    def test_all_handlers_execute_with_safe_fixtures(self):
        # Deterministic stand-in for Crossref only; no network is used in this smoke test.
        original_request = self.core._crossref_request
        mock_item = {
            "DOI": "10.5555/ars.smoke",
            "title": ["A reproducible engineering study"],
            "author": [{"given": "Ada", "family": "Lovelace"}],
            "published": {"date-parts": [[2024, 1, 1]]},
            "container-title": ["Journal of Test Studies"],
            "URL": "https://api.crossref.org/works/10.5555/ars.smoke",
        }
        def mock_crossref_request(url):
            if url.endswith("10.5555%2Fars.smoke") or url.endswith("10.5555/ars.smoke"):
                return {"message": mock_item}
            return {"message": {"total-results": 1, "items": [mock_item]}}
        self.core._crossref_request = mock_crossref_request
        try:
            self.assertTrue(self.tools["ars_backend_status"]()["all_required_sources_present"])
            self.assertEqual(self.tools["ars_crossref_search"]("engineering", 1)["returned"], 1)
            self.assertEqual(self.tools["ars_crossref_lookup_doi"]("10.5555/ars.smoke")["doi"], "10.5555/ars.smoke")

            acronym = self.tools["ars_check_acronyms"](
                "# Sample\n\n## Abstract\nRandomized controlled trial (RCT) methods were used.\n"
            )
            self.assertIn(acronym["status"], {"checked", "partial"})

            anchored = self.tools["ars_anchorize_draft"]("# Sample\n\nA short paragraph.\n")
            self.assertTrue(anchored["idempotent"])

            ris = (
                "TY  - JOUR\nTI  - A reproducible engineering study\nAU  - Doe, Jane\n"
                "PY  - 2022\nDO  - 10.5555/ars.screen\nAB  - Abstract for a smoke test.\nER  -\n"
            )
            screening = self.tools["ars_prepare_screening_records"](
                [{"filename": "smoke.ris", "content": ris}], {"smoke.ris": "Fixture"}, 0, 10
            )
            self.assertEqual(screening["records_total"], 1)

            integrity = self.tools["ars_check_pipeline_integrity"]([
                {"path": "phase5_review/review.md", "content": "A review report with no independent reviewer evidence."}
            ])
            self.assertIn("findings", integrity)
            self.assertEqual(len(self.tools["ars_pipeline_status"]()["stages"]), 10)

            created = self.tools["ars_pipeline_create"]("Tool smoke project", "full", "Test question")
            project_id = created["project"]["project_id"]
            token = created["access_token"]
            self.assertEqual(self.tools["ars_pipeline_get"](project_id, token)["current_stage"], "research")

            self.tools["ars_pipeline_add_artifact"](
                project_id, token, "research", "protocol.md", "protocol",
                hashlib.sha256(b"protocol").hexdigest(), len(b"protocol"), "", "smoke"
            )
            self.tools["ars_pipeline_finish_stage"](project_id, token, "research", "complete", "Research stage smoke result")
            self.assertEqual(self.tools["ars_pipeline_decide"](project_id, token, "continue")["current_stage"], "write")
            self.assertEqual(self.tools["ars_pipeline_pause"](project_id, token, "smoke pause")["status"], "paused")
            self.assertEqual(self.tools["ars_pipeline_resume"](project_id, token)["status"], "active")
            self.assertTrue(self.tools["ars_pipeline_delete"](project_id, token, f"DELETE {project_id}")["deleted"])
        finally:
            self.core._crossref_request = original_request


if __name__ == "__main__":
    unittest.main()
