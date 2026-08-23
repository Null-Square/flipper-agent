from __future__ import annotations

import argparse

import pytest

from hardware_pentest.interfaces import operator_cli


class _NonInteractiveInput:
    def isatty(self) -> bool:
        return False


def test_gate_grant_refuses_noninteractive_agent_self_approval(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(operator_cli.sys, "stdin", _NonInteractiveInput())
    args = argparse.Namespace(
        assessment_id="assessment-1",
        step_id="assessment-1:wifi",
        kind="approval",
        ttl_minutes=10.0,
        gate_root=str(tmp_path),
    )

    with pytest.raises(SystemExit, match="interactive operator TTY"):
        operator_cli._grant_gate(args)


def test_operator_parser_exposes_recovery_as_explicit_gate_kind() -> None:
    args = operator_cli.build_parser().parse_args(
        [
            "gate-grant",
            "--assessment-id",
            "assessment-1",
            "--step-id",
            "assessment-1:wifi",
            "--kind",
            "recovery",
        ]
    )

    assert args.kind == "recovery"


def test_implementation_hil_run_refuses_noninteractive_fixture_assertion(
    monkeypatch,
) -> None:
    monkeypatch.setattr(operator_cli.sys, "stdin", _NonInteractiveInput())
    args = argparse.Namespace(
        implementation_id="impl:" + "a" * 64,
        flipper_port=None,
        expected_uart_baud=115200,
        min_sample_bytes=32,
        implementation_root=".hardware-pentest/implementations",
        verification_root=".hardware-pentest/verification",
        evidence_root=".hardware-pentest/hil-evidence",
        procedure_id="adaptive.generated-implementation.execution-hil",
        procedure_version="1",
    )

    with pytest.raises(SystemExit, match="interactive operator TTY"):
        operator_cli._run_implementation_hil(args)


def test_operator_parser_exposes_execution_hil_fixture_expectations() -> None:
    args = operator_cli.build_parser().parse_args(
        [
            "implementation-hil-run",
            "--implementation-id",
            "impl:" + "a" * 64,
            "--expected-uart-baud",
            "115200",
            "--min-sample-bytes",
            "32",
        ]
    )

    assert args.expected_uart_baud == 115200
    assert args.min_sample_bytes == 32
    assert args.evidence_root == ".hardware-pentest/hil-evidence"
