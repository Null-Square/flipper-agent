from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from hardware_pentest.adapters.flipper.verification import verify_flipper_transport
from hardware_pentest.core.models import InstrumentIdentity


def _identity(instrument_id: str = "flipper:ABC") -> InstrumentIdentity:
    return InstrumentIdentity(
        instrument_id=instrument_id,
        kind="flipper-zero",
        model="Flipper Zero",
        transport="usb-cli",
        firmware_version="1.4.3",
        adapter_version="0.1.0-dev",
    )


def _adapter_factory(identities: list[InstrumentIdentity]):
    iterator: Iterator[InstrumentIdentity] = iter(identities)

    class FakeAdapter:
        def __init__(self, port: str, **kwargs: Any) -> None:
            self.port = port
            self.kwargs = kwargs
            self.identity = next(iterator)

        def probe(self) -> InstrumentIdentity:
            return self.identity

    return FakeAdapter


def test_transport_verification_passes_for_stable_identity() -> None:
    report = verify_flipper_transport(
        "/dev/fake",
        adapter_factory=_adapter_factory([_identity(), _identity()]),
    )

    assert report.passed is True
    assert all(check.passed for check in report.checks)
    assert report.to_dict()["first_identity"]["instrument_id"] == "flipper:ABC"


def test_transport_verification_fails_when_identity_changes() -> None:
    report = verify_flipper_transport(
        "/dev/fake",
        adapter_factory=_adapter_factory([_identity("flipper:A"), _identity("flipper:B")]),
    )

    checks = {check.check_id: check for check in report.checks}
    assert report.passed is False
    assert checks["stable_instrument_id"].passed is False
