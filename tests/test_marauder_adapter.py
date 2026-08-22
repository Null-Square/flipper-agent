from __future__ import annotations

from typing import Any

from hardware_pentest.adapters.marauder import (
    MARAUDER_WIFI_BEACONS_OBSERVE,
    MarauderAdapter,
)
from hardware_pentest.core.models import Action, ActionClass, ExecutionStatus


class AdapterFakeSerial:
    def __init__(
        self,
        *,
        firmware_version: str = "v1.12.1",
        access_points: tuple[str, ...] = ("[0][CH:6] NULLSQUARE-HIL-AP -42",),
        instances: list[AdapterFakeSerial] | None = None,
        **kwargs: Any,
    ) -> None:
        self.is_open = True
        self.writes: list[bytes] = []
        self.access_points = access_points
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
    firmware_versions: list[str] | None = None,
    access_points: tuple[str, ...] = ("[0][CH:6] NULLSQUARE-HIL-AP -42",),
    instances: list[AdapterFakeSerial] | None = None,
):
    versions = list(firmware_versions or ["v1.12.1"])

    def build(**kwargs: Any) -> AdapterFakeSerial:
        version = versions.pop(0) if len(versions) > 1 else versions[0]
        return AdapterFakeSerial(
            firmware_version=version,
            access_points=access_points,
            instances=instances,
            **kwargs,
        )

    return build


def _action(*, action_class: ActionClass = ActionClass.OBSERVE) -> Action:
    return Action(
        action_id="wifi-observe",
        capability_id=MARAUDER_WIFI_BEACONS_OBSERVE,
        target_id="lab-target",
        action_class=action_class,
        inputs={"duration_seconds": 0.05},
    )


def test_unverified_capability_is_not_advertised_or_executable() -> None:
    adapter = MarauderAdapter("/dev/fake", serial_factory=factory())

    assert adapter.capabilities() == []
    result = adapter.execute(_action())

    assert result.status is ExecutionStatus.BLOCKED
    assert "not hardware-verified" in (result.error or "")


def test_verified_override_advertises_only_passive_beacon_capability() -> None:
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


def test_successful_execution_returns_structured_ap_observation() -> None:
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
