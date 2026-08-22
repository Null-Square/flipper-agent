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
