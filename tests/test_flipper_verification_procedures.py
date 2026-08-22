from __future__ import annotations

from typing import Any

import pytest

from hardware_pentest.adapters.flipper.adapter import (
    GPIO_INSPECT,
    INFRARED_OBSERVE,
    NFC_IDENTIFY,
    SUBGHZ_OBSERVE,
)
from hardware_pentest.adapters.flipper.verification_procedures import FlipperCapabilityVerifier
from hardware_pentest.verification import LocalVerificationStore

NFC_PROMPT = b"[\x1b[32mnfc\x1b[0m]>: "


class VerificationFakeSerial:
    def __init__(
        self,
        *,
        infrared_protocol: str = "NEC",
        subghz_protocol: str = "Princeton",
        nfc_protocol: str = "Mifare Ultralight",
        gpio_level: int = 1,
        instances: list[VerificationFakeSerial] | None = None,
        **kwargs: Any,
    ) -> None:
        self.kwargs = kwargs
        self.infrared_protocol = infrared_protocol
        self.subghz_protocol = subghz_protocol
        self.nfc_protocol = nfc_protocol
        self.gpio_level = gpio_level
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
                b"hardware_uid: VERIFY123\r\n"
                b"firmware_version: 1.4.3\r\n"
                b">: "
            )
        elif data == b"ir rx\r":
            self._buffer.extend(
                b"ir rx\r\nReceiving  INFRARED...\r\nPress Ctrl+C to abort\r\n"
                + f"{self.infrared_protocol}, A:0x00FF, C:0x20DF\r\n".encode()
            )
        elif data == b"subghz rx 433920000 0\r":
            self._buffer.extend(
                b"subghz rx 433920000 0\r\n"
                b"Listening at frequency: 433920000 device: 0. Press CTRL+C to stop\r\n"
                + f"Protocol: {self.subghz_protocol}\r\n".encode()
                + b"Bit: 24\r\nKey: 00 00 00 00 00 74 BA DE\r\nTE: 403\r\n"
            )
        elif data == b"nfc\r":
            self._buffer.extend(
                b"nfc\r\nWelcome to NFC Command Line Interface!\r\n" + NFC_PROMPT
            )
        elif data == b"scanner -t\r":
            self._buffer.extend(
                b"scanner -t\r\nPress Ctrl+C to abort\r\n"
                b"Protocols detected: \r\n"
                + f"Protocol [1]: ISO14443-3A -> {self.nfc_protocol}\r\n".encode()
                + NFC_PROMPT
            )
        elif data == b"exit\r":
            self._buffer.extend(b"exit\r\n>: ")
        elif data == b"gpio read PA7\r":
            self._buffer.extend(
                f"gpio read PA7\r\nPin PA7 <= {self.gpio_level}\r\n>: ".encode()
            )
        elif data == b"\x03":
            self._buffer.extend(b"\r\n>: ")
        return len(data)

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self._buffer.clear()


def factory(
    *,
    infrared_protocol: str = "NEC",
    subghz_protocol: str = "Princeton",
    nfc_protocol: str = "Mifare Ultralight",
    gpio_level: int = 1,
    instances: list[VerificationFakeSerial] | None = None,
):
    def build(**kwargs: Any) -> VerificationFakeSerial:
        return VerificationFakeSerial(
            infrared_protocol=infrared_protocol,
            subghz_protocol=subghz_protocol,
            nfc_protocol=nfc_protocol,
            gpio_level=gpio_level,
            instances=instances,
            **kwargs,
        )

    return build


def verifier(
    tmp_path,
    **factory_kwargs: Any,
) -> tuple[FlipperCapabilityVerifier, LocalVerificationStore]:
    store = LocalVerificationStore(tmp_path / "verification")
    return (
        FlipperCapabilityVerifier(
            "/dev/fake",
            store=store,
            serial_factory=factory(**factory_kwargs),
        ),
        store,
    )


def test_infrared_verification_executes_real_handler_and_enables_capability(tmp_path) -> None:
    subject, store = verifier(tmp_path)

    record = subject.verify_infrared(
        expected_protocol="NEC",
        known_source_confirmed=True,
        duration_seconds=0.01,
    )

    assert record.passed is True
    assert record.capability_id == INFRARED_OBSERVE
    assert store.evidence_is_intact(record) is True
    assert store.verified_capabilities(
        _identity_from_record(record),
        {INFRARED_OBSERVE},
    ) == frozenset({INFRARED_OBSERVE})


def test_wrong_expected_protocol_writes_failed_record_and_does_not_enable(tmp_path) -> None:
    subject, store = verifier(tmp_path)

    record = subject.verify_infrared(
        expected_protocol="RC5",
        known_source_confirmed=True,
        duration_seconds=0.01,
    )

    assert record.passed is False
    assert any(check.check_id == "expected_protocol_observed" for check in record.checks)
    assert store.verified_capabilities(
        _identity_from_record(record),
        {INFRARED_OBSERVE},
    ) == frozenset()


def test_subghz_verification_matches_known_protocol(tmp_path) -> None:
    subject, _store = verifier(tmp_path)

    record = subject.verify_subghz(
        expected_protocol="Princeton",
        known_source_confirmed=True,
        duration_seconds=0.01,
    )

    assert record.passed is True
    assert record.capability_id == SUBGHZ_OBSERVE


def test_nfc_verification_matches_known_tag_protocol(tmp_path) -> None:
    subject, _store = verifier(tmp_path)

    record = subject.verify_nfc(
        expected_protocol="Mifare Ultralight",
        known_source_confirmed=True,
        duration_seconds=0.01,
    )

    assert record.passed is True
    assert record.capability_id == NFC_IDENTIFY


def test_gpio_verification_reads_only_and_matches_known_level(tmp_path) -> None:
    instances: list[VerificationFakeSerial] = []
    subject, _store = verifier(tmp_path, instances=instances)

    record = subject.verify_gpio(
        pin="PA7",
        expected_level=1,
        human_setup_confirmed=True,
    )

    assert record.passed is True
    assert record.capability_id == GPIO_INSPECT
    action_writes = [write for instance in instances for write in instance.writes]
    assert b"gpio read PA7\r" in action_writes
    assert not any(write.startswith(b"gpio mode") for write in action_writes)
    assert not any(write.startswith(b"gpio set") for write in action_writes)


def test_known_source_verifications_require_explicit_confirmation(tmp_path) -> None:
    subject, _store = verifier(tmp_path)

    with pytest.raises(ValueError, match="explicit confirmation"):
        subject.verify_nfc(
            expected_protocol="Mifare Ultralight",
            known_source_confirmed=False,
            duration_seconds=0.01,
        )


def test_gpio_verification_requires_explicit_electrical_setup_confirmation(tmp_path) -> None:
    subject, _store = verifier(tmp_path)

    with pytest.raises(ValueError, match="explicit confirmation"):
        subject.verify_gpio(
            pin="PA7",
            expected_level=1,
            human_setup_confirmed=False,
        )


def test_gpio_verification_rejects_debug_pin(tmp_path) -> None:
    subject, _store = verifier(tmp_path)

    with pytest.raises(ValueError, match="non-debug GPIO pins"):
        subject.verify_gpio(
            pin="PB7",
            expected_level=1,
            human_setup_confirmed=True,
        )


def _identity_from_record(record):
    from hardware_pentest.core.models import InstrumentIdentity

    return InstrumentIdentity(
        instrument_id=record.instrument_id,
        kind=record.instrument_kind,
        model=record.instrument_model,
        transport="usb-cli",
        firmware_version=record.firmware_version,
        adapter_version=record.adapter_version,
    )
