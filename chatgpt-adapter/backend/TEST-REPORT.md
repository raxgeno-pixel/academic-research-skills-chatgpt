# Backend v0.2.4 Test Report

## Executed in the current build environment

- `python -m unittest discover -s backend/tests -v`: **38 passed, 0 failed**.
- `PYTHONPATH=backend:skills pytest -q backend/tests backend/mcp_sdk_tests`: **38 passed, 4 skipped, 0 failed**. The four skipped cases require the official MCP SDK package, which could not be installed in this environment.
- Python syntax compilation: backend source and all test source files passed `compileall`.
- Static tool declaration check: 16 MCP tool decorators.
- Handler registry-shim calls: 16/16. This is not an MCP SDK or wire-protocol test.
- Database permission check: SQLite main database file mode is private on POSIX.
- HTTP transport configuration tests: loopback-only Host/Origin defaults, explicit allowlist overrides, and bounded request-size configuration.
- Standalone packaging: six upstream script dependencies are included in the extracted backend package.

## Official SDK tests included but not executed here

The package includes real SDK tests, pinned to `mcp==2.3.0`:

- `mcp_sdk_tests/test_mcp_sdk_integration.py` uses `Client(mcp, raise_exceptions=True)` for SDK initialization, tool discovery, schema exposure, and calls to all 16 tools.
- `mcp_sdk_tests/test_http_transport.py` starts the server as a subprocess and tests both `Client(StdioServerParameters(...))` over stdio and `Client(url)` over a real local Streamable HTTP socket.

These four tests were skipped because this build environment cannot resolve `files.pythonhosted.org`; the verified PyPI wheel could not be downloaded. PyPI lists MCP SDK 2.3.0 as released on 2 October 2026 and publishes the wheel SHA-256 `dd0c44c089d16453e8ae31a3877a0054d7a2314caaa81f5e0541b9b1734b2377`. The executable acceptance commands are documented in `PROTOCOL-TEST-RUNBOOK.md`.

## Not executed / not proven

- Official SDK in-process and Streamable HTTP test execution.
- stdio wire protocol and MCP Inspector compatibility.
- Malformed JSON-RPC / HTTP error handling.
- OAuth 2.1, TLS termination, public deployment, or ChatGPT MCP connection.
- Live Crossref requests.

Do not describe the service as protocol-verified or production-ready until those checks have passed in a network-enabled deployment environment.


## CI harness added in v0.2.4

A GitHub Actions workflow is included to install the pinned SDK in a network-enabled runner, run the real MCP Client integration tests, build the Docker image, and perform container/HTTP security smoke checks. It is source-only until run from a GitHub repository. No CI result is claimed by this report.
