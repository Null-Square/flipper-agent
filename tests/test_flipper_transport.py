from __future__ import annotations

from typing import Any

import pytest

from hardware_pentest.adapters.flipper.adapter import FlipperAdapter
from hardware_pentest.adapters.flipper.errors import FlipperIdentityError, FlipperTimeoutError
from hardware_pentest.adapters.flipper.transport import (
    FlipperSerialTransport,
    parse_device_info,
)


class FakeSerial:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.is_open = True
        self._buffer = bytearray(b">: ")
        self.writes: list[bytes] = []

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
        if data == b"info device\r":
            self._buffer.extend(
                b"info device\r\n"
                b"hardware_model: Flipper Zero\r\n"
                b"hardware_uid: A1B2C3D4\r\n"
                b"firmware_version: 1.4.3\r\n"
                b">: "
            )
        return len(data)

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self._buffer.clear()


class WrongDeviceSerial(FakeSerial):
    def write(self, data: bytes) -> int:
        self.writes.append(data)
        if data == b"info device\r":
            self._buffer.extend(
                b"info device\r\nhardware_model: Other Device\r\nfirmware_version: 1\r\n>: "
            )
        return len(data)


class SilentSerial(FakeSerial):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._buffer.clear()

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)


def test_parse_device_info_supports_cli_key_shapes() -> None:
    info = parse_device_info(
        "hardware.model: Flipper Zero\r\n"
        "hardware.uid: 1234\r\n"
        "firmware.version: 1.4.3\r\n"
    )
    assert info.model == "Flipper Zero"
    assert info.uid == "1234"
    assert info.firmware_version == "1.4.3"


def test_transport_verifies_identity_and_removes_command_echo() -> None:
    instances: list[FakeSerial] = []

    def factory(**kwargs: Any) -> FakeSerial:
        instance = FakeSerial(**kwargs)
        instances.append(instance)
        return instance

    with FlipperSerialTransport("/dev/fake", serial_factory=factory) as transport:
        info = transport.read_device_info()

    assert info.model == "Flipper Zero"
    assert info.uid == "A1B2C3D4"
    assert info.firmware_version == "1.4.3"
    assert instances[0].writes == [b"info device\r"]
    assert instances[0].is_open is False


def test_transport_rejects_non_flipper_identity() -> None:
    with FlipperSerialTransport(
        "/dev/fake",
        serial_factory=lambda **kwargs: WrongDeviceSerial(**kwargs),
    ) as transport:
        with pytest.raises(FlipperIdentityError):
            transport.read_device_info()


def test_transport_times_out_when_prompt_never_arrives() -> None:
    transport = FlipperSerialTransport(
        "/dev/silent",
        serial_factory=lambda **kwargs: SilentSerial(**kwargs),
        read_timeout=0.001,
        sync_timeout=0.005,
        command_timeout=0.005,
    )
    with pytest.raises(FlipperTimeoutError):
        transport.open()


def test_adapter_probe_builds_stable_identity_and_advertises_no_capabilities() -> None:
    adapter = FlipperAdapter(
        "/dev/fake",
        serial_number="USB-SERIAL",
        serial_factory=lambda **kwargs: FakeSerial(**kwargs),
    )

    identity = adapter.probe()

    assert identity.instrument_id == "flipper:A1B2C3D4"
    assert identity.model == "Flipper Zero"
    assert identity.transport == "usb-cli"
    assert identity.firmware_version == "1.4.3"
    assert adapter.capabilities() == []
