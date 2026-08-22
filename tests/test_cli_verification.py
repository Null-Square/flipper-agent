from __future__ import annotations

import pytest

from hardware_pentest.interfaces.cli import build_parser


def test_infrared_verification_cli_requires_named_procedure_and_expectation() -> None:
    args = build_parser().parse_args(
        [
            "flipper-verify",
            "--port",
            "/dev/fake",
            "infrared",
            "--expected-protocol",
            "NEC",
            "--confirm-known-source",
        ]
    )

    assert args.command == "flipper-verify"
    assert args.verification_procedure == "infrared"
    assert args.expected_protocol == "NEC"
    assert args.confirm_known_source is True


def test_subghz_verification_cli_exposes_only_receive_context() -> None:
    args = build_parser().parse_args(
        [
            "flipper-verify",
            "subghz",
            "--expected-protocol",
            "Princeton",
            "--frequency-hz",
            "433920000",
            "--confirm-known-source",
        ]
    )

    assert args.verification_procedure == "subghz"
    assert args.frequency_hz == 433_920_000
    assert not hasattr(args, "transmit")
    assert not hasattr(args, "payload")


def test_gpio_verification_cli_requires_known_binary_level() -> None:
    args = build_parser().parse_args(
        [
            "flipper-verify",
            "gpio",
            "--pin",
            "PA7",
            "--expected-level",
            "1",
            "--confirm-setup",
        ]
    )

    assert args.verification_procedure == "gpio"
    assert args.expected_level == 1
    assert args.confirm_setup is True


def test_gpio_cli_rejects_non_binary_expected_level() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "flipper-verify",
                "gpio",
                "--pin",
                "PA7",
                "--expected-level",
                "2",
                "--confirm-setup",
            ]
        )


def test_verification_cli_has_no_generic_pass_or_capability_override() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "flipper-verify",
                "infrared",
                "--expected-protocol",
                "NEC",
                "--confirm-known-source",
                "--passed",
                "true",
            ]
        )

    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "flipper-verify",
                "--capability-id",
                "infrared.observe",
                "infrared",
                "--expected-protocol",
                "NEC",
                "--confirm-known-source",
            ]
        )
