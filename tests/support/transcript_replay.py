from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_SENSITIVE_VALUES = (
    (
        re.compile(r"(?im)\bPassword:\s*(?P<value>[^\r\n]+)"),
        "<redacted-secret>",
    ),
    (
        re.compile(r"(?im)\bjoin\s+-a\s+\d+\s+-p\s+(?P<value>[^\r\n]+)"),
        "<redacted-secret>",
    ),
    (
        re.compile(r"(?im)\bhardware[_\.]uid\s*:\s*(?P<value>[^\r\n]+)"),
        "<redacted-uid>",
    ),
)
_MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")


class TranscriptReplaySerial:
    """Replay one sanitized TranscriptRecorder session as a strict serial endpoint."""

    def __init__(self, *, events: list[dict[str, str]], **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.is_open = True
        self.writes: list[bytes] = []
        self._events = list(events)
        self._buffer = bytearray()
        self._prime_rx()

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
        if not self._events or self._events[0].get("direction") != "tx":
            raise AssertionError(f"Transcript did not expect a write here: {data!r}")
        event = self._events.pop(0)
        expected = event.get("data", "").encode("utf-8")
        if data != expected:
            raise AssertionError(f"Transcript expected {expected!r}, got {data!r}")
        self._prime_rx()
        return len(data)

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self._buffer.clear()

    def assert_complete(self) -> None:
        if self._events:
            raise AssertionError(f"Unconsumed transcript events: {self._events!r}")
        if self._buffer:
            raise AssertionError(f"Unconsumed transcript bytes: {bytes(self._buffer)!r}")

    def _prime_rx(self) -> None:
        while self._events and self._events[0].get("direction") == "rx":
            event = self._events.pop(0)
            self._buffer.extend(event.get("data", "").encode("utf-8"))


def replay_factory(path: str | Path, *, label: str):
    fixture = _load_fixture(path)
    sessions = [item for item in fixture["sessions"] if item.get("label") == label]
    if len(sessions) != 1:
        raise ValueError(f"Expected exactly one transcript session labelled {label!r}")
    events = sessions[0].get("events")
    if not isinstance(events, list) or not events:
        raise ValueError(f"Transcript session {label!r} has no events")
    device = TranscriptReplaySerial(events=events)

    def build(**kwargs: Any) -> TranscriptReplaySerial:
        device.kwargs.update(kwargs)
        return device

    build.device = device  # type: ignore[attr-defined]
    return build


def _load_fixture(path: str | Path) -> dict[str, Any]:
    fixture_path = Path(path)
    text = fixture_path.read_text(encoding="utf-8")
    _validate_fixture_hygiene(text, fixture_path)
    payload = json.loads(text)
    if not isinstance(payload, dict) or payload.get("schema_version") != "1":
        raise ValueError("Transcript fixture must use schema_version '1'")
    sessions = payload.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        raise ValueError("Transcript fixture must contain at least one session")
    return payload


def _validate_fixture_hygiene(text: str, path: Path) -> None:
    if _MAC.search(text):
        raise ValueError(f"Transcript fixture contains unsanitized sensitive data: {path}")
    for pattern, allowed_value in _SENSITIVE_VALUES:
        for match in pattern.finditer(text):
            if match.group("value").strip() != allowed_value:
                raise ValueError(
                    f"Transcript fixture contains unsanitized sensitive data: {path}"
                )
