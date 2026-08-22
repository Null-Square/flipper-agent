from __future__ import annotations

import pytest

from hardware_pentest.adapters.marauder.errors import (
    MarauderIdentityError,
    MarauderProtocolError,
    MarauderTimeoutError,
    MarauderTransportError,
)
from hardware_pentest.adapters.marauder.transport import (
    MAX_RESPONSE_BYTES,
    MarauderSerialTransport,
)
from tests.support.scripted_serial import ScriptedSerial, SerialStep, serial_factory

pytestmark = pytest.mark.contract

_BOOT = (
    b"ESP-IDF version is: v5.5\r\n"
    b"--------------------------------\r\n"
    b"         ESP32 Marauder\r\n"
    b"            v1.12.1\r\n"
    b"--------------------------------\r\n> "
)
_HELP = (
    b"#help\r\n"
    b"scanall\r\nsniffbeacon\r\nstopscan [-f]\r\nlist -a\r\n"
    b"> "
)


def test_fragmented_marauder_boot_and_help_still_probe() -> None:
    device = ScriptedSerial(
        steps=(SerialStep(b"help\n", _HELP),),
        initial_bytes=_BOOT,
        max_read_size=1,
    )

    with MarauderSerialTransport(
        "/dev/fake",
        serial_factory=serial_factory(device),
        boot_timeout=0.1,
        command_timeout=0.1,
    ) as transport:
        info = transport.probe()

    assert info.firmware_version == "v1.12.1"
    assert "ESP32 Marauder" in info.banner
    assert "sniffbeacon" in info.help_text
    device.assert_complete()


def test_marauder_short_write_fails_closed() -> None:
    device = ScriptedSerial(
        steps=(SerialStep(b"help\n", short_write=True),),
        initial_bytes=_BOOT,
    )

    with MarauderSerialTransport(
        "/dev/fake",
        serial_factory=serial_factory(device),
        boot_timeout=0.05,
        command_timeout=0.05,
    ) as transport:
        with pytest.raises(MarauderTransportError, match="write was incomplete"):
            transport.probe()


def test_marauder_read_failure_is_normalized() -> None:
    device = ScriptedSerial(
        steps=(SerialStep(b"help\n", _HELP),),
        initial_bytes=_BOOT,
        read_error_after_writes=1,
    )

    with MarauderSerialTransport(
        "/dev/fake",
        serial_factory=serial_factory(device),
        boot_timeout=0.05,
        command_timeout=0.05,
    ) as transport:
        with pytest.raises(MarauderTransportError, match="read failed"):
            transport.probe()


def test_marauder_help_timeout_is_explicit() -> None:
    device = ScriptedSerial(
        steps=(SerialStep(b"help\n", b""),),
        initial_bytes=_BOOT,
    )

    with MarauderSerialTransport(
        "/dev/fake",
        serial_factory=serial_factory(device),
        boot_timeout=0.02,
        command_timeout=0.01,
    ) as transport:
        with pytest.raises(MarauderTimeoutError, match="command prompt"):
            transport.probe()


def test_marauder_wrong_help_signature_is_not_accepted_as_identity() -> None:
    device = ScriptedSerial(
        steps=(SerialStep(b"help\n", b"#help\r\ngeneric console\r\n> "),),
        initial_bytes=_BOOT,
    )

    with MarauderSerialTransport(
        "/dev/fake",
        serial_factory=serial_factory(device),
        boot_timeout=0.05,
        command_timeout=0.05,
    ) as transport:
        with pytest.raises(MarauderIdentityError, match="expected ESP32 Marauder CLI"):
            transport.probe()


def test_marauder_oversized_response_is_rejected_before_prompt() -> None:
    response = b"#help\r\n" + b"X" * (MAX_RESPONSE_BYTES + 8192) + b"> "
    device = ScriptedSerial(
        steps=(SerialStep(b"help\n", response),),
        initial_bytes=_BOOT,
        max_read_size=4096,
    )

    with MarauderSerialTransport(
        "/dev/fake",
        serial_factory=serial_factory(device),
        boot_timeout=0.05,
        command_timeout=0.2,
    ) as transport:
        with pytest.raises(MarauderProtocolError, match="bounded size limit"):
            transport.probe()
