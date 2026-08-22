from __future__ import annotations

from typing import Any

from hardware_pentest.adapters.flipper.adapter import GPIO_INSPECT, FlipperAdapter
from hardware_pentest.adapters.flipper.gpio import (
    ALLOWED_GPIO_INPUT_PINS,
    parse_gpio_read,
)
from hardware_pentest.adapters.flipper.transport import FlipperSerialTransport
from hardware_pentest.core.models import Action, ActionClass, ExecutionStatus


class GpioFakeSerial:
    def __init__(self, *, input_ready: bool = True, value: int = 1, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.input_ready = input_ready
        self.value = value
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
                b"hardware_uid: GPIO1234\r\n"
                b"firmware_version: 1.4.3\r\n"
                b">: "
            )
        elif data == b"gpio read PA7\r":
            if self.input_ready:
                self._buffer.extend(f"gpio read PA7\r\nPin PA7 <= {self.value}\r\n>: ".encode())
            else:
                self._buffer.extend(
                    b"gpio read PA7\r\nErr: pin PA7 is not set as an input.\r\n>: "
                )
        return len(data)

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self._buffer.clear()


def _factory(*, input_ready: bool = True, value: int = 1, instances=None):
    def factory(**kwargs: Any) -> GpioFakeSerial:
        instance = GpioFakeSerial(input_ready=input_ready, value=value, **kwargs)
        if instances is not None:
            instances.append(instance)
        return instance

    return factory


def _verified_adapter(*, input_ready: bool = True, value: int = 1) -> FlipperAdapter:
    return FlipperAdapter(
        "/dev/fake",
        serial_factory=_factory(input_ready=input_ready, value=value),
        verified_capabilities={GPIO_INSPECT},
        allow_verification_override=True,
    )


def _action(*, pin: str = "PA7", human: bool = True) -> Action:
    return Action(
        action_id="gpio-1",
        capability_id=GPIO_INSPECT,
        target_id="target-a",
        action_class=ActionClass.OBSERVE,
        inputs={"pin": pin},
        requires_human_action=human,
    )


def test_allowed_gpio_set_excludes_debug_and_dangerous_pins() -> None:
    assert ALLOWED_GPIO_INPUT_PINS == frozenset(
        {"PA7", "PA6", "PA4", "PB3", "PB2", "PC3", "PC1", "PC0"}
    )
    assert "PB7" not in ALLOWED_GPIO_INPUT_PINS
    assert "PA13" not in ALLOWED_GPIO_INPUT_PINS
    assert "PB9" not in ALLOWED_GPIO_INPUT_PINS


def test_parse_gpio_input_level() -> None:
    result = parse_gpio_read("Pin PA7 <= 1", "PA7")

    assert result.pin == "PA7"
    assert result.value == 1
    assert result.input_ready is True


def test_parse_gpio_not_input_mode() -> None:
    result = parse_gpio_read("Err: pin PA7 is not set as an input.", "PA7")

    assert result.value is None
    assert result.input_ready is False
    assert "human setup" in result.detail


def test_transport_issues_only_gpio_read_and_never_changes_pin_mode() -> None:
    instances: list[GpioFakeSerial] = []
    with FlipperSerialTransport(
        "/dev/fake",
        serial_factory=_factory(instances=instances),
    ) as transport:
        payload = transport.read_gpio_input("PA7")

    assert b"Pin PA7 <= 1" in payload
    assert instances[0].writes == [b"gpio read PA7\r"]


def test_gpio_capability_remains_hidden_without_verification() -> None:
    adapter = FlipperAdapter("/dev/fake", serial_factory=_factory())

    assert GPIO_INSPECT in adapter.implemented_capabilities
    assert adapter.capabilities() == []
    assert adapter.validate(_action()).valid is False


def test_gpio_requires_human_action_marker() -> None:
    adapter = _verified_adapter()

    validation = adapter.validate(_action(human=False))

    assert validation.valid is False
    assert "requires_human_action" in (validation.reason or "")


def test_gpio_rejects_debug_or_unknown_pin() -> None:
    adapter = _verified_adapter()

    validation = adapter.validate(_action(pin="PB7"))

    assert validation.valid is False
    assert "non-debug GPIO pins" in (validation.reason or "")


def test_verified_gpio_inspection_reads_digital_level() -> None:
    adapter = _verified_adapter(value=0)

    descriptor = adapter.capabilities()[0]
    result = adapter.execute(_action())

    assert descriptor.capability_id == GPIO_INSPECT
    assert descriptor.action_class is ActionClass.OBSERVE
    assert descriptor.constraints["requires_human_action"] is True
    assert descriptor.constraints["changes_pin_mode"] is False
    assert descriptor.constraints["writes_pin"] is False
    assert result.status is ExecutionStatus.SUCCESS
    assert result.normalized["pin"] == "PA7"
    assert result.normalized["value"] == 0


def test_gpio_execution_fails_if_human_setup_left_pin_out_of_input_mode() -> None:
    adapter = _verified_adapter(input_ready=False)

    result = adapter.execute(_action())

    assert result.status is ExecutionStatus.FAILED
    assert result.normalized["input_ready"] is False
    assert result.error
