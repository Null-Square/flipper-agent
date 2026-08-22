from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SerialStep:
    expected_write: bytes
    response: bytes = b""
    short_write: bool = False
    write_error: OSError | None = None


class ScriptedSerial:
    """Stateful serial double with strict writes, fragmentation and injected I/O faults."""

    def __init__(
        self,
        *,
        steps: tuple[SerialStep, ...] | list[SerialStep],
        initial_bytes: bytes,
        max_read_size: int | None = None,
        read_error_after_writes: int | None = None,
        **kwargs: Any,
    ) -> None:
        self.steps = list(steps)
        self.kwargs = kwargs
        self.is_open = True
        self.max_read_size = max_read_size
        self.read_error_after_writes = read_error_after_writes
        self.writes: list[bytes] = []
        self._buffer = bytearray(initial_bytes)
        self._read_error_raised = False

    @property
    def in_waiting(self) -> int:
        return len(self._buffer)

    def read(self, size: int = 1) -> bytes:
        if (
            self.read_error_after_writes is not None
            and len(self.writes) >= self.read_error_after_writes
            and not self._read_error_raised
        ):
            self._read_error_raised = True
            raise OSError("injected serial read failure")
        if not self._buffer:
            return b""
        requested = max(1, size)
        if self.max_read_size is not None:
            requested = min(requested, self.max_read_size)
        chunk = bytes(self._buffer[:requested])
        del self._buffer[:requested]
        return chunk

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        if not self.steps:
            raise AssertionError(f"Unexpected serial write: {data!r}")
        step = self.steps.pop(0)
        if data != step.expected_write:
            raise AssertionError(
                f"Expected serial write {step.expected_write!r}, got {data!r}"
            )
        if step.write_error is not None:
            raise step.write_error
        if step.short_write:
            return max(0, len(data) - 1)
        self._buffer.extend(step.response)
        return len(data)

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self._buffer.clear()

    def assert_complete(self) -> None:
        if self.steps:
            expected = [step.expected_write for step in self.steps]
            raise AssertionError(f"Unconsumed scripted serial writes: {expected!r}")


def serial_factory(device: ScriptedSerial):
    def build(**kwargs: Any) -> ScriptedSerial:
        device.kwargs.update(kwargs)
        return device

    return build
