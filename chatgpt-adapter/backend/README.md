# Academic Research Skills MCP Backend v0.2.4

This backend exposes bounded research utilities plus a persistent, transactional pipeline state manager. The standalone backend archive is laid out as `backend/` plus a minimal `skills/` dependency tree; the full plugin archive contains the complete skill/dependency tree. It is deployable source code, not an already-hosted endpoint or an automatically attached ChatGPT connection.

## MCP tools

The server exposes 16 tools: seven research utilities and nine pipeline state tools. The tools and their decision boundaries are declared in `ars_mcp/server.py`. The Python MCP SDK is pinned to `mcp==2.3.0` so the tested server/client API does not float across breaking 2.x changes.

### Research utilities

| Tool | Function | Boundary |
|---|---|---|
| `ars_backend_status` | Backend and selected source availability | Does not prove remote connectivity. |
| `ars_crossref_search` | Search Crossref metadata | Metadata discovery only; not a quality or retraction verdict. |
| `ars_crossref_lookup_doi` | Resolve a DOI | Returns Crossref-registered metadata only. |
| `ars_check_acronyms` | Run deterministic acronym checker | Read-only and coverage-bounded. |
| `ars_anchorize_draft` | Add block IDs and create a manifest | Review output before using it as a revision baseline. |
| `ars_prepare_screening_records` | Import RIS/NBIB/WoS TXT/CSV/TSV; normalize and deduplicate | Does not screen or decide inclusion/exclusion. |
| `ars_check_pipeline_integrity` | Advisory phase-integrity checker | Structural/timestamp checks only. |

### Pipeline state tools

| Tool | Function | Boundary |
|---|---|---|
| `ars_pipeline_status` | Return stage model and security/storage policy | Describes capabilities; not deployment health. |
| `ars_pipeline_create` | Create project with one-time access token | Stores metadata, not manuscript text. |
| `ars_pipeline_get` | Retrieve state, artifact metadata, recent event ledger | Requires project ID and capability token. |
| `ars_pipeline_add_artifact` | Register name, type, hash, byte count, locator, provenance note | Does not upload/store file bytes. |
| `ars_pipeline_finish_stage` | Store actual outcome and place mandatory checkpoint | Never advance the stage. |
| `ars_pipeline_decide` | Record explicit decision and enforce state transition | Rejects invalid stage/outcome combinations. |
| `ars_pipeline_pause` / `ars_pipeline_resume` | Pause and resume at the same state | Preserves pending decision checkpoints. |
| `ars_pipeline_delete` | Permanently delete a project and its records | Requires exact `DELETE <project_id>` confirmation. |

## Pipeline model

The state machine contains 10 stage IDs: `research`, `write`, `pre_review_integrity`, `peer_review`, `revise`, `re_review`, `re_revise`, `final_integrity`, `finalize`, and `process_summary`. Each stage completion enters `awaiting_decision`. Only a valid explicit user decision can move the project forward. Integrity failures must be revised; a bypass is available only after three recorded failed rounds and is marked as risk acceptance, never PASS.

## Storage and privacy boundary

SQLite is used with WAL mode, foreign keys, busy timeout, and `BEGIN IMMEDIATE` around state mutations. Configure `ARS_STATE_DB`; mount its parent directory as a durable protected volume. The orchestrator stores project metadata, a research question, bounded stage summaries, issue labels, artifact hashes/metadata, and an event ledger. It does not accept or store manuscript files, PDF contents, abstracts, or full-text documents. Do not put sensitive data in summaries or notes.

The user receives a high-entropy capability token once at project creation; only its SHA-256 digest is stored. This token is an application-level project capability, **not OAuth authentication**. It does not protect the whole MCP HTTP endpoint or all research utility tools. The HTTP server now enables MCP DNS-rebinding protection and a Host/Origin allowlist; defaults are loopback-only. A remote deployment must set `ARS_ALLOWED_HOSTS` and `ARS_ALLOWED_ORIGINS` to exact trusted values and must still add OAuth 2.1 resource-server authentication, TLS, user/project authorization binding, rate limits, abuse controls, monitoring, retention policy, and a privacy notice. Do not treat the allowlist as authentication.

Artifact digests are caller-supplied and their format is checked; this service cannot recompute them because file bytes are not uploaded.

## Local setup from the package root

Python 3.11+ is required. The standalone archive and full plugin archive both use this root layout:

```text
.
├── backend/
│   ├── ars_mcp/
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
└── skills/
    ├── scripts/
    └── sr-screener/scripts/
```

Install and run from the directory containing both `backend/` and `skills/`. The server uses Python 3.11+ and an exact MCP SDK pin for reproducibility:

```bash
python -m venv .venv
# Activate .venv, then:
pip install -r backend/requirements.txt
PYTHONPATH=backend:skills ARS_STATE_DB=./data/ars_state.sqlite3 python -m ars_mcp.server
```

Default transport is stdio. For local Streamable HTTP testing, bind to loopback:

```bash
PYTHONPATH=backend:skills ARS_MCP_TRANSPORT=streamable-http ARS_HOST=127.0.0.1 ARS_PORT=8000 \
ARS_STATE_DB=./data/ars_state.sqlite3 python -m ars_mcp.server
```

The endpoint is `/mcp`. The default Host/Origin allowlist accepts loopback requests only. For a remote deployment, explicitly set (example values only):

```bash
ARS_ALLOWED_HOSTS=ars-mcp.example.org,ars-mcp.example.org:*
ARS_ALLOWED_ORIGINS=https://chatgpt.com
```

Do not use an unrestricted wildcard. The default MCP request body limit is 12 MiB (bounded to 64 MiB); set `ARS_MAX_MCP_REQUEST_BYTES` deliberately if larger screening exports are needed. Use MCP Inspector only after installing the pinned CLI extra (`pip install 'mcp[cli]==2.3.0'`). The SDK's current v2 API uses `MCPServer`; the server import in this package follows the v2 module path.

## Docker

Build from the package root (the directory containing `backend/` and `skills/`):

```bash
docker build -f backend/Dockerfile -t ars-mcp .
```

The container listens on port 8000. The sample Docker image binds to `0.0.0.0` inside the container for port forwarding; publish the port only to loopback for local testing, for example `-p 127.0.0.1:8000:8000`, until OAuth 2.1 and TLS are configured. Mount a durable protected volume at `/data`.

## Tests

From the package root:

```bash
PYTHONPATH=backend:skills python -m unittest discover -s backend/tests -v
```

The suite includes unit tests, handler-level smoke tests, and an official-SDK in-process integration suite using `mcp.Client(mcp_server, raise_exceptions=True)`. The in-process suite exercises SDK initialization, tool discovery, schema exposure, and calls to all 16 tools. The transport suite separately launches the server through stdio and Streamable HTTP clients, so it checks real subprocess and local TCP protocol exchanges. None of these tests alone establishes OAuth, public hosting security, or successful ChatGPT attachment.

## MCP protocol test runbook

See [`PROTOCOL-TEST-RUNBOOK.md`](PROTOCOL-TEST-RUNBOOK.md) for the exact acceptance commands, expected results, Inspector steps, Host/Origin negative tests, and deployment gates.

## Official MCP SDK integration tests

Install test dependencies and run the SDK-backed test suite:

```bash
pip install 'mcp==2.3.0' 'pytest>=8,<10' PyYAML
PYTHONPATH=backend:skills pytest -q backend/mcp_sdk_tests
```

This uses the official in-process SDK client (`Client(mcp, raise_exceptions=True)`) to perform SDK initialization, `tools/list`, schema exposure, and calls all 16 tools with safe fixtures. It also starts the server as a subprocess and uses `Client(StdioServerParameters(...))` and `Client(url)` to test real stdio and Streamable HTTP initialization, tool discovery, and tool calls. These tests are distinct from the registry shim.

For MCP Inspector, use the SDK CLI from the package root (the default `mcp dev` transport is stdio):

```bash
pip install 'mcp[cli]==2.3.0'
PYTHONPATH=backend:skills ARS_STATE_DB=./data/inspector.sqlite3 mcp dev backend/ars_mcp/server.py
```

Select Streamable HTTP only when testing a separately started HTTP server; `mcp dev` defaults to stdio. These wire/Inspector steps have not yet been executed in the current build environment.


## CI workflow

The GitHub repository integration adds `.github/workflows/chatgpt-adapter-ci.yml` at the repository root. It runs the official MCP SDK in-process, stdio, and Streamable HTTP tests, then builds the Docker image from `chatgpt-adapter/` and runs `backend/mcp_sdk_tests/docker_http_smoke.py` against the container. The smoke script validates all 16 tools, non-root execution, SQLite file permissions, Host/Origin rejection, and request-size enforcement. See `CI-RUNBOOK.md`. The workflow is provided but has not been run in this build environment.
