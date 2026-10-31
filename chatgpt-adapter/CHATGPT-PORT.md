# ChatGPT Port — Complete Source Preservation, Dependency Integration, and Runtime Test Mapping (v3.25.8)

## What is included
This release contains the five ChatGPT skill entry points under `skills/`: `deep-research`, `academic-paper`, `academic-paper-reviewer`, `academic-pipeline`, and `sr-screener`. Their supporting agents, references, examples, templates, and screening scripts are retained. Cross-skill dependencies are additionally mirrored under `skills/` so project-root references such as `shared/`, `docs/`, and `scripts/` resolve from the active skill package.

The complete upstream repository supplied for this conversion is also preserved byte-for-byte under `upstream/academic-research-skills-main/`. This includes the original Claude Code plugin metadata, slash commands, agent definitions, hooks, scripts, tests, evaluation fixtures, documentation, workflows, and repository assets. The upstream snapshot is included for completeness, auditability, and future porting; Claude-specific runtime files are not activated by ChatGPT merely by being present.

## Dependency integration (v3.25.3)
The package includes 499 path-compatible dependency mirrors selected from the supplied upstream source: `shared/` (147), `docs/` (41), `scripts/` (132), root-level `agents/` (1), `commands/` (1), `evals/` (143), `examples/` (25), selected `audits/`, `pi/`, and `tests/` references (3), and six root-level project documents. Each active skill points to `skills/DEPENDENCY-INDEX.md`. All 499 mirrored files are byte-identical to their upstream counterparts. Validation found 274 relative Markdown links across the selected support package with no unresolved links, and 215 upstream-resolvable project-relative path references in the active skills with no missing mirrored target. The mirror is intentionally selective; the full source remains under `upstream/`. This stage does not activate Claude hooks or legacy slash commands. Selected deterministic scripts are called only through the separately packaged backend adapters.

## Backend integration (v3.25.8)
The `backend/` directory contains an MCP server implementation pinned to the official MCP Python SDK `mcp==2.3.0`. It exposes sixteen bounded tools (seven research utilities and nine pipeline state tools): backend status, Crossref search and DOI lookup, acronym checking, draft anchorization, systematic-review record import/de-duplication, advisory pipeline-integrity checking, and ten-stage pipeline-state management. The server code is included but is not hosted or connected to ChatGPT by this plugin archive. A reachable HTTPS deployment and an eligible ChatGPT custom-MCP connection are separate prerequisites. The current Docker sample runs as a non-root user and uses a loopback-default Host/Origin allowlist; it remains local/private test configuration, not a production public deployment.

## Runtime compatibility boundary
ChatGPT can use the packaged `SKILL.md` instructions and supporting text/reference files when the plugin runtime exposes them. The original project targets Claude Code. Claude slash commands, lifecycle hooks, agent dispatch, local filesystem assumptions, shell commands, and Python/Node scripts do not become executable ChatGPT capabilities just because they are included.

Where an original workflow expects a Claude command, treat it as a user-invocable workflow through the corresponding skill. Where it expects deterministic code, batch processing, external APIs, persistent state, or multi-agent execution, the included MCP/API backend must first be deployed, protected, and connected through a supported ChatGPT account/workspace. No unsupported execution is claimed.

## Functional mapping
| Upstream capability | ChatGPT adaptation | Boundary
|---|---|---|
| `deep-research` | `skills/deep-research/SKILL.md` | Research discovery and synthesis can use available search/research tools; API-specific protocols require connected services. |
| `academic-paper` | `skills/academic-paper/SKILL.md` | Drafting, planning, revision, and citation guidance are instruction-driven; file conversion or scripted validation requires tools. |
| `academic-paper-reviewer` | `skills/academic-paper-reviewer/SKILL.md` | Reviewer perspectives are simulated within one assistant workflow, not independent Claude subagents. |
| `academic-pipeline` | `skills/academic-pipeline/SKILL.md` | Stage gates and human approvals are instruction-driven; persistent state and automated orchestration require backend support. |
| `sr-screener` | `skills/sr-screener/SKILL.md` | Screening criteria and decision guidance are retained; included Python/JS scripts are source assets and need an execution backend. |
| Claude slash commands | Preserved in upstream snapshot | Not directly callable as ChatGPT slash commands. |
| Claude hooks | Preserved in upstream snapshot | Not activated by ChatGPT. |
| Tests/evals/fixtures | Preserved in upstream snapshot | Not automatically run by plugin installation; must be executed in a compatible test harness. |

## Completeness statement
The full supplied upstream repository snapshot is included in this release. This is source-file preservation of the supplied ZIP payload, not a claim of 100% runtime or behavioral equivalence. The backend tools implement only the explicitly listed operations; they do not recreate the full Claude Code runtime. Full behavioral parity requires porting and testing each runtime-dependent feature against supported ChatGPT APIs/tools.

## Attribution and license
Adapted from Academic Research Skills by Cheng-I Wu: https://github.com/Imbad0202/academic-research-skills. Licensed CC BY-NC 4.0. Attribution and non-commercial restrictions apply. No endorsement by the original author is implied.


## Stage 4 — Workflow orchestration

A SQLite state manager is included under `backend/ars_mcp/pipeline.py`. It enforces named stages, allowed outcomes, human approval checkpoints, bounded integrity-failure loops, explicit risk overrides, pause/resume, artifact metadata registration, capability-token access, and project deletion. The active `academic-pipeline` skill describes tool invocation only when MCP tools are actually exposed in the session. This is not autonomous agent dispatch and does not by itself connect the backend to ChatGPT. OAuth 2.1, secure remote hosting, and MCP wire-protocol interoperability remain deployment tasks.


## Stage 5 — Integration test status (v3.25.8)

The source bundle passes 38 unit/handler/CI-asset tests. A combined pytest run reports 38 passed and four official-SDK tests skipped because `mcp==2.3.0` could not be downloaded in the isolated build environment. The package includes real SDK tests for `Client(mcp)` initialization, `tools/list`, schema exposure, all 16 tool calls, Streamable HTTP, and stdio subprocess transport. Those SDK tests are prepared but have not been executed. MCP Inspector, OAuth 2.1, Docker runtime, public hosting, and ChatGPT connection are also unverified. The standalone backend archive includes the six upstream scripts required by the backend adapters and is tested from its extracted package-root layout.

## Stage 6 — Security and SDK compatibility preparation (v3.25.8)

The MCP SDK is pinned to `2.3.0`. Streamable HTTP enables SDK DNS-rebinding protection with a loopback-only Host/Origin default allowlist. Request bodies are bounded (12 MiB default, 64 MiB maximum). SQLite database files are private on POSIX, newly created database directories are private, and the Docker image runs as an unprivileged user. These controls reduce local deployment risk but do not replace OAuth 2.1 authentication, user/project authorization binding, TLS, rate limits, monitoring, backup/restore, or retention controls. Docker build/runtime and live protocol tests remain pending because this environment has no Docker engine and cannot resolve the PyPI wheel host.


## Stage 6 protocol-test preparation update

The MCP server now uses the SDK's documented public import `from mcp.server import MCPServer`. Four official SDK protocol tests are packaged: in-process initialization/list/call coverage for all 16 tools, Streamable HTTP over a local socket, and stdio subprocess transport. They remain **skipped**, not passed, in this build environment because the official SDK wheel cannot be downloaded. The SDK version is pinned exactly to `mcp==2.3.0`; the public PyPI release is independently verifiable by its published SHA-256. The test invocation is documented in `backend/README.md`.

The Docker sample is not a public deployment template: it binds inside the container but retains a loopback-only Host/Origin allowlist unless an operator explicitly configures exact public hostnames. Public exposure still requires OAuth 2.1, TLS, identity authorization, backups, rate controls, and monitoring.


## Stage 7 — Reproducible protocol and Docker CI harness (v3.25.8)

The repository integration adds `.github/workflows/chatgpt-adapter-ci.yml` at the repository root; the adapter package itself remains isolated under `chatgpt-adapter/`. In a GitHub repository, it installs the exact MCP SDK 2.3.0, runs the real in-process, stdio, and Streamable HTTP client tests, then builds the supplied Docker image and runs the official SDK client against the container. The Docker smoke script checks all 16 tools, non-root execution, SQLite mode 0600, rejected Host (421), rejected Origin (403), and over-limit request body (413). The workflow is included as source; it has **not** been executed in this environment because PyPI DNS is unavailable and no Docker daemon is exposed. A green CI run is still required before calling wire protocol or container behavior verified.

## Stage 7 release notes — reproducible CI harness (v3.25.8)

Backend is now v0.2.4. Five CI-asset tests validate the GitHub Actions workflow, exact MCP SDK pin, integration-test commands, Docker smoke entry point, and disclosure that CI must still run externally. The workflow runs 38 unit/configuration/handler/CI-asset tests plus four SDK-backed protocol tests, then a Docker Streamable HTTP smoke/security job. The local verification result is **38 passed, 4 SDK tests skipped, 0 failed**; skipped means not executed because the SDK wheel could not be downloaded in this environment. Docker is not installed here. No green GitHub Actions run is claimed.
