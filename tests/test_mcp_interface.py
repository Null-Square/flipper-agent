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
        engagement_root=tmp_path / "engagements",
        evidence_root=tmp_path / "evidence",
        verification_root=tmp_path / "verification",
        preflight_root=tmp_path / "preflight",
        gate_root=tmp_path / "gates",
        implementation_root=tmp_path / "implementations",
        generated_project_root=tmp_path / "generated",
    )


def _tool_names(server) -> set[str]:
    return {tool.name for tool in asyncio.run(server.list_tools())}


def test_mcp_read_only_server_exposes_high_level_context_and_candidates(tmp_path) -> None:
    names = _tool_names(build_server(_service(tmp_path)))

    assert names == {
        "service_info",
        "hardware_discover",
        "engagement_list",
        "assessment_list",
        "assessment_context",
        "assessment_candidates",
        "implementation_records",
        "verification_records",
        "preflight_records",
    }
    assert "assessment_create" not in names
    assert "assessment_synthesis_work_order" not in names
    assert "assessment_synthesis_candidate_build" not in names
    assert "assessment_execute_next" not in names
    assert "assessment_recover_interrupted" not in names
    assert not any("serial" in name for name in names)
    assert not any("raw" in name for name in names)
    assert not any("command" in name for name in names)
    assert not any("gate_grant" in name for name in names)
    assert not any("engagement_import" in name for name in names)


def test_mcp_mutating_tools_require_explicit_server_opt_in(tmp_path) -> None:
    names = _tool_names(build_server(_service(tmp_path), allow_execution=True))

    assert "assessment_create" in names
    assert "assessment_refresh" in names
    assert "assessment_synthesis_work_order" in names
    assert "assessment_synthesis_candidate_build" in names
    assert "assessment_execute_next" in names
    assert "assessment_recover_interrupted" in names
    assert "assessment_candidates" in names
    assert "implementation_records" in names
    assert "gate_grant" not in names
    assert "engagement_import" not in names


def test_mcp_http_defaults_to_loopback_and_stable_port() -> None:
    args = build_parser().parse_args(["--transport", "streamable-http"])

    _validate_server_args(args)

    assert args.host == "127.0.0.1"
    assert args.port == 8765
    assert args.allow_execution is False
    assert args.implementation_root == ".hardware-pentest/implementations"
    assert args.generated_project_root == ".hardware-pentest/generated"
    assert args.ufbt_executable == "ufbt"
    assert args.synthesis_build_timeout_seconds == 120.0


def test_mcp_refuses_public_network_binding_without_secure_gateway() -> None:
    args = build_parser().parse_args(
        ["--transport", "streamable-http", "--host", "0.0.0.0"]
    )

    with pytest.raises(SystemExit, match="Non-loopback MCP binding is disabled"):
        _validate_server_args(args)


def test_http_execution_requires_second_environment_opt_in(monkeypatch) -> None:
    args = build_parser().parse_args(
        ["--transport", "streamable-http", "--allow-execution"]
    )
    monkeypatch.delenv("HPA_MCP_REMOTE_EXECUTION", raising=False)

    with pytest.raises(SystemExit, match="HPA_MCP_REMOTE_EXECUTION=1"):
        _validate_server_args(args)

    monkeypatch.setenv("HPA_MCP_REMOTE_EXECUTION", "1")
    _validate_server_args(args)


@pytest.mark.parametrize("port", [0, 65536])
def test_mcp_rejects_invalid_port(port: int) -> None:
    args = build_parser().parse_args(["--transport", "streamable-http", "--port", str(port)])

    with pytest.raises(SystemExit, match="--port"):
        _validate_server_args(args)
