from __future__ import annotations

import json
from typing import Any

import pytest

from hardware_pentest.adapters.marauder import (
    MARAUDER_WIFI_ARP_DISCOVER,
    MARAUDER_WIFI_BEACONS_OBSERVE,
    MARAUDER_WIFI_ENVIRONMENT_SCAN,
    MARAUDER_WIFI_NETWORK_JOIN,
    MARAUDER_WIFI_PING_DISCOVER,
    MARAUDER_WIFI_PORTS_SCAN,
)
from hardware_pentest.adapters.marauder.verification_procedures import MarauderCapabilityVerifier
from hardware_pentest.verification import LocalVerificationStore


class VerificationBackend:
    def __init__(
        self,
        *,
        access_points: tuple[str, ...] = ("[0][CH:6] NULLSQUARE-HIL-AP -40",),
        discovered_ips: tuple[str, ...] = ("[0] 192.168.50.1", "[1] 192.168.50.10"),
        service_line: str = "192.168.50.10: 443",
    ) -> None:
        self.access_points = access_points
        self.discovered_ips = discovered_ips
        self.service_line = service_line
        self.writes: list[str] = []


class VerificationFakeSerial:
    def __init__(
        self,
        *,
        backend: VerificationBackend,
        banner: bool = True,
        **kwargs: Any,
    ) -> None:
        self.is_open = True
        self.backend = backend
        self._buffer = bytearray()
        self._pending_stream = b""
        if banner:
            self._buffer.extend(b"ESP32 Marauder\r\n            v1.12.1\r\n> ")

    @property
    def in_waiting(self) -> int:
        if not self._buffer and self._pending_stream:
            self._buffer.extend(self._pending_stream)
            self._pending_stream = b""
        return len(self._buffer)

    def read(self, size: int = 1) -> bytes:
        if not self._buffer:
            return b""
        chunk = bytes(self._buffer[:size])
        del self._buffer[:size]
        return chunk

    def write(self, data: bytes) -> int:
        command = data.decode("ascii").rstrip("\n")
        self.backend.writes.append(command)
        if command == "help":
            self._respond(
                command,
                "scanall\r\nsniffbeacon\r\nstopscan [-f]\r\nlist -a\r\nlist -c",
            )
        elif command in {"clearlist -a", "clearlist -c"}:
            self._respond(command, "0 selected")
        elif command in {"scanall -serial", "sniffbeacon -serial"}:
            self._respond(command, f"Starting {command}. Stop with stopscan")
        elif command.startswith("join -a 0 -p "):
            secret = command.removeprefix("join -a 0 -p ")
            self._respond(
                command,
                "Using SSID: NULLSQUARE-HIL-AP Password: "
                f"{secret}\r\nIP address: 192.168.50.20\r\n"
                "Gateway: 192.168.50.1\r\nNetmask: 255.255.255.0",
            )
        elif command == "pingscan -serial":
            self._respond(command, "Starting Ping Scan with...")
            self._pending_stream = b"192.168.50.10\r\n"
        elif command == "arpscan -serial":
            self._respond(command, "Starting ARP Scan with...")
            self._pending_stream = b"192.168.50.10\r\n"
        elif command.startswith("portscan -s ") and command.endswith(" -serial"):
            self._respond(command, "Starting Port Scan with...")
            self._pending_stream = (self.backend.service_line + "\r\n").encode()
        elif command == "stopscan":
            self._respond(command, "Stopping WiFi tran/recv")
        elif command == "stopscan -f":
            self._respond(command, "Stopping WiFi tran/recv")
        elif command == "list -a":
            self._respond(command, "\r\n".join(self.backend.access_points))
        elif command == "list -c":
            self._respond(command, "[0] AA:BB:CC:DD:EE:FF -> AP 0 -50")
        elif command == "list -i":
            self._respond(command, "\r\n".join(self.backend.discovered_ips))
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
    backend: VerificationBackend | None = None,
):
    backend = backend or VerificationBackend()

    def build(**kwargs: Any) -> VerificationFakeSerial:
        return VerificationFakeSerial(backend=backend, banner=banner, **kwargs)

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


def test_environment_scan_can_be_verified_against_same_known_ap(tmp_path) -> None:
    store = LocalVerificationStore(tmp_path / "verification")
    verifier = MarauderCapabilityVerifier(
        "/dev/fake",
        serial_number="BOARD123",
        serial_factory=factory(),
        store=store,
    )

    record = verifier.verify_environment_scan(
        expected_ssid="NULLSQUARE-HIL-AP",
        expected_channel=6,
        known_ap_confirmed=True,
        duration_seconds=0.05,
    )

    assert record.passed is True
    assert record.capability_id == MARAUDER_WIFI_ENVIRONMENT_SCAN
    assert store.evidence_is_intact(record) is True


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


def test_preflight_firmware_hint_allows_same_board_reconnect_verification(tmp_path) -> None:
    verifier = MarauderCapabilityVerifier(
        "/dev/fake",
        serial_number="BOARD123",
        serial_factory=factory(banner=False),
        firmware_version_hint="v1.12.1",
        store=LocalVerificationStore(tmp_path / "verification"),
    )

    record = verifier.verify_beacon_observation(
        expected_ssid="NULLSQUARE-HIL-AP",
        known_ap_confirmed=True,
        duration_seconds=0.05,
    )

    assert record.firmware_version == "v1.12.1"


def test_network_profile_verifies_join_ping_and_arp_without_persisting_secret(
    tmp_path,
    monkeypatch,
) -> None:
    secret = "NetworkSecret42!"
    monkeypatch.setenv("HPA_LAB_WIFI_PASSWORD", secret)
    backend = VerificationBackend()
    store = LocalVerificationStore(tmp_path / "verification")
    verifier = MarauderCapabilityVerifier(
        "/dev/fake",
        serial_number="BOARD123",
        serial_factory=factory(backend=backend),
        store=store,
    )

    records = verifier.verify_network_profile(
        expected_ssid="NULLSQUARE-HIL-AP",
        password_env="HPA_LAB_WIFI_PASSWORD",
        expected_host_ip="192.168.50.10",
        network_transmit_confirmed=True,
        duration_seconds=0.05,
    )

    assert {record.capability_id for record in records} == {
        MARAUDER_WIFI_NETWORK_JOIN,
        MARAUDER_WIFI_PING_DISCOVER,
        MARAUDER_WIFI_ARP_DISCOVER,
    }
    assert all(record.passed for record in records)
    assert all(store.evidence_is_intact(record) for record in records)
    evidence_text = "\n".join(
        (store.root / record.evidence_reference).read_text(encoding="utf-8")
        for record in records
    )
    assert secret not in evidence_text
    assert "HPA_LAB_WIFI_PASSWORD" in evidence_text
    assert any(command.startswith("join -a 0 -p ") for command in backend.writes)
    assert "pingscan -serial" in backend.writes
    assert "arpscan -serial" in backend.writes
    assert "stopscan -f" in backend.writes


def test_network_profile_can_verify_allowlisted_controlled_service(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HPA_LAB_WIFI_PASSWORD", "NetworkSecret42!")
    backend = VerificationBackend(service_line="192.168.50.10: 443")
    verifier = MarauderCapabilityVerifier(
        "/dev/fake",
        serial_number="BOARD123",
        serial_factory=factory(backend=backend),
        store=LocalVerificationStore(tmp_path / "verification"),
    )

    records = verifier.verify_network_profile(
        expected_ssid="NULLSQUARE-HIL-AP",
        password_env="HPA_LAB_WIFI_PASSWORD",
        expected_host_ip="192.168.50.10",
        expected_service="https",
        network_transmit_confirmed=True,
        duration_seconds=0.05,
    )

    assert len(records) == 4
    port_record = next(record for record in records if record.capability_id == MARAUDER_WIFI_PORTS_SCAN)
    assert port_record.passed is True
    assert "portscan -s https -serial" in backend.writes


def test_network_profile_requires_explicit_transmit_confirmation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HPA_LAB_WIFI_PASSWORD", "NetworkSecret42!")
    verifier = MarauderCapabilityVerifier(
        "/dev/fake",
        serial_factory=factory(),
        store=LocalVerificationStore(tmp_path / "verification"),
    )

    with pytest.raises(ValueError, match="authorized transmission"):
        verifier.verify_network_profile(
            expected_ssid="NULLSQUARE-HIL-AP",
            password_env="HPA_LAB_WIFI_PASSWORD",
            expected_host_ip="192.168.50.10",
            network_transmit_confirmed=False,
            duration_seconds=0.05,
        )


def test_failed_known_host_does_not_verify_discovery_capabilities(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HPA_LAB_WIFI_PASSWORD", "NetworkSecret42!")
    backend = VerificationBackend(discovered_ips=("[0] 192.168.50.1",))
    verifier = MarauderCapabilityVerifier(
        "/dev/fake",
        serial_number="BOARD123",
        serial_factory=factory(backend=backend),
        store=LocalVerificationStore(tmp_path / "verification"),
    )

    records = verifier.verify_network_profile(
        expected_ssid="NULLSQUARE-HIL-AP",
        password_env="HPA_LAB_WIFI_PASSWORD",
        expected_host_ip="192.168.50.10",
        network_transmit_confirmed=True,
        duration_seconds=0.05,
    )

    ping = next(record for record in records if record.capability_id == MARAUDER_WIFI_PING_DISCOVER)
    arp = next(record for record in records if record.capability_id == MARAUDER_WIFI_ARP_DISCOVER)
    assert ping.passed is False
    assert arp.passed is False


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
