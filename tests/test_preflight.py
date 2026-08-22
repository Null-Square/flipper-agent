from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from hardware_pentest.adapters.flipper.apps import MARAUDER_APP
from hardware_pentest.preflight import (
    FlipperMarauderCompositeState,
    FlipperMarauderPreflight,
    PreflightStatus,
    TranscriptRecorder,
)
from hardware_pentest.verification import LocalVerificationStore


class FlipperBackend:
    def __init__(self, *, installed: bool = True) -> None:
        self.installed = installed
        self.running_app: str | None = None


class FlipperFakeSerial:
    def __init__(self, backend: FlipperBackend, **kwargs: Any) -> None:
        self.backend = backend
        self.is_open = True
        self._buffer = bytearray(b">: ")

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
        command = data.decode("ascii", errors="ignore").rstrip("\r")
        if command == "info device":
            self._respond(
                command,
                "hardware_model: Flipper Zero\r\n"
                "hardware_uid: FLIPPER123\r\n"
                "firmware_version: 1.4.3",
            )
        elif command == f"storage stat {MARAUDER_APP.path}":
            body = (
                "Type: File\r\nSize: 42000"
                if self.backend.installed
                else "Storage error: Not exist"
            )
            self._respond(command, body)
        elif command == f"storage md5 {MARAUDER_APP.path}":
            self._respond(command, "0123456789abcdef0123456789abcdef")
        elif command == f'loader open "{MARAUDER_APP.path}"':
            self.backend.running_app = MARAUDER_APP.display_name
            self._respond(command, "")
        elif command == "loader info":
            body = (
                f'Application "{self.backend.running_app}" is running'
                if self.backend.running_app
                else "No application is running"
            )
            self._respond(command, body)
        elif command == "loader close":
            old = self.backend.running_app
            self.backend.running_app = None
            body = f'Application "{old}" was closed' if old else "No application is running"
            self._respond(command, body)
        elif data == b"\r":
            self._buffer.extend(b">: ")
        return len(data)

    def _respond(self, command: str, body: str) -> None:
        payload = command + "\r\n"
        if body:
            payload += body + "\r\n"
        payload += ">: "
        self._buffer.extend(payload.encode())

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self._buffer.clear()


class MarauderBackend:
    def __init__(
        self,
        *,
        firmware_version: str | None = "v1.12.1",
        aps: tuple[str, ...] = ("[0][CH:6] NULLSQUARE-HIL-AP -41",),
    ) -> None:
        self.firmware_version = firmware_version
        self.aps = aps


class MarauderFakeSerial:
    def __init__(self, backend: MarauderBackend, **kwargs: Any) -> None:
        self.backend = backend
        self.is_open = True
        self._buffer = bytearray()
        if backend.firmware_version:
            self._buffer.extend(
                (
                    "ESP32 Marauder\r\n"
                    f"            {backend.firmware_version}\r\n"
                    "> "
                ).encode()
            )

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
            self._respond(command, "\r\n".join(self.backend.aps))
        return len(data)

    def _respond(self, command: str, body: str) -> None:
        self._buffer.extend(f"#{command}\r\n{body}\r\n> ".encode())

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self._buffer.clear()


def flipper_factory(backend: FlipperBackend):
    def build(**kwargs: Any) -> FlipperFakeSerial:
        return FlipperFakeSerial(backend, **kwargs)

    return build


def marauder_factory(backend: MarauderBackend):
    def build(**kwargs: Any) -> MarauderFakeSerial:
        return MarauderFakeSerial(backend, **kwargs)

    return build


def make_preflight(
    tmp_path,
    *,
    flipper_backend: FlipperBackend | None = None,
    marauder_backend: MarauderBackend | None = None,
    marauder_serial_number: str | None = "BOARD123",
) -> FlipperMarauderPreflight:
    flipper_backend = flipper_backend or FlipperBackend()
    marauder_backend = marauder_backend or MarauderBackend()
    return FlipperMarauderPreflight(
        flipper_port="/dev/flipper",
        flipper_serial_number="USB-FLIPPER-123",
        marauder_port="/dev/marauder",
        marauder_serial_number=marauder_serial_number,
        flipper_serial_factory=flipper_factory(flipper_backend),
        marauder_serial_factory=marauder_factory(marauder_backend),
        verification_store=LocalVerificationStore(tmp_path / "verification"),
    )


def test_full_known_lab_preflight_is_ready_and_builds_composite_identity(tmp_path) -> None:
    report = make_preflight(tmp_path).run(
        beacon_duration_seconds=0.05,
        expected_lab_ssid="NULLSQUARE-HIL-AP",
        expected_lab_channel=6,
    )

    assert report.ready is True
    assert report.has_warnings is False
    assert report.composite_identity is not None
    assert report.composite_identity.kind == "flipper-marauder-composite"
    assert all(check.status is PreflightStatus.PASS for check in report.checks)


def test_missing_marauder_fap_blocks_readiness(tmp_path) -> None:
    report = make_preflight(tmp_path, flipper_backend=FlipperBackend(installed=False)).run(
        beacon_duration_seconds=0.05,
        expected_lab_ssid="NULLSQUARE-HIL-AP",
    )

    assert report.ready is False
    fap = next(check for check in report.checks if check.check_id == "flipper.marauder_fap")
    assert fap.status is PreflightStatus.FAIL
    assert report.composite_identity is None


def test_unknown_marauder_firmware_blocks_readiness(tmp_path) -> None:
    report = make_preflight(
        tmp_path,
        marauder_backend=MarauderBackend(firmware_version=None),
    ).run(beacon_duration_seconds=0.05)

    assert report.ready is False
    firmware = next(check for check in report.checks if check.check_id == "marauder.firmware")
    assert firmware.status is PreflightStatus.FAIL


def test_missing_stable_board_serial_refuses_composite_trust(tmp_path) -> None:
    report = make_preflight(tmp_path, marauder_serial_number=None).run(
        beacon_duration_seconds=0.05,
        expected_lab_ssid="NULLSQUARE-HIL-AP",
    )

    assert report.ready is False
    stable = next(
        check for check in report.checks if check.check_id == "composite.stable_board_identity"
    )
    assert stable.status is PreflightStatus.FAIL
    assert report.composite_identity is None


def test_missing_known_hil_ap_blocks_deterministic_preflight(tmp_path) -> None:
    report = make_preflight(
        tmp_path,
        marauder_backend=MarauderBackend(aps=("[0][CH:1] OTHER -60",)),
    ).run(
        beacon_duration_seconds=0.05,
        expected_lab_ssid="NULLSQUARE-HIL-AP",
        expected_lab_channel=6,
    )

    assert report.ready is False
    hil = next(check for check in report.checks if check.check_id == "marauder.known_lab_ap")
    assert hil.status is PreflightStatus.FAIL


def test_no_known_ap_expectation_is_ready_with_warning(tmp_path) -> None:
    report = make_preflight(tmp_path).run(beacon_duration_seconds=0.05)

    assert report.ready is True
    assert report.has_warnings is True


def test_composite_identity_changes_when_any_component_changes() -> None:
    report_identity = make_identity("flipper:ABC", "flipper-zero", "1.4.3", "0.7.0-dev")
    marauder_identity = make_identity("marauder:BOARD", "esp32-marauder", "v1.12.1", "0.1.0-dev")
    state = FlipperMarauderCompositeState(
        flipper=report_identity,
        marauder=marauder_identity,
        marauder_fap_md5="0123456789abcdef0123456789abcdef",
        marauder_fap_version_hint="7.9",
    )

    original = state.instrument_identity().instrument_id
    changed_firmware = replace(
        state,
        marauder=replace(marauder_identity, firmware_version="v1.13.0"),
    )
    changed_fap = replace(state, marauder_fap_md5="fedcba9876543210fedcba9876543210")

    assert changed_firmware.instrument_identity().instrument_id != original
    assert changed_fap.instrument_identity().instrument_id != original


def test_transcript_recorder_redacts_uid_and_mac_even_when_reads_are_split(tmp_path) -> None:
    recorder = TranscriptRecorder()
    stream = ChunkedStream(
        chunks=[
            b"hardware_uid: ABC",
            b"DEF\r\nradio_ble_mac: AA:BB:",
            b"CC:DD:EE:FF\r\n",
        ]
    )
    factory = recorder.recording_factory("flipper", base_factory=lambda **kwargs: stream)
    recorded = factory(port="/dev/ttyACM0")

    recorded.write(b"info device\r")
    while recorded.in_waiting:
        recorded.read(64)
    output = recorder.write(tmp_path / "transcript.json")
    payload = json.loads(output.read_text(encoding="utf-8"))
    text = json.dumps(payload)

    assert "ABCDEF" not in text
    assert "AA:BB:CC:DD:EE:FF" not in text
    assert "<redacted-uid>" in text
    assert "<redacted-mac>" in text


class ChunkedStream:
    def __init__(self, *, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)
        self.is_open = True
        self.writes: list[bytes] = []

    @property
    def in_waiting(self) -> int:
        return len(self.chunks[0]) if self.chunks else 0

    def read(self, size: int = 1) -> bytes:
        if not self.chunks:
            return b""
        return self.chunks.pop(0)

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self.chunks.clear()


def make_identity(instrument_id: str, kind: str, firmware: str, adapter: str):
    from hardware_pentest.core.models import InstrumentIdentity

    return InstrumentIdentity(
        instrument_id=instrument_id,
        kind=kind,
        model=kind,
        transport="usb",
        firmware_version=firmware,
        adapter_version=adapter,
    )
