from __future__ import annotations

from typing import Any

import pytest

from hardware_pentest.adapters.marauder import MARAUDER_WIFI_BEACONS_OBSERVE
from hardware_pentest.adapters.marauder.verification_procedures import MarauderCapabilityVerifier
from hardware_pentest.verification import LocalVerificationStore


class VerificationFakeSerial:
    def __init__(
        self,
        *,
        banner: bool = True,
        access_points: tuple[str, ...] = ("[0][CH:6] NULLSQUARE-HIL-AP -40",),
        **kwargs: Any,
    ) -> None:
        self.is_open = True
        self.access_points = access_points
        self._buffer = bytearray()
        if banner:
            self._buffer.extend(b"ESP32 Marauder\r\n            v1.12.1\r\n> ")

    @property
    def in_waiting(self) -> int:
        return len(self._buffer)

    def read(self, size: int = 1) -> bytes:
        if not self._buffer:
            return b""
        chunk = bytes(self._buffer[:size])
        del self._buffer[:size]
        return chunk

    def write(self, data: bytes) -> int:
        command = data.decode("ascii").rstrip("\n")
        if command == "help":
            self._respond(command, "sniffbeacon\r\nstopscan [-f]\r\nlist -a")
        elif command == "clearlist -a":
            self._respond(command, "0 selected")
        elif command == "sniffbeacon":
            self._respond(command, "StartingBeacon sniff. Stop with stopscan")
        elif command == "stopscan":
            self._respond(command, "Stopping WiFi tran/recv")
        elif command == "list -a":
            self._respond(command, "\r\n".join(self.access_points))
        return len(data)

    def _respond(self, command: str, body: str) -> None:
        self._buffer.extend(f"#{command}\r\n{body}\r\n> ".encode())

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self._buffer.clear()


def factory(
    *,
    banner: bool = True,
    access_points: tuple[str, ...] = ("[0][CH:6] NULLSQUARE-HIL-AP -40",),
):
    def build(**kwargs: Any) -> VerificationFakeSerial:
        return VerificationFakeSerial(banner=banner, access_points=access_points, **kwargs)

    return build


def test_known_ap_verification_creates_pass_record_and_enables_capability(tmp_path) -> None:
    store = LocalVerificationStore(tmp_path / "verification")
    verifier = MarauderCapabilityVerifier(
        "/dev/fake",
        serial_number="BOARD123",
        serial_factory=factory(),
        store=store,
    )

    record = verifier.verify_beacon_observation(
        expected_ssid="NULLSQUARE-HIL-AP",
        expected_channel=6,
        known_ap_confirmed=True,
        duration_seconds=0.05,
    )

    assert record.passed is True
    assert record.capability_id == MARAUDER_WIFI_BEACONS_OBSERVE
    assert store.evidence_is_intact(record) is True
    assert store.verified_capabilities(
        identity=_identity_from_record(record),
        implemented_capabilities={MARAUDER_WIFI_BEACONS_OBSERVE},
    ) == frozenset({MARAUDER_WIFI_BEACONS_OBSERVE})


def test_wrong_expected_ap_creates_failed_record(tmp_path) -> None:
    store = LocalVerificationStore(tmp_path / "verification")
    verifier = MarauderCapabilityVerifier(
        "/dev/fake",
        serial_number="BOARD123",
        serial_factory=factory(),
        store=store,
    )

    record = verifier.verify_beacon_observation(
        expected_ssid="NOT-HERE",
        known_ap_confirmed=True,
        duration_seconds=0.05,
    )

    assert record.passed is False
    assert any(
        check.check_id == "expected_lab_ap_observed" and not check.passed
        for check in record.checks
    )


def test_verification_requires_explicit_known_ap_confirmation(tmp_path) -> None:
    verifier = MarauderCapabilityVerifier(
        "/dev/fake",
        serial_factory=factory(),
        store=LocalVerificationStore(tmp_path / "verification"),
    )

    with pytest.raises(ValueError, match="explicit confirmation"):
        verifier.verify_beacon_observation(
            expected_ssid="NULLSQUARE-HIL-AP",
            known_ap_confirmed=False,
            duration_seconds=0.05,
        )


def test_unknown_firmware_cannot_create_verification_record(tmp_path) -> None:
    verifier = MarauderCapabilityVerifier(
        "/dev/fake",
        serial_factory=factory(banner=False),
        store=LocalVerificationStore(tmp_path / "verification"),
    )

    with pytest.raises(ValueError, match="firmware version is unknown"):
        verifier.verify_beacon_observation(
            expected_ssid="NULLSQUARE-HIL-AP",
            known_ap_confirmed=True,
            duration_seconds=0.05,
        )


def _identity_from_record(record):
    from hardware_pentest.core.models import InstrumentIdentity

    return InstrumentIdentity(
        instrument_id=record.instrument_id,
        kind=record.instrument_kind,
        model=record.instrument_model,
        transport="usb-serial",
        firmware_version=record.firmware_version,
        adapter_version=record.adapter_version,
    )
