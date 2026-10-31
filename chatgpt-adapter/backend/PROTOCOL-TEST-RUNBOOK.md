# MCP Protocol Test Runbook — Backend v0.2.4

This runbook is the acceptance sequence for the official MCP Python SDK. Run it on a network-enabled machine with Python 3.11+ and Node.js available if you intend to use MCP Inspector.

## 1. Install the exact SDK and test tools

Run from the package root (the directory containing `backend/` and `skills/`):

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install 'mcp==2.3.0' 'pytest>=8,<10' 'PyYAML>=6,<7'
```

The MCP 2.3.0 wheel published on PyPI has SHA-256:

```text
dd0c44c089d16453e8ae31a3877a0054d7a2314caaa81f5e0541b9b1734b2377
```

PyPI release record: <https://pypi.org/project/mcp/2.3.0/>. Pinning is intentional; do not silently float to another SDK release during acceptance testing.

## 2. Run unit and protocol integration tests

```bash
PYTHONPATH=backend:skills python -m unittest discover -s backend/tests -v
PYTHONPATH=backend:skills python -m pytest -q backend/tests backend/mcp_sdk_tests -vv
```

The second command must execute the four SDK-backed tests, not skip them. They cover:

- In-process `Client(mcp, raise_exceptions=True)` initialization and protocol negotiation.
- `tools/list`, schema shape, and `tools/call` for all 16 registered tools using safe fixtures (Crossref is mocked in this test).
- Real stdio subprocess initialization, tool discovery, and tool invocation.
- Real local Streamable HTTP initialization, tool discovery, and tool invocation over TCP.

Expected result in a complete SDK-enabled environment: **37 passed, 0 skipped** (33 local unit/handler/config tests plus four SDK protocol tests). If the count differs, inspect all skip and failure reasons rather than treating a partial run as a pass.

## 3. Inspect the stdio server

Install the CLI extra and start the MCP Inspector:

```bash
python -m pip install 'mcp[cli]==2.3.0'
PYTHONPATH=backend:skills ARS_STATE_DB=./data/inspector.sqlite3 mcp dev backend/ars_mcp/server.py
```

The default `mcp dev` launch uses stdio. Confirm that all 16 tools are visible, inspect their input schemas, then call `ars_backend_status` and `ars_pipeline_status`. Do not use actual manuscript or personal data in acceptance fixtures.

## 4. Inspect Streamable HTTP locally

Terminal A:

```bash
mkdir -p ./data
PYTHONPATH=backend:skills \
ARS_MCP_TRANSPORT=streamable-http \
ARS_HOST=127.0.0.1 ARS_PORT=8000 \
ARS_STATE_DB=./data/http-inspector.sqlite3 \
ARS_ALLOWED_HOSTS='127.0.0.1:*,localhost:*,[::1]:*' \
ARS_ALLOWED_ORIGINS='http://127.0.0.1:*,http://localhost:*,http://[::1]:*' \
python -m ars_mcp.server
```

Terminal B: connect the MCP Inspector to `http://127.0.0.1:8000/mcp`. Verify the initialize handshake, `tools/list`, and a harmless status-tool call. Confirm that an unlisted `Host` header is rejected and that the server logs the rejection.

## 5. Required negative and operational tests before deployment

- An unlisted Host must receive the SDK's DNS-rebinding protection rejection.
- A browser Origin not in `ARS_ALLOWED_ORIGINS` must be rejected.
- Request bodies larger than `ARS_MAX_MCP_REQUEST_BYTES` must be rejected before tool execution.
- A wrong project capability token must not disclose a project or its contents.
- A non-root container must be able to create/write the SQLite database on the mounted `/data` volume, while other users cannot read its database file.
- Restart the container and verify state persistence from the mounted volume; separately test backup restoration.
- If behind a TLS-terminating reverse proxy, use HTTPS externally, trust only the actual proxy IP for forwarded headers, and configure exact Host/Origin values. Do not trust `X-Forwarded-*` from arbitrary network clients.

## 6. Acceptance boundary

Passing this runbook proves MCP SDK interoperability for the tested SDK version and local transports. It does **not** prove production security. Before any public exposure, implement and test OAuth 2.1 resource-server authentication, tenant/user-to-project authorization, TLS, rate limits, monitoring, backup/restore, retention controls, and privacy terms. A per-project capability token is not transport-level authentication.
