# Backend Security Notes — v0.2.4

## Implemented in this release

- SQLite main database file is chmod 0600 on POSIX. A parent directory created by the backend is chmod 0700. Existing caller-supplied directories are not chmodded.
- Docker container runs as unprivileged `ars` user. A dedicated persistent `/data` volume is expected.
- MCP Streamable HTTP transport uses `TransportSecuritySettings` with DNS-rebinding protection enabled. Defaults accept loopback Host and Origin values only.
- Remote Host and browser Origin values must be set explicitly through `ARS_ALLOWED_HOSTS` and `ARS_ALLOWED_ORIGINS`. Avoid wildcard host/origin entries.
- MCP request bodies are limited to 12 MiB by default; configurable with a hard maximum of 64 MiB.
- SDK dependency is pinned to `mcp==2.3.0`.

## Not implemented

- OAuth 2.1 authorization server / resource-server token verification.
- Per-user identity and tenant binding for projects.
- Rate limiting, quotas, abuse monitoring, audit export, backup/restore automation, and retention enforcement.
- TLS termination and a production reverse-proxy configuration.
- Secret rotation and managed secret storage.

## Deployment rule

Do not expose this service directly to the public internet. The application-level project token is only a capability for a particular project; it does not authenticate general MCP calls or protect utility tools. A public deployment must add OAuth 2.1, TLS, identity-to-project authorization, rate limiting, monitoring, durable backups, and a privacy/retention policy.


## Reverse-proxy requirements

The sample image is deliberately loopback-allowlisted even though the process binds to `0.0.0.0` inside the container. Configure `ARS_ALLOWED_HOSTS` and `ARS_ALLOWED_ORIGINS` to exact production values only after deploying behind a controlled TLS proxy and adding OAuth 2.1. When TLS terminates upstream, trust forwarded headers only from the proxy's actual IP address. Do not use a wildcard `Host`/`Origin` allowlist as a shortcut. See `PROTOCOL-TEST-RUNBOOK.md`.
