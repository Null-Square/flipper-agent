from __future__ import annotations

import pytest

from hardware_pentest.adapters.flipper.errors import (
    FlipperIdentityError,
    FlipperProtocolError,
    FlipperTransportError,
)
from hardware_pentest.adapters.flipper.transport import (
    MAX_RESPONSE_BYTES,
    FlipperSerialTransport,
)
from tests.support.scripted_serial import SerialStep, ScriptedSerial, serial_factory

pytestmark = pytest.mark.contract


def _device_response(*, model: str = "Flipper Zero") -> bytes:
    return (
        b"info device\r\n"
        + f"hardware_model: {model}\r\n".encode()
        + b"hardware_uid: CONTRACT123\r\n"
        + b"firmware_version: 1.4.3\r\n"
        + b">: "
    )


def test_fragmented_serial_delivery_still_parses_identity() -> None:
    device = ScriptedSerial(
        steps=(SerialStep(b"info device\r", _device_response()),),
        initial_bytes=b">: ",
        max_read_size=1,
    )

    with FlipperSerialTransport(
        "/dev/fake",
        serial_factory=serial_factory(device),
    ) as transport:
        info = transport.read_device_info()

    assert info.model == "Flipper Zero"
    assert info.uid == "CONTRACT123"
    assert info.firmware_version == "1.4.3"
    device.assert_complete()


def test_short_serial_write_fails_closed() -> None:
    device = ScriptedSerial(
        steps=(SerialStep(b"info device\r", short_write=True),),
        initial_bytes=b">: ",
    )

    with FlipperSerialTransport(
        "/dev/fake",
        serial_factory=serial_factory(device),
    ) as transport:
        with pytest.raises(FlipperTransportError, match="Short write"):
            transport.read_device_info()


def test_serial_read_error_is_normalized_as_transport_failure() -> None:
    device = ScriptedSerial(
        steps=(SerialStep(b"info device\r", _device_response()),),
        initial_bytes=b">: ",
        read_error_after_writes=1,
    )

    with FlipperSerialTransport(
        "/dev/fake",
        serial_factory=serial_factory(device),
    ) as transport:
        with pytest.raises(FlipperTransportError, match="Read failed"):
            transport.read_device_info()


def test_wrong_device_identity_is_rejected() -> None:
    device = ScriptedSerial(
        steps=(SerialStep(b"info device\r", _device_response(model="Not A Flipper")),),
        initial_bytes=b">: ",
    )

    with FlipperSerialTransport(
        "/dev/fake",
        serial_factory=serial_factory(device),
    ) as transport:
        with pytest.raises(FlipperIdentityError, match="did not identify as Flipper Zero"):
            transport.read_device_info()


def test_malformed_identity_response_is_rejected() -> None:
    response = b"info device\r\nthis is not key value output\r\n>: "
    device = ScriptedSerial(
        steps=(SerialStep(b"info device\r", response),),
        initial_bytes=b">: ",
    )

    with FlipperSerialTransport(
        "/dev/fake",
        serial_factory=serial_factory(device),
    ) as transport:
        with pytest.raises(FlipperProtocolError, match="key/value"):
            transport.read_device_info()


def test_oversized_response_is_rejected_before_prompt_arrives() -> None:
    response = b"info device\r\n" + b"X" * (MAX_RESPONSE_BYTES + 8192) + b">: "
    device = ScriptedSerial(
        steps=(SerialStep(b"info device\r", response),),
        initial_bytes=b">: ",
        max_read_size=4096,
    )

    with FlipperSerialTransport(
        "/dev/fake",
        serial_factory=serial_factory(device),
    ) as transport:
        with pytest.raises(FlipperProtocolError, match="exceeded"):
            transport.read_device_info()
