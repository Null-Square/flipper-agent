from __future__ import annotations

from typing import Any

import pytest

from hardware_pentest.adapters.flipper.adapter import NFC_IDENTIFY, FlipperAdapter
from hardware_pentest.adapters.flipper.errors import FlipperProtocolError
from hardware_pentest.adapters.flipper.nfc import parse_nfc_protocol_scan
from hardware_pentest.adapters.flipper.transport import FlipperSerialTransport
from hardware_pentest.core.models import Action, ActionClass, ExecutionStatus

NFC_PROMPT = b"[\x1b[32mnfc\x1b[0m]>: "


class NfcFakeSerial:
    def __init__(
        self,
        *,
        emit_protocol: bool = True,
        nfc_available: bool = True,
        instances: list[NfcFakeSerial] | None = None,
        **kwargs: Any,
    ) -> None:
        self.kwargs = kwargs
        self.emit_protocol = emit_protocol
        self.nfc_available = nfc_available
        self.is_open = True
        self._buffer = bytearray(b">: ")
        self.writes: list[bytes] = []
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
        if data == b"info device\r":
            self._buffer.extend(
                b"info device\r\n"
                b"hardware_model: Flipper Zero\r\n"
                b"hardware_uid: NFC12345\r\n"
                b"firmware_version: 1.4.3\r\n"
                b">: "
            )
        elif data == b"nfc\r":
            if self.nfc_available:
                self._buffer.extend(
                    b"nfc\r\nWelcome to NFC Command Line Interface!\r\n" + NFC_PROMPT
                )
            else:
                self._buffer.extend(
                    b"nfc\r\nNFC app is running, unable to run NFC CLI at the same time!\r\n>: "
                )
        elif data == b"scanner -t\r":
            self._buffer.extend(b"scanner -t\r\nPress Ctrl+C to abort\r\n\r\n")
            if self.emit_protocol:
                self._buffer.extend(
                    b"Protocols detected: \r\n"
                    b"Protocol [1]: ISO14443-3A -> Mifare Ultralight\r\n" + NFC_PROMPT
                )
        elif data == b"\x03":
            self._buffer.extend(b"Protocols detected: \r\n" + NFC_PROMPT)
        elif data == b"exit\r":
            self._buffer.extend(b"exit\r\n>: ")
        return len(data)

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self._buffer.clear()


def _factory(
    *,
    emit_protocol: bool = True,
    nfc_available: bool = True,
    instances: list[NfcFakeSerial] | None = None,
):
    def factory(**kwargs: Any) -> NfcFakeSerial:
        return NfcFakeSerial(
            emit_protocol=emit_protocol,
            nfc_available=nfc_available,
            instances=instances,
            **kwargs,
        )

    return factory


def _verified_adapter() -> FlipperAdapter:
    return FlipperAdapter(
        "/dev/fake",
        serial_factory=_factory(),
        verified_capabilities={NFC_IDENTIFY},
        allow_verification_override=True,
    )


def test_parse_nfc_protocol_tree() -> None:
    scan = parse_nfc_protocol_scan(
        "Protocols detected:\r\n"
        "Protocol [2]: ISO14443-3B\r\n"
        "Protocol [1]: ISO14443-3A -> Mifare Ultralight\r\n"
    )

    assert scan.protocol_count == 2
    assert scan.protocols[0].index == 1
    assert scan.protocols[0].hierarchy == ("ISO14443-3A", "Mifare Ultralight")
    assert scan.protocols[0].leaf_protocol == "Mifare Ultralight"


def test_nfc_transport_stops_early_when_scanner_identifies_protocol() -> None:
    instances: list[NfcFakeSerial] = []
    with FlipperSerialTransport(
        "/dev/fake",
        serial_factory=_factory(instances=instances),
    ) as transport:
        payload = transport.scan_nfc_protocols(0.1)

    assert b"Protocol [1]: ISO14443-3A -> Mifare Ultralight" in payload
    assert instances[0].writes == [b"nfc\r", b"scanner -t\r", b"exit\r"]


def test_nfc_transport_interrupts_bounded_scan_when_no_tag_is_seen() -> None:
    instances: list[NfcFakeSerial] = []
    with FlipperSerialTransport(
        "/dev/fake",
        serial_factory=_factory(emit_protocol=False, instances=instances),
    ) as transport:
        payload = transport.scan_nfc_protocols(0.01)

    assert parse_nfc_protocol_scan(payload).protocol_count == 0
    assert instances[0].writes == [b"nfc\r", b"scanner -t\r", b"\x03", b"exit\r"]


def test_nfc_transport_rejects_unavailable_subshell() -> None:
    with FlipperSerialTransport(
        "/dev/fake",
        serial_factory=_factory(nfc_available=False),
    ) as transport:
        with pytest.raises(FlipperProtocolError, match="Unable to enter NFC CLI"):
            transport.scan_nfc_protocols(0.01)


def test_nfc_identify_is_interact_and_remains_gated_until_verified() -> None:
    action = Action(
        action_id="nfc-1",
        capability_id=NFC_IDENTIFY,
        target_id="target-a",
        action_class=ActionClass.INTERACT,
        inputs={"duration_seconds": 0.01},
    )
    adapter = FlipperAdapter("/dev/fake", serial_factory=_factory())

    assert NFC_IDENTIFY in adapter.implemented_capabilities
    assert adapter.capabilities() == []
    assert adapter.validate(action).valid is False


def test_verified_nfc_identify_executes_and_normalizes_protocols() -> None:
    adapter = _verified_adapter()
    action = Action(
        action_id="nfc-2",
        capability_id=NFC_IDENTIFY,
        target_id="target-a",
        action_class=ActionClass.INTERACT,
        inputs={"duration_seconds": 0.01},
    )

    descriptors = adapter.capabilities()
    result = adapter.execute(action)

    assert descriptors[0].action_class is ActionClass.INTERACT
    assert result.status is ExecutionStatus.SUCCESS
    assert result.normalized["protocol_count"] == 1
    assert result.normalized["protocols"][0]["leaf_protocol"] == "Mifare Ultralight"


def test_nfc_identify_rejects_observe_action_class() -> None:
    adapter = _verified_adapter()
    action = Action(
        action_id="nfc-3",
        capability_id=NFC_IDENTIFY,
        target_id="target-a",
        action_class=ActionClass.OBSERVE,
        inputs={"duration_seconds": 0.01},
    )

    validation = adapter.validate(action)

    assert validation.valid is False
    assert "INTERACT" in (validation.reason or "")
