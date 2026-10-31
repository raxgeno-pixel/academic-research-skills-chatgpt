# MCP Integration Checklist — Backend v0.2.4

This checklist is intentionally conservative. An included test is not the same as a passed test.

## Verified in the current build environment

- [x] All 16 Python tool handlers are declared and registered in the local registry shim.
- [x] All 16 handler functions execute with deterministic safe fixtures under the registry shim.
- [x] 38 unit/handler/CI-asset tests pass (`python -m unittest discover -s backend/tests -v`).
- [x] `pytest -q backend/tests backend/mcp_sdk_tests` reports 38 passed and 4 SDK tests skipped because the official SDK is unavailable locally.
- [x] Python syntax compilation passes for backend and both test directories.
- [x] SQLite main database file is private (mode 0600 on POSIX); newly created database directory is private (mode 0700).
- [x] Streamable HTTP uses SDK DNS-rebinding protection and a Host/Origin allowlist. Default allowlist is loopback-only; remote hostnames must be explicitly added.
- [x] MCP request body size is bounded (12 MiB default; 64 MiB hard maximum).
- [x] Docker image runs as an unprivileged `ars` user.
- [x] Full and standalone package layouts include all six upstream script dependencies used by adapters.
- [x] SDK version is pinned to `mcp==2.3.0` for repeatable installation.

## Runnable but not yet executed (requires the official SDK to be installed)

- [ ] `mcp_sdk_tests/test_mcp_sdk_integration.py`: real SDK in-process client initialization, `tools/list`, schema exposure, and calls to all 16 tools.
- [ ] `mcp_sdk_tests/test_http_transport.py`: real stdio subprocess test and Streamable HTTP client/server test over a local TCP socket.
- [ ] MCP Inspector via `mcp dev backend/ars_mcp/server.py`.

## Remaining production and ChatGPT integration gates

- [ ] Execute the four official SDK tests in `mcp_sdk_tests/` (see `PROTOCOL-TEST-RUNBOOK.md`); all four are currently skipped in this build environment.
- [ ] Verify HTTP error handling, malformed JSON-RPC behavior, Host/Origin negative tests, and request-size rejection.
- [ ] Add OAuth 2.1 resource-server authentication and user/project authorization binding before any public exposure.
- [ ] Run Docker build, container startup, non-root write, and container health tests.
- [ ] Deploy behind TLS with an exact public Host/Origin allowlist.
- [ ] Configure durable storage, backups, restore testing, rate limits, monitoring, retention, and privacy notice.
- [ ] Connect to a supported ChatGPT plan and verify app authorization and tool discovery.

## Security warning

The service remains local/private single-tenant source only. The project capability token protects individual pipeline records but is not transport-level OAuth authentication. The Host/Origin allowlist mitigates DNS rebinding; it is not user authentication. Do not expose the included Streamable HTTP endpoint publicly until OAuth 2.1, TLS, authorization binding, and operational controls are implemented and tested.


## Reproducible CI harness (provided, not run)

- [x] GitHub Actions workflow added for exact SDK installation, in-process/stdio/HTTP protocol tests, and Docker smoke tests.
- [x] Docker smoke script covers all 16 tools, non-root identity, SQLite mode 0600, Host 421, Origin 403, and request body 413.
- [ ] Push the package root to a GitHub repository and obtain a green Actions run.
- [ ] Review and retain the actual Actions run URL and logs as protocol evidence.

- [x] CI workflow YAML, SDK test commands, Docker smoke entry point, security expectations, and the external-run requirement are checked by five local CI-asset tests.
