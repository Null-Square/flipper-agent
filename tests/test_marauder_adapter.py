from __future__ import annotations

from typing import Any

from hardware_pentest.adapters.marauder import (
    MARAUDER_WIFI_BEACONS_OBSERVE,
    MARAUDER_WIFI_DEAUTH_FRAMES_OBSERVE,
    MARAUDER_WIFI_ENVIRONMENT_SCAN,
    MARAUDER_WIFI_PMKID_OBSERVE,
    MarauderAdapter,
)
from hardware_pentest.core.models import Action, ActionClass, ExecutionStatus


class AdapterFakeSerial:
    def __init__(
        self,
        *,
        firmware_version: str = "v1.12.1",
        access_points: tuple[str, ...] = ("[0][CH:6] NULLSQUARE-HIL-AP -42",),
        stream_lines: dict[str, tuple[str, ...]] | None = None,
        instances: list[AdapterFakeSerial] | None = None,
        **kwargs: Any,
    ) -> None:
        self.is_open = True
        self.writes: list[bytes] = []
        self.access_points = access_points
        self.stream_lines = stream_lines or {}
        self._pending_stream = b""
        self._buffer = bytearray(
            (
                "ESP32 Marauder\r\n"
                f"            {firmware_version}\r\n"
                "> "
            ).encode()
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
        command = data.decode("ascii").rstrip("\n")
        if command == "help":
            self._respond(
                command,
                "scanall\r\nsniffraw\r\nsniffbeacon\r\nsniffprobe\r\n"
                "sniffdeauth\r\nsniffpmkid [-c <channel>][-d][-l]\r\n"
                "sniffsae\r\npacketcount\r\nstopscan [-f]\r\nlist -a",
            )
        elif command in {"clearlist -a", "clearlist -c"}:
            self._respond(command, "0 selected")
        elif _is_observation_command(command):
            self._respond(command, f"Starting {command}. Stop with stopscan")
            lines = self.stream_lines.get(command, ())
            if lines:
                self._pending_stream = ("\r\n".join(lines) + "\r\n").encode()
        elif command == "stopscan":
            self._respond(command, "Stopping WiFi tran/recv")
        elif command == "list -a":
            self._respond(command, "\r\n".join(self.access_points))
        elif command == "list -c":
            self._respond(command, "[0] AA:BB:CC:DD:EE:FF -> AP 0 -55")
        elif command == "list -p":
            self._respond(command, "[0] NULLSQUARE-PROBE")
        return len(data)

    def _respond(self, command: str, body: str) -> None:
        self._buffer.extend(f"#{command}\r\n{body}\r\n> ".encode())

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self._buffer.clear()


def _is_observation_command(command: str) -> bool:
    tokens = command.split()
    if not tokens:
        return False
    return tokens[0] in {
        "scanall",
        "sniffraw",
        "sniffbeacon",
        "sniffprobe",
        "sniffdeauth",
        "sniffpmkid",
        "sniffsae",
        "packetcount",
    } and "-serial" in tokens


def factory(
    *,
    firmware_versions: list[str] | None = None,
    access_points: tuple[str, ...] = ("[0][CH:6] NULLSQUARE-HIL-AP -42",),
    stream_lines: dict[str, tuple[str, ...]] | None = None,
    instances: list[AdapterFakeSerial] | None = None,
):
    versions = list(firmware_versions or ["v1.12.1"])

    def build(**kwargs: Any) -> AdapterFakeSerial:
        version = versions.pop(0) if len(versions) > 1 else versions[0]
        return AdapterFakeSerial(
            firmware_version=version,
            access_points=access_points,
            stream_lines=stream_lines,
            instances=instances,
            **kwargs,
        )

    return build


def _action(
    capability_id: str = MARAUDER_WIFI_BEACONS_OBSERVE,
    *,
    action_class: ActionClass = ActionClass.OBSERVE,
    inputs: dict[str, object] | None = None,
) -> Action:
    return Action(
        action_id="wifi-observe",
        capability_id=capability_id,
        target_id="lab-target",
        action_class=action_class,
        inputs=inputs or {"duration_seconds": 0.05},
    )


def test_unverified_capability_is_not_advertised_or_executable() -> None:
    adapter = MarauderAdapter("/dev/fake", serial_factory=factory())

    assert adapter.capabilities() == []
    result = adapter.execute(_action())

    assert result.status is ExecutionStatus.BLOCKED
    assert "not hardware-verified" in (result.error or "")


def test_verified_override_advertises_only_verified_capabilities() -> None:
    adapter = MarauderAdapter(
        "/dev/fake",
        serial_factory=factory(),
        verified_capabilities={MARAUDER_WIFI_BEACONS_OBSERVE},
        allow_verification_override=True,
    )

    capabilities = adapter.capabilities()

    assert [item.capability_id for item in capabilities] == [MARAUDER_WIFI_BEACONS_OBSERVE]
    assert capabilities[0].action_class is ActionClass.OBSERVE
    assert capabilities[0].constraints["receive_only"] is True


def test_pmkid_descriptor_explicitly_disables_active_deauthentication() -> None:
    adapter = MarauderAdapter(
        "/dev/fake",
        serial_factory=factory(),
        verified_capabilities={MARAUDER_WIFI_PMKID_OBSERVE},
        allow_verification_override=True,
    )

    capability = adapter.capabilities()[0]

    assert capability.capability_id == MARAUDER_WIFI_PMKID_OBSERVE
    assert capability.constraints["active_deauthentication"] is False
    assert capability.quality["contains_authentication_material"] is True


def test_successful_beacon_execution_returns_structured_ap_observation() -> None:
    adapter = MarauderAdapter(
        "/dev/fake",
        serial_factory=factory(),
        verified_capabilities={MARAUDER_WIFI_BEACONS_OBSERVE},
        allow_verification_override=True,
    )

    result = adapter.execute(_action())

    assert result.status is ExecutionStatus.SUCCESS
    assert result.normalized["observation_mode"] == "passive-beacon"
    assert result.normalized["access_point_count"] == 1
    assert result.normalized["access_points"][0]["ssid"] == "NULLSQUARE-HIL-AP"


def test_environment_scan_returns_ap_and_station_observation_counts() -> None:
    adapter = MarauderAdapter(
        "/dev/fake",
        serial_factory=factory(),
        verified_capabilities={MARAUDER_WIFI_ENVIRONMENT_SCAN},
        allow_verification_override=True,
    )

    result = adapter.execute(_action(MARAUDER_WIFI_ENVIRONMENT_SCAN))

    assert result.status is ExecutionStatus.SUCCESS
    assert result.normalized["access_point_count"] == 1
    assert result.normalized["station_line_count"] == 1


def test_passive_deauth_observation_records_stream_without_transmitting() -> None:
    instances: list[AdapterFakeSerial] = []
    command = "sniffdeauth -serial"
    adapter = MarauderAdapter(
        "/dev/fake",
        serial_factory=factory(
            stream_lines={command: ("DEAUTH AA:BB:CC:DD:EE:FF",)},
            instances=instances,
        ),
        verified_capabilities={MARAUDER_WIFI_DEAUTH_FRAMES_OBSERVE},
        allow_verification_override=True,
    )

    result = adapter.execute(_action(MARAUDER_WIFI_DEAUTH_FRAMES_OBSERVE))

    assert result.status is ExecutionStatus.SUCCESS
    assert result.normalized["observed_line_count"] == 1
    assert "only observes deauthentication" in " ".join(result.limitations)
    writes = [write for instance in instances for write in instance.writes]
    assert b"sniffdeauth -serial\n" in writes
    assert not any(b"attack" in write for write in writes)


def test_pmkid_observation_accepts_bounded_channel_and_never_uses_dash_d() -> None:
    instances: list[AdapterFakeSerial] = []
    command = "sniffpmkid -c 6 -serial"
    adapter = MarauderAdapter(
        "/dev/fake",
        serial_factory=factory(
            stream_lines={command: ("PMKID material",)},
            instances=instances,
        ),
        verified_capabilities={MARAUDER_WIFI_PMKID_OBSERVE},
        allow_verification_override=True,
    )

    result = adapter.execute(
        _action(
            MARAUDER_WIFI_PMKID_OBSERVE,
            inputs={"duration_seconds": 0.05, "channel": 6},
        )
    )

    assert result.status is ExecutionStatus.SUCCESS
    writes = [write for instance in instances for write in instance.writes]
    assert b"sniffpmkid -c 6 -serial\n" in writes
    assert not any(b" -d" in write for write in writes)


def test_zero_observed_access_points_is_inconclusive_not_success_claim() -> None:
    adapter = MarauderAdapter(
        "/dev/fake",
        serial_factory=factory(access_points=()),
        verified_capabilities={MARAUDER_WIFI_BEACONS_OBSERVE},
        allow_verification_override=True,
    )

    result = adapter.execute(_action())

    assert result.status is ExecutionStatus.INCONCLUSIVE
    assert result.normalized["access_point_count"] == 0


def test_non_observe_action_class_is_rejected() -> None:
    adapter = MarauderAdapter(
        "/dev/fake",
        serial_factory=factory(),
        verified_capabilities={MARAUDER_WIFI_BEACONS_OBSERVE},
        allow_verification_override=True,
    )

    result = adapter.execute(_action(action_class=ActionClass.INTERACT))

    assert result.status is ExecutionStatus.BLOCKED
    assert "must use OBSERVE" in (result.error or "")


def test_unknown_input_key_is_rejected_instead_of_ignored() -> None:
    adapter = MarauderAdapter(
        "/dev/fake",
        serial_factory=factory(),
        verified_capabilities={MARAUDER_WIFI_BEACONS_OBSERVE},
        allow_verification_override=True,
    )

    result = adapter.execute(
        _action(inputs={"duration_seconds": 0.05, "attack": True})
    )

    assert result.status is ExecutionStatus.BLOCKED
    assert "Unsupported input" in (result.error or "")


def test_firmware_change_between_probe_and_execution_fails_closed() -> None:
    adapter = MarauderAdapter(
        "/dev/fake",
        serial_factory=factory(firmware_versions=["v1.12.1", "v1.13.0"]),
        verified_capabilities={MARAUDER_WIFI_BEACONS_OBSERVE},
        allow_verification_override=True,
    )
    adapter.probe()

    result = adapter.execute(_action())

    assert result.status is ExecutionStatus.FAILED
    assert "verified firmware state changed" in (result.error or "")
