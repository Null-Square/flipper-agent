from __future__ import annotations

from typing import Any

import pytest

from hardware_pentest.adapters.flipper.apps import MARAUDER_APP, FlipperAppManager
from hardware_pentest.adapters.flipper.apps.models import FlipperAppSpec
from hardware_pentest.adapters.flipper.errors import FlipperProtocolError


class AppFakeSerial:
    def __init__(
        self,
        *,
        installed: bool = True,
        running_app_name: str | None = None,
        instances: list[AppFakeSerial] | None = None,
        **kwargs: Any,
    ) -> None:
        self.installed = installed
        self.kwargs = kwargs
        self.is_open = True
        self.running_app_name = running_app_name
        self.writes: list[bytes] = []
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
        command = data.decode("ascii", errors="ignore").rstrip("\r")
        if data == b"info device\r":
            self._respond(
                command,
                "hardware_model: Flipper Zero\r\n"
                "hardware_uid: APPTEST123\r\n"
                "firmware_version: 1.4.3",
            )
        elif command == f"storage stat {MARAUDER_APP.path}":
            body = (
                "Type: File\r\nSize: 42420"
                if self.installed
                else "Storage error: Not exist"
            )
            self._respond(command, body)
        elif command == f"storage md5 {MARAUDER_APP.path}":
            self._respond(command, "0123456789abcdef0123456789ABCDEF")
        elif command == f"loader open {MARAUDER_APP.path}":
            self.running_app_name = MARAUDER_APP.display_name
            self._respond(command, "")
        elif command == "loader info":
            body = (
                f'Application "{self.running_app_name}" is running'
                if self.running_app_name
                else "No application is running"
            )
            self._respond(command, body)
        elif command == "loader close":
            old_name = self.running_app_name
            self.running_app_name = None
            body = f'Application "{old_name}" was closed' if old_name else "No application is running"
            self._respond(command, body)
        elif command.startswith("input send "):
            self._respond(command, "")
        elif data == b"\r":
            self._buffer.extend(b">: ")
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


def factory(
    *,
    installed: bool = True,
    running_app_name: str | None = None,
    instances: list[AppFakeSerial] | None = None,
):
    def build(**kwargs: Any) -> AppFakeSerial:
        return AppFakeSerial(
            installed=installed,
            running_app_name=running_app_name,
            instances=instances,
            **kwargs,
        )

    return build


def test_discovery_finds_known_marauder_fap_and_fingerprints_it() -> None:
    manager = FlipperAppManager("/dev/fake", serial_factory=factory())

    installations = manager.discover()

    assert len(installations) == 1
    marauder = installations[0]
    assert marauder.spec == MARAUDER_APP
    assert marauder.installed is True
    assert marauder.file_md5 == "0123456789abcdef0123456789abcdef"
    assert marauder.stat == {"type": "File", "size": "42420"}


def test_missing_fap_does_not_request_md5() -> None:
    instances: list[AppFakeSerial] = []
    manager = FlipperAppManager(
        "/dev/fake",
        serial_factory=factory(installed=False, instances=instances),
    )

    installation = manager.installation(MARAUDER_APP.app_id)

    assert installation.installed is False
    assert installation.file_md5 is None
    writes = [item for instance in instances for item in instance.writes]
    assert f"storage stat {MARAUDER_APP.path}\r".encode() in writes
    assert not any(item.startswith(b"storage md5") for item in writes)


def test_launch_uses_exact_catalogued_fap_and_verifies_running_app_name() -> None:
    instances: list[AppFakeSerial] = []
    manager = FlipperAppManager(
        "/dev/fake",
        serial_factory=factory(instances=instances),
    )

    state = manager.launch(MARAUDER_APP.app_id)

    assert state.running is True
    assert state.application_name == MARAUDER_APP.display_name
    writes = [item for instance in instances for item in instance.writes]
    assert f"loader open {MARAUDER_APP.path}\r".encode() in writes


def test_unknown_app_id_is_rejected_before_device_io() -> None:
    instances: list[AppFakeSerial] = []
    manager = FlipperAppManager(
        "/dev/fake",
        serial_factory=factory(instances=instances),
    )

    with pytest.raises(FlipperProtocolError, match="Unknown Flipper app"):
        manager.launch("../../evil")

    assert instances == []


def test_catalogue_path_cannot_escape_ext_apps() -> None:
    bad = FlipperAppSpec(
        app_id="bad",
        display_name="Bad",
        path="/ext/apps/GPIO/../../bad.fap",
        category="GPIO",
    )
    manager = FlipperAppManager(
        "/dev/fake",
        serial_factory=factory(),
        app_specs=(bad,),
    )

    with pytest.raises(FlipperProtocolError, match="parent traversal"):
        manager.discover()


def test_short_input_is_bounded_to_expected_running_app_and_event_sequence() -> None:
    instances: list[AppFakeSerial] = []
    manager = FlipperAppManager(
        "/dev/fake",
        serial_factory=factory(
            running_app_name=MARAUDER_APP.display_name,
            instances=instances,
        ),
    )

    state = manager.send_short_input(MARAUDER_APP.app_id, "ok")

    assert state.running is True
    assert state.application_name == MARAUDER_APP.display_name
    events = [item for item in instances[0].writes if item.startswith(b"input send")]
    assert events == [
        b"input send ok press\r",
        b"input send ok short\r",
        b"input send ok release\r",
    ]


def test_input_refuses_to_control_a_different_running_app() -> None:
    instances: list[AppFakeSerial] = []
    manager = FlipperAppManager(
        "/dev/fake",
        serial_factory=factory(running_app_name="Sub-GHz", instances=instances),
    )

    with pytest.raises(FlipperProtocolError, match="Expected running app"):
        manager.send_short_input(MARAUDER_APP.app_id, "ok")

    assert not any(item.startswith(b"input send") for item in instances[0].writes)


def test_close_refuses_to_close_a_different_running_app() -> None:
    instances: list[AppFakeSerial] = []
    manager = FlipperAppManager(
        "/dev/fake",
        serial_factory=factory(running_app_name="NFC", instances=instances),
    )

    with pytest.raises(FlipperProtocolError, match="Expected running app"):
        manager.close(MARAUDER_APP.app_id)

    assert b"loader close\r" not in instances[0].writes


def test_invalid_input_key_is_rejected_without_injection() -> None:
    instances: list[AppFakeSerial] = []
    manager = FlipperAppManager(
        "/dev/fake",
        serial_factory=factory(
            running_app_name=MARAUDER_APP.display_name,
            instances=instances,
        ),
    )

    with pytest.raises(FlipperProtocolError, match="Input key must be one of"):
        manager.send_short_input(MARAUDER_APP.app_id, "shell")

    writes = instances[0].writes
    assert not any(item.startswith(b"input send") for item in writes)
