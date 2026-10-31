# Academic Research Skills — Stage 7 Release Notes

Plugin release: **3.25.8**  
Backend release: **0.2.4**

## Work completed

- Added repository-root `.github/workflows/chatgpt-adapter-ci.yml` with two jobs: official SDK tests and a Docker/Streamable HTTP security smoke run.
- Added `backend/mcp_sdk_tests/docker_http_smoke.py` to verify the container through the official SDK client, all 16 tool registrations, a pipeline state write, non-root execution, SQLite mode `0600`, invalid Host rejection (`421`), invalid Origin rejection (`403`), and request body limit rejection (`413`).
- Added `backend/CI-RUNBOOK.md` with repository setup, local commands, CI behavior, and remaining production gates.
- Added five static tests validating the workflow and its smoke-test requirements.
- Bumped backend package/pipeline version to `0.2.4` and plugin package version to `3.25.8`.

## Verification performed in this build environment

- Python compilation: passed.
- `python -m unittest discover -s backend/tests -q`: **38 passed**.
- `pytest -q backend/tests backend/mcp_sdk_tests`: **38 passed, 4 skipped, 0 failed**.
- YAML parse: passed.
- Standalone backend archive was re-extracted and the same test commands were rerun: **38 passed, 4 skipped, 0 failed**.

## Explicitly not verified

- Four official MCP SDK protocol tests are included but skipped because this environment could not resolve/download the PyPI MCP SDK wheel.
- Docker is not installed in this environment; image build/runtime and the Docker HTTP smoke script have not run.
- GitHub Actions workflow has not been pushed to or run in a GitHub repository.
- MCP Inspector, OAuth 2.1, public HTTPS deployment, reverse-proxy configuration, multi-tenant authorization, and live ChatGPT connection have not been tested.

The CI workflow is an executable acceptance harness, not evidence of a completed run. Do not mark the protocol or Docker gates complete until there is a green CI run with retained logs.
