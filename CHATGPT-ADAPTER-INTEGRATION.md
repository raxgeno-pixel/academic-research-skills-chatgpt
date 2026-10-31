# ChatGPT adapter integration

This change adds the ChatGPT adaptation as a separate package under `chatgpt-adapter/`. The original Claude Code project remains at the repository root and is not overwritten. The existing upstream CI workflows remain unchanged; the new workflow is `.github/workflows/chatgpt-adapter-ci.yml`.

## Package contents

- `chatgpt-adapter/skills/`: five ChatGPT-native skill entry points and their referenced support files.
- `chatgpt-adapter/backend/`: MCP server, transactional SQLite workflow state, tests, and Dockerfile.
- `chatgpt-adapter/plugin.json` and `chatgpt-adapter/.codex-plugin/plugin.json`: plugin manifests.
- `chatgpt-adapter/CHATGPT-PORT.md`: compatibility boundaries and source attribution.

## CI behavior

The new workflow runs only when `chatgpt-adapter/**` or its own workflow file changes. It installs the pinned `mcp==2.3.0` SDK, compiles the backend, runs unit/handler and official SDK protocol tests, then builds the Docker image and runs the Streamable HTTP/security smoke test.

## Apply

Extract/merge this patch archive at the repository root. It contains only new `chatgpt-adapter/`, `.github/workflows/chatgpt-adapter-ci.yml`, and `CHATGPT-ADAPTER-INTEGRATION.md` paths. Do not overwrite the original Claude Code directories or the repository's existing workflows.

## Verification boundary

The source package has local test evidence recorded in `chatgpt-adapter/CHATGPT-PORT.md` and `chatgpt-adapter/STAGE7-RELEASE-NOTES.md`. This patch has not been pushed to GitHub and no GitHub Actions run is claimed. A passing CI run is still required to validate the official SDK protocol tests and Docker execution in GitHub's runner environment. OAuth 2.1, external TLS, production deployment, and a live ChatGPT MCP connection remain separate work.
