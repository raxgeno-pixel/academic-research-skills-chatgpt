# CI Runbook — Academic Research Skills MCP

Version: backend 0.2.4 / plugin 3.25.8

The repository integration adds a GitHub Actions workflow at the repository-root path `.github/workflows/chatgpt-adapter-ci.yml`. The adapter itself is isolated under `chatgpt-adapter/`.
It is designed to run where PyPI access and Docker are available; it is **not** a
record of a CI run. To execute it, place the `chatgpt-adapter/` directory (containing `backend/` and `skills/`) in the repository, commit the repository-root workflow at `.github/workflows/chatgpt-adapter-ci.yml`, and push to a branch or manually select `workflow_dispatch` in GitHub Actions.

## Jobs

1. `python-tests` installs the exact `mcp==2.3.0` SDK, compiles the sources, runs
   the deterministic unit tests, then runs all SDK integration tests. This includes
   `Client(mcp_server)` in-process tests and subprocess stdio / local Streamable
   HTTP protocol tests.
2. `docker-smoke` builds the supplied Dockerfile, launches the container as its
   configured non-root user, then uses the official SDK `Client` against the
   container's `/mcp` endpoint. It checks all 16 tools, creates a pipeline record,
   verifies SQLite mode `0600`, and requires negative HTTP tests to reject a
   disallowed Host (421), disallowed Origin (403), and oversized body (413).

## Manual local commands

```bash
python -m pip install -r chatgpt-adapter/backend/requirements.txt 'pytest>=8,<10'
PYTHONPATH=chatgpt-adapter/backend:chatgpt-adapter/skills python -m unittest discover -s chatgpt-adapter/backend/tests -v
PYTHONPATH=chatgpt-adapter/backend:chatgpt-adapter/skills pytest -c chatgpt-adapter/backend/pyproject.toml -q chatgpt-adapter/backend/tests chatgpt-adapter/backend/mcp_sdk_tests
```

Docker smoke test (after installing Docker and `mcp==2.3.0`):

```bash
ARS_CI_IMAGE=ars-mcp:ci \
ARS_CI_CONTAINER=ars-mcp-ci \
ARS_CI_PORT=18765 \
ARS_CI_MAX_BODY_BYTES=1048576 \
python chatgpt-adapter/backend/mcp_sdk_tests/docker_http_smoke.py
```

First build the image from the package root:

```bash
docker build -f chatgpt-adapter/backend/Dockerfile -t ars-mcp:ci chatgpt-adapter
```

## What this still does not verify

A green CI run would validate SDK protocol operation, the local Docker HTTP server,
Host/Origin rejection, request-size enforcement, non-root runtime and local database
permissions. It would **not** establish OAuth 2.1, external TLS termination, public
DNS/reverse-proxy configuration, backup/restore, multi-tenant authorization, or a
live ChatGPT connection. Those remain separate deployment acceptance gates.
