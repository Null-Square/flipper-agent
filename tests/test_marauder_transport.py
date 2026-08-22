from __future__ import annotations

from typing import Any

import pytest

from hardware_pentest.adapters.marauder.errors import MarauderIdentityError, MarauderProtocolError
from hardware_pentest.adapters.marauder.transport import (
    DEFAULT_BAUDRATE,
    MarauderSerialTransport,
    parse_access_points,
    parse_firmware_version,
)


class MarauderFakeSerial:
    def __init__(
        self,
        *,
        banner: bool = True,
        valid_help: bool = True,
        access_points: tuple[str, ...] = (
            "[0][CH:1] Lab AP -44",
            "[1][CH:11] Guest WiFi -71 (selected)",
        ),
        stations: tuple[str, ...] = ("[0] AA:BB:CC:DD:EE:FF -> AP 0 -55",),
        stream_lines: dict[str, tuple[str, ...]] | None = None,
        instances: list[MarauderFakeSerial] | None = None,
        **kwargs: Any,
    ) -> None:
        self.kwargs = kwargs
        self.valid_help = valid_help
        self.access_points = access_points
        self.stations = stations
        self.stream_lines = stream_lines or {}
        self.is_open = True
        self.writes: list[bytes] = []
        self._buffer = bytearray()
        self._pending_stream = b""
        if banner:
            self._buffer.extend(
                b"ESP-IDF version is: v5.5\r\n"
                b"--------------------------------\r\n"
                b"         ESP32 Marauder\r\n"
                b"            v1.12.1\r\n"
                b"--------------------------------\r\n\r\n> "
            )
        if instances is not None:
            instances.append(self)

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
        self.writes.append(data)
        command = data.decode("ascii", errors="ignore").rstrip("\n")
        if command == "help":
            body = (
                "============ Commands ============\r\n"
                "scanall\r\nsniffraw\r\nsniffbeacon\r\nsniffprobe\r\n"
                "sniffdeauth\r\nsniffpmkid [-c <channel>][-d][-l]\r\n"
                "sniffsae\r\npacketcount\r\nstopscan [-f]\r\nlist -a\r\n"
                if self.valid_help
                else "generic console help\r\n"
            )
            self._respond(command, body)
        elif command in {"clearlist -a", "clearlist -c", "clearlist -s"}:
            self._respond(command, "0 selected")
        elif command in {
            "scanall",
            "sniffraw",
            "sniffbeacon",
            "sniffprobe",
            "sniffdeauth",
            "sniffpmkid",
            "sniffsae",
            "packetcount",
        } or command.startswith("sniffpmkid -c "):
            self._respond(command, f"Starting {command}. Stop with stopscan")
            lines = self.stream_lines.get(command, ())
            if lines:
                self._pending_stream = ("\r\n".join(lines) + "\r\n").encode()
        elif command == "stopscan":
            self._respond(command, "Stopping WiFi tran/recv")
        elif command == "list -a":
            self._respond(command, "\r\n".join(self.access_points))
        elif command == "list -c":
            self._respond(command, "\r\n".join(self.stations))
        elif command == "list -p":
            self._respond(command, "[0] Lab-Probe")
        return len(data)

    def _respond(self, command: str, body: str) -> None:
        self._buffer.extend(f"#{command}\r\n{body}\r\n> ".encode())

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self._buffer.clear()


def factory(**configuration: Any):
    def build(**kwargs: Any) -> MarauderFakeSerial:
        return MarauderFakeSerial(**configuration, **kwargs)

    return build


def test_probe_uses_current_marauder_help_signature_and_parses_boot_version() -> None:
    instances: list[MarauderFakeSerial] = []
    with MarauderSerialTransport(
        "/dev/fake",
        serial_factory=factory(instances=instances),
        boot_timeout=0.01,
        command_timeout=0.05,
    ) as transport:
        info = transport.probe()

    assert info.firmware_version == "v1.12.1"
    assert "ESP32 Marauder" in info.banner
    assert "sniffbeacon" in info.help_text
    assert instances[0].kwargs["baudrate"] == DEFAULT_BAUDRATE
    assert instances[0].writes == [b"help\n"]


def test_probe_can_identify_cli_without_boot_banner_but_version_is_unknown() -> None:
    with MarauderSerialTransport(
        "/dev/fake",
        serial_factory=factory(banner=False),
        boot_timeout=0.01,
        command_timeout=0.05,
    ) as transport:
        info = transport.probe()

    assert info.firmware_version is None
    assert "list -a" in info.help_text


def test_probe_rejects_non_marauder_console() -> None:
    with MarauderSerialTransport(
        "/dev/fake",
        serial_factory=factory(valid_help=False),
        boot_timeout=0.01,
        command_timeout=0.05,
    ) as transport:
        with pytest.raises(MarauderIdentityError, match="expected ESP32 Marauder CLI"):
            transport.probe()


def test_passive_beacon_capture_uses_only_bounded_safe_command_sequence() -> None:
    instances: list[MarauderFakeSerial] = []
    with MarauderSerialTransport(
        "/dev/fake",
        serial_factory=factory(instances=instances),
        boot_timeout=0.01,
        command_timeout=0.05,
    ) as transport:
        transport.probe()
        capture = transport.observe_beacons(0.05)

    assert [item.ssid for item in capture.access_points] == ["Lab AP", "Guest WiFi"]
    assert capture.access_points[0].channel == 1
    assert capture.access_points[0].rssi_dbm == -44
    assert capture.access_points[1].selected is True
    assert instances[0].writes == [
        b"help\n",
        b"clearlist -a\n",
        b"sniffbeacon\n",
        b"stopscan\n",
        b"list -a\n",
    ]
    assert not any(b"attack" in write for write in instances[0].writes)


def test_environment_scan_clears_and_returns_ap_and_station_snapshots() -> None:
    instances: list[MarauderFakeSerial] = []
    with MarauderSerialTransport(
        "/dev/fake",
        serial_factory=factory(instances=instances),
        boot_timeout=0.01,
        command_timeout=0.05,
    ) as transport:
        transport.probe()
        capture = transport.scan_environment(0.05)

    assert [item.ssid for item in capture.access_points] == ["Lab AP", "Guest WiFi"]
    assert "AA:BB:CC:DD:EE:FF" in capture.station_list_output
    assert instances[0].writes == [
        b"help\n",
        b"clearlist -a\n",
        b"clearlist -c\n",
        b"scanall\n",
        b"stopscan\n",
        b"list -a\n",
        b"list -c\n",
    ]


@pytest.mark.parametrize(
    ("method_name", "expected_command"),
    [
        ("observe_raw_frames", b"sniffraw\n"),
        ("observe_probe_requests", b"sniffprobe\n"),
        ("observe_deauth_frames", b"sniffdeauth\n"),
        ("observe_sae", b"sniffsae\n"),
        ("observe_packet_activity", b"packetcount\n"),
    ],
)
def test_passive_observation_methods_use_fixed_commands(method_name, expected_command) -> None:
    instances: list[MarauderFakeSerial] = []
    with MarauderSerialTransport(
        "/dev/fake",
        serial_factory=factory(
            instances=instances,
            stream_lines={expected_command.decode().strip(): ("observed frame",)},
        ),
        boot_timeout=0.01,
        command_timeout=0.05,
    ) as transport:
        transport.probe()
        capture = getattr(transport, method_name)(0.05)

    assert expected_command in instances[0].writes
    assert b"stopscan\n" in instances[0].writes
    assert "observed frame" in capture.stream_output
    assert not any(b"attack" in write for write in instances[0].writes)


def test_pmkid_observation_never_generates_active_deauthentication_flag() -> None:
    instances: list[MarauderFakeSerial] = []
    with MarauderSerialTransport(
        "/dev/fake",
        serial_factory=factory(
            instances=instances,
            stream_lines={"sniffpmkid -c 6": ("EAPOL observed",)},
        ),
        boot_timeout=0.01,
        command_timeout=0.05,
    ) as transport:
        transport.probe()
        capture = transport.observe_pmkid(0.05, channel=6)

    assert b"sniffpmkid -c 6\n" in instances[0].writes
    assert "EAPOL observed" in capture.stream_output
    assert not any(b" -d" in write for write in instances[0].writes)
    assert not any(b"attack" in write for write in instances[0].writes)


def test_pmkid_channel_is_hard_bounded() -> None:
    with MarauderSerialTransport(
        "/dev/fake",
        serial_factory=factory(),
        boot_timeout=0.01,
        command_timeout=0.05,
    ) as transport:
        with pytest.raises(MarauderProtocolError, match="channel"):
            transport.observe_pmkid(0.05, channel=0)


def test_access_point_parser_preserves_spaces_and_uses_last_integer_as_rssi() -> None:
    parsed = parse_access_points(
        "[7][CH:6] Camera Lab 2 -63\n"
        "[8][CH:36] 5G Network 2026 -51 (selected)\n"
        "2 selected"
    )

    assert [(item.ssid, item.rssi_dbm) for item in parsed] == [
        ("Camera Lab 2", -63),
        ("5G Network 2026", -51),
    ]


def test_firmware_parser_requires_marauder_banner() -> None:
    assert parse_firmware_version("ESP32 Marauder\r\n v1.2.3\r\n") == "v1.2.3"
    assert parse_firmware_version("some firmware v1.2.3") is None


def test_capture_duration_is_hard_bounded_for_all_observations() -> None:
    with MarauderSerialTransport(
        "/dev/fake",
        serial_factory=factory(),
        boot_timeout=0.01,
        command_timeout=0.05,
    ) as transport:
        with pytest.raises(MarauderProtocolError, match="between"):
            transport.observe_beacons(31.0)
        with pytest.raises(MarauderProtocolError, match="between"):
            transport.observe_raw_frames(31.0)
