from __future__ import annotations

from typing import Any

from hardware_pentest.adapters.flipper.adapter import SUBGHZ_OBSERVE, FlipperAdapter
from hardware_pentest.adapters.flipper.subghz import (
    DEFAULT_SUBGHZ_FREQUENCY_HZ,
    is_valid_subghz_rx_frequency,
    parse_subghz_capture,
)
from hardware_pentest.adapters.flipper.transport import FlipperSerialTransport
from hardware_pentest.core.models import Action, ActionClass, ExecutionStatus


class SubGhzFakeSerial:
    def __init__(self, *, emit_packet: bool = True, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.emit_packet = emit_packet
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
        elif data == b"subghz rx 433920000 0\r":
            self._buffer.extend(
                b"subghz rx 433920000 0\r\n"
                b"Load_keystore keeloq_mfcodes OK\r\n"
                b"Listening at frequency: 433920000 device: 0. Press CTRL+C to stop\r\n"
            )
            if self.emit_packet:
                self._buffer.extend(
                    b"Protocol: Princeton\r\n"
                    b"Bit: 24\r\n"
                    b"Key: 00 00 00 00 00 74 BA DE\r\n"
                    b"TE: 403\r\n"
                )
        elif data == b"\x03":
            self._buffer.extend(b"\r\n>: ")
        return len(data)

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self._buffer.clear()


def _factory(*, emit_packet: bool = True):
    def factory(**kwargs: Any) -> SubGhzFakeSerial:
        return SubGhzFakeSerial(emit_packet=emit_packet, **kwargs)

    return factory


def test_subghz_frequency_ranges_match_supported_receive_bands() -> None:
    assert is_valid_subghz_rx_frequency(433_920_000) is True
    assert is_valid_subghz_rx_frequency(315_000_000) is True
    assert is_valid_subghz_rx_frequency(868_350_000) is True
    assert is_valid_subghz_rx_frequency(500_000_000) is False


def test_parse_subghz_packet() -> None:
    capture = parse_subghz_capture(
        "Load_keystore keeloq_mfcodes OK\r\n"
        "Listening at frequency: 433920000 device: 0. Press CTRL+C to stop\r\n"
        "Protocol: Princeton\r\n"
        "Bit: 24\r\n"
        "Key: 00 00 00 00 00 74 BA DE\r\n"
        "TE: 403\r\n"
    )

    assert capture.frequency_hz == 433_920_000
    assert capture.device_index == 0
    assert capture.packet_count == 1
    assert capture.packets[0].protocol == "Princeton"
    assert capture.packets[0].fields["Bit"] == "24"
    assert capture.packets[0].fields["TE"] == "403"


def test_transport_uses_receive_only_internal_radio_and_etx() -> None:
    instances: list[SubGhzFakeSerial] = []

    def factory(**kwargs: Any) -> SubGhzFakeSerial:
        instance = SubGhzFakeSerial(**kwargs)
        instances.append(instance)
        return instance

    with FlipperSerialTransport("/dev/fake", serial_factory=factory) as transport:
        payload = transport.capture_subghz(DEFAULT_SUBGHZ_FREQUENCY_HZ, 0.01)

    assert b"Protocol: Princeton" in payload
    assert instances[0].writes == [b"subghz rx 433920000 0\r", b"\x03"]


def test_unverified_subghz_capability_is_not_advertised() -> None:
    adapter = FlipperAdapter("/dev/fake", serial_factory=_factory())
    action = Action(
        action_id="rf-1",
        capability_id=SUBGHZ_OBSERVE,
        target_id="target-a",
        action_class=ActionClass.OBSERVE,
        inputs={"duration_seconds": 0.01, "frequency_hz": 433_920_000},
    )

    assert adapter.capabilities() == []
    assert adapter.validate(action).valid is False


def test_verified_subghz_capability_executes_and_normalizes_packet() -> None:
    adapter = FlipperAdapter(
        "/dev/fake",
        serial_factory=_factory(),
        verified_capabilities={SUBGHZ_OBSERVE},
    )
    action = Action(
        action_id="rf-2",
        capability_id=SUBGHZ_OBSERVE,
        target_id="target-a",
        action_class=ActionClass.OBSERVE,
        inputs={"duration_seconds": 0.01, "frequency_hz": 433_920_000},
    )

    capabilities = adapter.capabilities()
    result = adapter.execute(action)

    assert [item.capability_id for item in capabilities] == [SUBGHZ_OBSERVE]
    assert result.status is ExecutionStatus.SUCCESS
    assert result.normalized["frequency_hz"] == 433_920_000
    assert result.normalized["packet_count"] == 1
    assert result.normalized["packets"][0]["protocol"] == "Princeton"


def test_subghz_capability_is_inconclusive_when_no_packet_arrives() -> None:
    adapter = FlipperAdapter(
        "/dev/fake",
        serial_factory=_factory(emit_packet=False),
        verified_capabilities={SUBGHZ_OBSERVE},
    )
    action = Action(
        action_id="rf-3",
        capability_id=SUBGHZ_OBSERVE,
        target_id="target-a",
        action_class=ActionClass.OBSERVE,
        inputs={"duration_seconds": 0.01, "frequency_hz": 433_920_000},
    )

    result = adapter.execute(action)

    assert result.status is ExecutionStatus.INCONCLUSIVE
    assert result.normalized["packet_count"] == 0


def test_subghz_validation_blocks_out_of_band_frequency() -> None:
    adapter = FlipperAdapter(
        "/dev/fake",
        serial_factory=_factory(),
        verified_capabilities={SUBGHZ_OBSERVE},
    )
    action = Action(
        action_id="rf-4",
        capability_id=SUBGHZ_OBSERVE,
        target_id="target-a",
        action_class=ActionClass.OBSERVE,
        inputs={"duration_seconds": 0.01, "frequency_hz": 500_000_000},
    )

    validation = adapter.validate(action)

    assert validation.valid is False
    assert "receive ranges" in (validation.reason or "")
