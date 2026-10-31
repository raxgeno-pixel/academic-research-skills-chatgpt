from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ADAPTER_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ADAPTER_ROOT.parent
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "chatgpt-adapter-ci.yml"


class CICheckAssetsTests(unittest.TestCase):
    def test_github_actions_workflow_is_valid_yaml_and_has_expected_triggers(self):
        self.assertTrue(WORKFLOW.is_file())
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        self.assertEqual(workflow["name"], "Academic Research Skills ChatGPT Adapter CI")
        triggers = workflow.get("on", workflow.get(True, {}))  # PyYAML 1.1 parses `on` as True.
        self.assertTrue({"push", "pull_request", "workflow_dispatch"}.issubset(triggers))

    def test_workflow_runs_sdk_tests_after_installing_exact_sdk_pin(self):
        workflow = yaml.safe_load(WORKFLOW.read_text())
        requirement = (ADAPTER_ROOT / "backend" / "requirements.txt").read_text()
        self.assertIn("mcp==2.3.0", requirement)
        steps = workflow["jobs"]["python-tests"]["steps"]
        run_blocks = "\n".join(str(step.get("run", "")) for step in steps)
        self.assertIn("pytest -c chatgpt-adapter/backend/pyproject.toml", run_blocks)
        self.assertIn("python -m compileall", run_blocks)

    def test_workflow_builds_docker_and_runs_http_smoke_script(self):
        workflow = yaml.safe_load(WORKFLOW.read_text())
        steps = workflow["jobs"]["docker-smoke"]["steps"]
        run_blocks = "\n".join(str(step.get("run", "")) for step in steps)
        self.assertIn("docker build -f chatgpt-adapter/backend/Dockerfile", run_blocks)
        self.assertIn("chatgpt-adapter/backend/mcp_sdk_tests/docker_http_smoke.py", run_blocks)

    def test_docker_smoke_asserts_core_protocol_and_security_contracts(self):
        smoke = (ADAPTER_ROOT / "backend" / "mcp_sdk_tests" / "docker_http_smoke.py").read_text()
        for expected in ("len(names) == 16", "uid != 0", 'mode == "600"',
                         "host_status == 421", "origin_status == 403", "size_status == 413"):
            self.assertIn(expected, smoke)

    def test_ci_runbook_discloses_that_workflow_requires_external_execution(self):
        runbook = ADAPTER_ROOT / "backend" / "CI-RUNBOOK.md"
        self.assertTrue(runbook.is_file())
        contents = " ".join(re.sub(r"[*_`]", "", runbook.read_text().lower()).split())
        self.assertIn("not a record of a ci run", contents)
        self.assertIn("oauth 2.1", contents)


if __name__ == "__main__":
    unittest.main()
