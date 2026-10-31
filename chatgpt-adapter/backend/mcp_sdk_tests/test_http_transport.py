"""Real Streamable HTTP MCP protocol smoke test using the official SDK client.

Run from the package root with the pinned `mcp==2.3.0` dependency installed:
    PYTHONPATH=backend:skills pytest -q backend/mcp_sdk_tests
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(PACKAGE_ROOT / "skills"))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_listening(process: subprocess.Popen, port: int, timeout: float = 12.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"MCP server exited early with code {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.1)
    raise TimeoutError(f"MCP HTTP server did not start on port {port}: {last_error}")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_streamable_http_initialize_list_tools_and_call(tmp_path):
    try:
        from mcp import Client
    except ImportError:
        pytest.skip("official MCP SDK is not installed in this test environment")

    port = _free_port()
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(BACKEND), str(PACKAGE_ROOT / "skills")]),
        "ARS_MCP_TRANSPORT": "streamable-http",
        "ARS_HOST": "127.0.0.1",
        "ARS_PORT": str(port),
        "PORT": str(port),
        "ARS_STATE_DB": str(tmp_path / "http-mcp.sqlite3"),
        "ARS_ALLOWED_HOSTS": "127.0.0.1:*,localhost:*,[::1]:*",
        "ARS_ALLOWED_ORIGINS": "http://127.0.0.1:*,http://localhost:*,http://[::1]:*",
        "ARS_MAX_MCP_REQUEST_BYTES": str(12 * 1024 * 1024),
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "ars_mcp.server"],
        cwd=PACKAGE_ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_until_listening(process, port)
        async with Client(f"http://127.0.0.1:{port}/mcp") as client:
            assert client.server_info is not None
            assert client.protocol_version
            listed = await client.list_tools()
            names = {tool.name for tool in listed.tools}
            assert len(names) == 16
            assert "ars_backend_status" in names
            status = await client.call_tool("ars_backend_status", {})
            assert status.is_error is False
            assert status.structured_content is not None
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.anyio
async def test_stdio_subprocess_initialize_list_tools_and_call(tmp_path):
    try:
        from mcp import Client, StdioServerParameters
    except ImportError:
        pytest.skip("official MCP SDK is not installed in this test environment")

    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ars_mcp.server"],
        env={
            "PYTHONPATH": os.pathsep.join([str(BACKEND), str(PACKAGE_ROOT / "skills")]),
            "PYTHONUTF8": "1",
            "ARS_MCP_TRANSPORT": "stdio",
            "ARS_STATE_DB": str(tmp_path / "stdio-mcp.sqlite3"),
        },
    )
    async with Client(server) as client:
        assert client.server_info is not None
        assert client.protocol_version
        listed = await client.list_tools()
        names = {tool.name for tool in listed.tools}
        assert len(names) == 16
        assert "ars_pipeline_status" in names
        status = await client.call_tool("ars_pipeline_status", {})
        assert status.is_error is False
        assert status.structured_content is not None
