from __future__ import annotations

from typing import Any

from hardware_pentest.adapters.flipper.adapter import INFRARED_OBSERVE, FlipperAdapter
from hardware_pentest.adapters.flipper.infrared import parse_infrared_capture
from hardware_pentest.adapters.flipper.transport import FlipperSerialTransport
from hardware_pentest.core.models import Action, ActionClass, ExecutionStatus


class InfraredFakeSerial:
    def __init__(self, *, emit_signal: bool = True, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.emit_signal = emit_signal
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
        elif data == b"ir rx\r":
            self._buffer.extend(
                b"ir rx\r\nReceiving  INFRARED...\r\nPress Ctrl+C to abort\r\n"
            )
            if self.emit_signal:
                self._buffer.extend(b"NEC, A:0x00FF, C:0x20DF\r\n")
        elif data == b"ir rx raw\r":
            self._buffer.extend(
                b"ir rx raw\r\nReceiving RAW INFRARED...\r\nPress Ctrl+C to abort\r\n"
                b"RAW, 4 samples:\r\n9000 4500 560 560 \r\n"
            )
        elif data == b"\x03":
            self._buffer.extend(b"\r\n>: ")
        return len(data)

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self._buffer.clear()


def _factory(*, emit_signal: bool = True):
    def factory(**kwargs: Any) -> InfraredFakeSerial:
        return InfraredFakeSerial(emit_signal=emit_signal, **kwargs)

    return factory


def _verified_adapter(*, emit_signal: bool = True) -> FlipperAdapter:
    return FlipperAdapter(
        "/dev/fake",
        serial_factory=_factory(emit_signal=emit_signal),
        verified_capabilities={INFRARED_OBSERVE},
        allow_verification_override=True,
    )


def test_parse_decoded_infrared_signal_and_repeat() -> None:
    capture = parse_infrared_capture(
        "Receiving  INFRARED...\r\n"
        "Press Ctrl+C to abort\r\n"
        "NEC, A:0x00ff, C:0x20df\r\n"
        "NEC, A:0x00ff, C:0x20df R\r\n"
    )

    assert capture.signal_count == 2
    assert capture.decoded[0].protocol == "NEC"
    assert capture.decoded[0].address == "0x00FF"
    assert capture.decoded[0].command == "0x20DF"
    assert capture.decoded[0].repeat is False
    assert capture.decoded[1].repeat is True


def test_parse_raw_infrared_signal() -> None:
    capture = parse_infrared_capture(
        "Receiving RAW INFRARED...\r\n"
        "Press Ctrl+C to abort\r\n"
        "RAW, 4 samples:\r\n"
        "9000 4500 560 560 \r\n"
    )

    assert capture.signal_count == 1
    assert capture.raw[0].declared_samples == 4
    assert capture.raw[0].timings == (9000, 4500, 560, 560)


def test_transport_uses_receive_only_ir_command_and_etx() -> None:
    instances: list[InfraredFakeSerial] = []

    def factory(**kwargs: Any) -> InfraredFakeSerial:
        instance = InfraredFakeSerial(**kwargs)
        instances.append(instance)
        return instance

    with FlipperSerialTransport("/dev/fake", serial_factory=factory) as transport:
        payload = transport.capture_infrared(0.01)

    assert b"NEC, A:0x00FF, C:0x20DF" in payload
    assert instances[0].writes == [b"ir rx\r", b"\x03"]


def test_unverified_infrared_capability_is_not_advertised() -> None:
    adapter = FlipperAdapter("/dev/fake", serial_factory=_factory())
    action = Action(
        action_id="ir-1",
        capability_id=INFRARED_OBSERVE,
        target_id="target-a",
        action_class=ActionClass.OBSERVE,
        inputs={"duration_seconds": 0.01},
    )

    assert adapter.capabilities() == []
    assert adapter.validate(action).valid is False


def test_verified_infrared_capability_executes_and_normalizes_signal() -> None:
    adapter = _verified_adapter()
    action = Action(
        action_id="ir-2",
        capability_id=INFRARED_OBSERVE,
        target_id="target-a",
        action_class=ActionClass.OBSERVE,
        inputs={"duration_seconds": 0.01},
    )

    capabilities = adapter.capabilities()
    result = adapter.execute(action)

    assert [item.capability_id for item in capabilities] == [INFRARED_OBSERVE]
    assert result.status is ExecutionStatus.SUCCESS
    assert result.normalized["signal_count"] == 1
    assert result.normalized["decoded"][0]["protocol"] == "NEC"


def test_verified_infrared_capability_is_inconclusive_when_no_signal_arrives() -> None:
    adapter = _verified_adapter(emit_signal=False)
    action = Action(
        action_id="ir-3",
        capability_id=INFRARED_OBSERVE,
        target_id="target-a",
        action_class=ActionClass.OBSERVE,
        inputs={"duration_seconds": 0.01},
    )

    result = adapter.execute(action)

    assert result.status is ExecutionStatus.INCONCLUSIVE
    assert result.normalized["signal_count"] == 0
    assert result.limitations


def test_infrared_validation_rejects_duration_outside_bounds() -> None:
    adapter = _verified_adapter()
    action = Action(
        action_id="ir-4",
        capability_id=INFRARED_OBSERVE,
        target_id="target-a",
        action_class=ActionClass.OBSERVE,
        inputs={"duration_seconds": 31},
    )

    validation = adapter.validate(action)

    assert validation.valid is False
    assert "duration_seconds" in (validation.reason or "")
