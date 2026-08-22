from __future__ import annotations

from typing import Any

import pytest

from hardware_pentest.adapters.marauder.errors import MarauderProtocolError
from hardware_pentest.adapters.marauder.transport import MarauderSerialTransport


class NetworkFakeSerial:
    def __init__(
        self,
        *,
        join_success: bool = True,
        instances: list[NetworkFakeSerial] | None = None,
        **kwargs: Any,
    ) -> None:
        self.is_open = True
        self.join_success = join_success
        self.writes: list[bytes] = []
        self._buffer = bytearray(b"ESP32 Marauder\r\n            v1.12.1\r\n> ")
        self._pending_stream = b""
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
            self._respond(command, "sniffbeacon\r\nstopscan [-f]\r\nlist -a")
        elif command == "list -a":
            self._respond(command, "[0][CH:6] NULLSQUARE-LAB -40\r\n[1][CH:11] Guest -70")
        elif command.startswith("join -a 0 -p "):
            secret = command.removeprefix("join -a 0 -p ")
            if self.join_success:
                self._respond(
                    command,
                    "Using SSID: NULLSQUARE-LAB Password: "
                    f"{secret}\r\nIP address: 192.168.50.20\r\n"
                    "Gateway: 192.168.50.1\r\nNetmask: 255.255.255.0",
                )
            else:
                self._respond(
                    command,
                    "Using SSID: NULLSQUARE-LAB Password: "
                    f"{secret}\r\nCould not connect to WiFi network",
                )
        elif command in {"pingscan -serial", "arpscan -serial"}:
            label = "Ping" if command.startswith("ping") else "ARP"
            self._respond(command, f"Starting {label} Scan with...")
            self._pending_stream = b"network observation\r\n"
        elif command.startswith("portscan ") and command.endswith(" -serial"):
            self._respond(command, "Starting Port Scan with...")
            self._pending_stream = b"port observation\r\n"
        elif command == "stopscan":
            self._respond(command, "Stopping WiFi tran/recv")
        elif command == "stopscan -f":
            self._respond(command, "Stopping WiFi tran/recv")
        elif command == "list -i":
            self._respond(command, "[0] 192.168.50.1\r\n[1] 192.168.50.10")
        return len(data)

    def _respond(self, command: str, body: str) -> None:
        self._buffer.extend(f"#{command}\r\n{body}\r\n> ".encode())

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self._buffer.clear()


def factory(*, join_success: bool = True, instances=None):
    def build(**kwargs: Any) -> NetworkFakeSerial:
        return NetworkFakeSerial(
            join_success=join_success,
            instances=instances,
            **kwargs,
        )

    return build


def transport(*, join_success: bool = True, instances=None) -> MarauderSerialTransport:
    return MarauderSerialTransport(
        "/dev/fake",
        serial_factory=factory(join_success=join_success, instances=instances),
        boot_timeout=0.01,
        command_timeout=0.05,
        join_timeout=0.05,
    )


def test_join_uses_existing_ap_index_and_redacts_password_from_result() -> None:
    secret = "LabSecret42!"
    instances: list[NetworkFakeSerial] = []
    with transport(instances=instances) as device:
        device.probe()
        joined = device.join_access_point(0, secret)

    assert joined.ssid == "NULLSQUARE-LAB"
    assert joined.ip_address == "192.168.50.20"
    assert joined.gateway == "192.168.50.1"
    assert joined.netmask == "255.255.255.0"
    assert secret not in joined.output
    assert "<redacted-secret>" in joined.output
    assert f"join -a 0 -p {secret}\n".encode() in instances[0].writes


def test_join_rejects_index_not_present_in_current_ap_list_before_secret_send() -> None:
    instances: list[NetworkFakeSerial] = []
    with transport(instances=instances) as device:
        device.probe()
        with pytest.raises(MarauderProtocolError, match="not present"):
            device.join_access_point(9, "LabSecret42!")

    assert not any(write.startswith(b"join ") for write in instances[0].writes)


def test_join_failure_does_not_include_password_in_exception() -> None:
    secret = "LabSecret42!"
    with transport(join_success=False) as device:
        device.probe()
        with pytest.raises(MarauderProtocolError) as failure:
            device.join_access_point(0, secret)

    assert secret not in str(failure.value)


def test_network_password_whitespace_is_rejected_before_join_command() -> None:
    instances: list[NetworkFakeSerial] = []
    with transport(instances=instances) as device:
        device.probe()
        with pytest.raises(MarauderProtocolError, match="whitespace"):
            device.join_access_point(0, "not supported")

    assert not any(write.startswith(b"join ") for write in instances[0].writes)


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("ping_scan", b"pingscan -serial\n"),
        ("arp_scan", b"arpscan -serial\n"),
    ],
)
def test_network_discovery_uses_bounded_fixed_commands(method, expected) -> None:
    instances: list[NetworkFakeSerial] = []
    with transport(instances=instances) as device:
        device.probe()
        capture = getattr(device, method)(0.05)

    assert expected in instances[0].writes
    assert b"stopscan\n" in instances[0].writes
    assert [item.address for item in capture.discovered_ips] == [
        "192.168.50.1",
        "192.168.50.10",
    ]


def test_full_port_scan_can_target_only_an_index_from_discovered_ip_list() -> None:
    instances: list[NetworkFakeSerial] = []
    with transport(instances=instances) as device:
        device.probe()
        capture = device.port_scan(0.05, ip_index=1)

    assert capture.operation == "port-scan"
    assert b"portscan -a -t 1 -serial\n" in instances[0].writes


def test_port_scan_rejects_unknown_ip_index_before_scan_command() -> None:
    instances: list[NetworkFakeSerial] = []
    with transport(instances=instances) as device:
        device.probe()
        with pytest.raises(MarauderProtocolError, match="not present"):
            device.port_scan(0.05, ip_index=9)

    assert not any(write.startswith(b"portscan ") for write in instances[0].writes)


def test_service_port_scan_is_allowlisted() -> None:
    instances: list[NetworkFakeSerial] = []
    with transport(instances=instances) as device:
        device.probe()
        device.port_scan(0.05, service="https")
        with pytest.raises(MarauderProtocolError, match="one of"):
            device.port_scan(0.05, service="custom-4444")

    assert b"portscan -s https -serial\n" in instances[0].writes
    assert not any(b"custom-4444" in write for write in instances[0].writes)
