from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT / "skills"))

from ars_mcp import core  # noqa: E402


class BackendCoreTests(unittest.TestCase):
    def test_status_reports_selected_scripts(self):
        result = core.backend_status()
        self.assertTrue(result["all_required_sources_present"])
        self.assertEqual(result["backend_version"], "0.2.4")
        self.assertTrue(all(result["available_tools"].values()))

    def test_anchorize_is_idempotent_and_manifest_hashes(self):
        draft = "# Study\n\nFirst paragraph.\n\nSecond paragraph.\n"
        result = core.anchorize_draft(draft)
        self.assertTrue(result["idempotent"])
        self.assertIn("<!--block:B0001-->", result["anchored_draft"])
        self.assertEqual(result["manifest"]["base_draft_hash"], result["anchored_sha256"][:12])
        self.assertGreaterEqual(len(result["manifest"]["blocks"]), 2)

    def test_acronym_checker_returns_hash_and_coverage(self):
        draft = """# Sample\n\n## Abstract\nRandomized controlled trial (RCT) methods were used.\n\n## Introduction\nRandomized controlled trial (RCT) methods are often reported.\n"""
        result = core.check_acronyms(draft)
        self.assertIn(result["status"], {"checked", "partial"})
        self.assertEqual(len(result["input_sha256"]), 64)
        self.assertIn("coverage", result)

    def test_screening_import_deduplicates_identical_doi_and_title(self):
        ris = """TY  - JOUR\nTI  - A study of reproducible methods in engineering research\nAU  - Doe, Jane\nPY  - 2022\nDO  - 10.5555/ars.test.001\nAB  - A sufficiently long abstract for record preparation and screening.\nER  -\n\nTY  - JOUR\nTI  - A study of reproducible methods in engineering research\nAU  - Doe, Jane\nPY  - 2022\nDO  - 10.5555/ars.test.001\nAB  - Duplicate export of the same record.\nER  -\n"""
        result = core.prepare_screening_records(
            [{"filename": "sample.ris", "content": ris}],
            database_labels={"sample.ris": "Test Database"},
            limit=10,
        )
        self.assertEqual(result["identification"]["raw_total"], 2)
        self.assertEqual(result["records_total"], 1)
        self.assertEqual(result["identification"]["duplicates_removed"], 1)
        self.assertEqual(result["records"][0]["id"], "R00001")

    def test_integrity_checker_reports_phase5_missing_reviewers(self):
        result = core.check_pipeline_integrity([
            {"path": "phase5_review/review.md", "content": "A review report without separate role attribution."}
        ])
        self.assertTrue(result["findings"])
        self.assertIn("Advisory only", result["interpretation"])

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            core.check_pipeline_integrity([{"path": "../secret.txt", "content": "x"}])


    def test_crossref_metadata_mapping(self):
        item = {
            "DOI": "10.5555/example",
            "title": ["A reproducible research example"],
            "author": [{"given": "Ada", "family": "Lovelace"}],
            "published-print": {"date-parts": [[2024, 5, 1]]},
            "container-title": ["Journal of Example Studies"],
            "is-referenced-by-count": 3,
            "URL": "https://api.crossref.org/works/10.5555/example",
        }
        result = core._crossref_item(item)
        self.assertEqual(result["doi_url"], "https://doi.org/10.5555/example")
        self.assertEqual(result["year_or_date"], "2024-05-01")
        self.assertEqual(result["authors"], ["Ada Lovelace"])
        self.assertIn("not proof", result["quality_note"])


    def test_server_registers_expected_tool_surface_without_importing_sdk(self):
        import ast
        server_path = BACKEND / "ars_mcp" / "server.py"
        tree = ast.parse(server_path.read_text(encoding="utf-8"))
        tools = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if any(
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr == "tool"
                    for dec in node.decorator_list
                ):
                    tools.append(node.name)
        self.assertEqual(len(tools), 16)
        self.assertIn("ars_prepare_screening_records", tools)
        self.assertIn("ars_pipeline_create", tools)
        self.assertIn("ars_pipeline_decide", tools)
        self.assertIn("ars_pipeline_delete", tools)

    def test_server_import_uses_documented_public_mcp_python_sdk_api(self):
        import ast
        server_path = BACKEND / "ars_mcp" / "server.py"
        tree = ast.parse(server_path.read_text(encoding="utf-8"))
        imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertTrue(any(node.module == "mcp.server" and any(alias.name == "MCPServer" for alias in node.names) for node in imports))

    def test_doi_validation_rejects_non_doi(self):
        with self.assertRaises(ValueError):
            core.crossref_lookup_doi("https://example.com/paper")

    def test_screening_filename_extension_is_restricted(self):
        with self.assertRaises(ValueError):
            core.prepare_screening_records([{"filename": "attack.py", "content": "print(1)"}])


if __name__ == "__main__":
    unittest.main()
