from __future__ import annotations

import hashlib
from typing import Any

import pytest

from hardware_pentest.adapters.flipper.apps import MARAUDER_APP, FlipperAppManager
from hardware_pentest.adapters.flipper.errors import FlipperProtocolError


class ProvisioningFakeSerial:
    def __init__(self, *, instances=None, **kwargs: Any) -> None:
        self.is_open = True
        self.writes: list[bytes] = []
        self.remote = bytearray()
        self.pending_chunk_size: int | None = None
        self.pending_command: str | None = None
        self._buffer = bytearray(b">: ")
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
        if self.pending_chunk_size is not None:
            assert len(data) == self.pending_chunk_size
            self.remote.extend(data)
            command = self.pending_command or "storage write chunk"
            self.pending_chunk_size = None
            self.pending_command = None
            self._respond(command, "")
            return len(data)

        command = data.decode("ascii", errors="ignore").rstrip("\r")
        if data == b"\r":
            self._buffer.extend(b">: ")
        elif command == "info device":
            self._respond(
                command,
                "hardware_model: Flipper Zero\r\n"
                "hardware_uid: PROVISION123\r\n"
                "firmware_version: 1.4.3",
            )
        elif command == f"storage stat {MARAUDER_APP.path}":
            body = (
                f"Type: File\r\nSize: {len(self.remote)}"
                if self.remote
                else "Storage error: Not exist"
            )
            self._respond(command, body)
        elif command == f"storage remove {MARAUDER_APP.path}":
            self.remote.clear()
            self._respond(command, "")
        elif command.startswith(f"storage write chunk {MARAUDER_APP.path} "):
            self.pending_chunk_size = int(command.rsplit(" ", 1)[1])
            self.pending_command = command
        elif command == f"storage md5 {MARAUDER_APP.path}":
            digest = hashlib.md5(self.remote, usedforsecurity=False).hexdigest()
            self._respond(command, digest)
        return len(data)

    def _respond(self, command: str, body: str) -> None:
        payload = command + "\r\n"
        if body:
            payload += body + "\r\n"
        payload += ">: "
        self._buffer.extend(payload.encode())

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self._buffer.clear()


def factory(instances):
    def build(**kwargs: Any) -> ProvisioningFakeSerial:
        return ProvisioningFakeSerial(instances=instances, **kwargs)

    return build


def test_pinned_fap_is_written_in_bounded_chunks_and_verified(tmp_path) -> None:
    payload = b"A" * 600
    source = tmp_path / "marauder.fap"
    source.write_bytes(payload)
    expected_sha256 = hashlib.sha256(payload).hexdigest()
    instances: list[ProvisioningFakeSerial] = []
    manager = FlipperAppManager(
        "/dev/fake",
        serial_factory=factory(instances),
    )

    installation = manager.install_from_file(
        MARAUDER_APP.app_id,
        source,
        expected_sha256=expected_sha256,
    )

    assert installation.installed is True
    assert installation.file_md5 == hashlib.md5(payload, usedforsecurity=False).hexdigest()
    assert len(instances) == 1
    writes = instances[0].writes
    assert f"storage write chunk {MARAUDER_APP.path} 512\r".encode() in writes
    assert f"storage write chunk {MARAUDER_APP.path} 88\r".encode() in writes
    assert b"A" * 512 in writes
    assert b"A" * 88 in writes


def test_sha256_mismatch_is_rejected_before_device_io(tmp_path) -> None:
    source = tmp_path / "marauder.fap"
    source.write_bytes(b"trusted-looking-but-wrong")
    instances: list[ProvisioningFakeSerial] = []
    manager = FlipperAppManager(
        "/dev/fake",
        serial_factory=factory(instances),
    )

    with pytest.raises(FlipperProtocolError, match="SHA-256 mismatch"):
        manager.install_from_file(
            MARAUDER_APP.app_id,
            source,
            expected_sha256="0" * 64,
        )

    assert instances == []


def test_provisioning_refuses_non_sha256_pin(tmp_path) -> None:
    source = tmp_path / "marauder.fap"
    source.write_bytes(b"payload")
    manager = FlipperAppManager("/dev/fake", serial_factory=factory([]))

    with pytest.raises(FlipperProtocolError, match="64 hexadecimal"):
        manager.install_from_file(
            MARAUDER_APP.app_id,
            source,
            expected_sha256="not-a-digest",
        )
