from __future__ import annotations

import asyncio

import pytest

from hardware_pentest.interfaces.mcp_server import (
    _validate_server_args,
    build_parser,
    build_server,
)
from hardware_pentest.service import HardwarePentestService


def _service(tmp_path) -> HardwarePentestService:
    return HardwarePentestService(
        assessment_root=tmp_path / "assessments",
        verification_root=tmp_path / "verification",
        preflight_root=tmp_path / "preflight",
    )


def test_mcp_server_exposes_only_high_level_domain_tools(tmp_path) -> None:
    server = build_server(_service(tmp_path))
    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}

    assert names == {
        "service_info",
        "hardware_discover",
        "assessment_list",
        "assessment_context",
        "verification_records",
        "preflight_records",
    }
    assert not any("serial" in name for name in names)
    assert not any("raw" in name for name in names)
    assert not any("command" in name for name in names)


def test_mcp_http_defaults_to_loopback_and_stable_port() -> None:
    args = build_parser().parse_args(["--transport", "streamable-http"])

    _validate_server_args(args)

    assert args.host == "127.0.0.1"
    assert args.port == 8765


def test_mcp_refuses_public_network_binding_without_secure_gateway() -> None:
    args = build_parser().parse_args(
        ["--transport", "streamable-http", "--host", "0.0.0.0"]
    )

    with pytest.raises(SystemExit, match="Non-loopback MCP binding is disabled"):
        _validate_server_args(args)


@pytest.mark.parametrize("port", [0, 65536])
def test_mcp_rejects_invalid_port(port: int) -> None:
    args = build_parser().parse_args(["--transport", "streamable-http", "--port", str(port)])

    with pytest.raises(SystemExit, match="--port"):
        _validate_server_args(args)
