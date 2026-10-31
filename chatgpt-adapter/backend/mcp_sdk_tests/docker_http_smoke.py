"""Dockerized Streamable HTTP smoke and negative security tests.

The GitHub Actions job builds the image, launches it with a private data
volume, then this script uses the official MCP SDK client plus raw HTTP probes.
It is not a substitute for OAuth/TLS acceptance testing on a real deployment.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request

from mcp import Client

IMAGE = os.environ["ARS_CI_IMAGE"]
CONTAINER = os.environ["ARS_CI_CONTAINER"]
PORT = int(os.environ.get("ARS_CI_PORT", "18765"))
BODY_LIMIT = int(os.environ.get("ARS_CI_MAX_BODY_BYTES", "1048576"))
ENDPOINT = f"http://127.0.0.1:{PORT}/mcp"


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, capture_output=True)


def _wait_for_port(timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.4):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.2)
    logs = _run("docker", "logs", CONTAINER, check=False).stderr
    raise TimeoutError(f"Container did not listen on port {PORT}: {last_error}\n{logs}")


def _post_probe(*, host: str, origin: str | None, body: bytes) -> tuple[int, str]:
    headers = {
        "Host": host,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if origin is not None:
        headers["Origin"] = origin
    request = urllib.request.Request(ENDPOINT, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read(2048).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(2048).decode("utf-8", "replace")


def _protocol_initialize_body() -> bytes:
    return json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "ars-ci-security-probe", "version": "1.0.0"},
        },
    }).encode("utf-8")


async def _sdk_smoke() -> None:
    async with Client(ENDPOINT) as client:
        assert client.server_info is not None
        assert client.protocol_version
        listed = await client.list_tools()
        names = {tool.name for tool in listed.tools}
        assert len(names) == 16, sorted(names)
        status = await client.call_tool("ars_backend_status", {})
        assert not status.is_error, status.content
        assert status.structured_content is not None

        created = await client.call_tool("ars_pipeline_create", {
            "title": "Docker CI smoke project",
            "workflow_type": "full",
            "research_question": "Verify database permissions in a non-root container.",
        })
        assert not created.is_error, created.content


def _storage_and_identity_checks() -> None:
    uid = int(_run("docker", "exec", CONTAINER, "id", "-u").stdout.strip())
    assert uid != 0, f"Container is running as root (uid={uid})"
    mode = _run(
        "docker", "exec", CONTAINER,
        "stat", "-c", "%a", "/data/ars_state.sqlite3",
    ).stdout.strip()
    assert mode == "600", f"SQLite database mode is {mode!r}, expected '600'"


def _http_security_negative_tests() -> None:
    init = _protocol_initialize_body()

    host_status, host_body = _post_probe(
        host="attacker.invalid", origin=None, body=init,
    )
    assert host_status == 421, f"Unexpected disallowed Host result: {host_status}: {host_body}"

    origin_status, origin_body = _post_probe(
        host=f"127.0.0.1:{PORT}", origin="https://attacker.invalid", body=init,
    )
    assert origin_status == 403, f"Unexpected disallowed Origin result: {origin_status}: {origin_body}"

    oversized = b" " * (BODY_LIMIT + 1)
    size_status, size_body = _post_probe(
        host=f"127.0.0.1:{PORT}", origin=None, body=oversized,
    )
    assert size_status == 413, f"Unexpected oversized request result: {size_status}: {size_body}"


def main() -> None:
    _run("docker", "run", "-d", "--name", CONTAINER,
         "-p", f"127.0.0.1:{PORT}:8000",
         "-e", "ARS_ALLOWED_HOSTS=127.0.0.1:*,localhost:*,[::1]:*",
         "-e", "ARS_ALLOWED_ORIGINS=http://127.0.0.1:*,http://localhost:*,http://[::1]:*",
         "-e", f"ARS_MAX_MCP_REQUEST_BYTES={BODY_LIMIT}",
         IMAGE)
    try:
        _wait_for_port()
        asyncio.run(_sdk_smoke())
        _storage_and_identity_checks()
        _http_security_negative_tests()
        print("PASS: official SDK client initialized over Streamable HTTP")
        print("PASS: tools/list returned all 16 tools; backend and pipeline tools/call succeeded")
        print("PASS: container process is non-root; SQLite database mode is 0600")
        print("PASS: disallowed Host => 421; disallowed Origin => 403; oversized request => 413")
    finally:
        _run("docker", "rm", "-f", CONTAINER, check=False)


if __name__ == "__main__":
    main()
