from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from hardware_pentest.adapters.flipper.errors import FlipperProtocolError
from hardware_pentest.core.models import Action, ActionClass, CapabilityMaturity, ExecutionStatus
from hardware_pentest.synthesis import (
    BuildArtifact,
    GeneratedAppManifest,
    GeneratedFlipperAdapter,
    GeneratedProjectWriter,
    UfbTBuilder,
    generated_app_path,
    generated_result_path,
)

SAFE_SOURCE = r'''
#include <furi.h>
#include <furi_hal_gpio.h>
#include "hpa_runtime.h"

int32_t hpa_generated_main(void* context) {
    UNUSED(context);
    bool value = furi_hal_gpio_read(&gpio_ext_pa7);
    const char* result = value
        ? "{\"schema_version\":\"1\",\"status\":\"success\",\"observations\":{\"PA7\":1}}"
        : "{\"schema_version\":\"1\",\"status\":\"success\",\"observations\":{\"PA7\":0}}";
    return hpa_write_evidence_json(result) ? 0 : 1;
}
'''.strip()

RESULT_JSON = (
    '{"schema_version":"1","status":"success",'
    '"observations":{"PA7":1}}'
)


@dataclass
class GeneratedDeviceBackend:
    display_name: str = "HPA GPIO Sample"
    prepared_result: bytes = RESULT_JSON.encode()
    running_name: str | None = None
    running_ticks: int = 0
    files: dict[str, bytearray] = field(default_factory=dict)
    directories: set[str] = field(default_factory=set)
    writes: list[bytes] = field(default_factory=list)
    loader_close_count: int = 0
    auto_exit: bool = True
    ignore_removes: bool = False


class GeneratedFakeSerial:
    def __init__(self, *, backend: GeneratedDeviceBackend, **kwargs: Any) -> None:
        self.backend = backend
        self.kwargs = kwargs
        self.is_open = True
        self._buffer = bytearray(b">: ")
        self._pending_path: str | None = None
        self._pending_size: int | None = None

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
        self.backend.writes.append(data)
        if self._pending_size is not None:
            assert self._pending_path is not None
            assert len(data) == self._pending_size
            self.backend.files.setdefault(self._pending_path, bytearray()).extend(data)
            command = f"storage write_chunk {self._pending_path} {self._pending_size}"
            self._pending_path = None
            self._pending_size = None
            self._respond(command, "")
            return len(data)

        command = data.decode("ascii", errors="ignore").rstrip("\r")
        if data == b"\r":
            self._buffer.extend(b">: ")
        elif command == "info device":
            self._respond(
                command,
                "hardware_model: Flipper Zero\r\n"
                "hardware_uid: GENERATED123\r\n"
                "firmware_version: 1.4.3",
            )
        elif command.startswith("storage stat "):
            path = command.removeprefix("storage stat ")
            if path in self.backend.directories:
                body = "Directory"
            else:
                payload = self.backend.files.get(path)
                body = (
                    f"File, size: {len(payload)}b"
                    if payload is not None
                    else "Storage error: Not exist"
                )
            self._respond(command, body)
        elif command.startswith("storage mkdir "):
            path = command.removeprefix("storage mkdir ")
            self.backend.directories.add(path)
            self._respond(command, "")
        elif command.startswith("storage remove "):
            path = command.removeprefix("storage remove ")
            if not self.backend.ignore_removes:
                self.backend.files.pop(path, None)
            self._respond(command, "")
        elif command.startswith("storage write_chunk "):
            remainder = command.removeprefix("storage write_chunk ")
            path, size_text = remainder.rsplit(" ", 1)
            self._pending_path = path
            self._pending_size = int(size_text)
        elif command.startswith("storage md5 "):
            path = command.removeprefix("storage md5 ")
            payload = bytes(self.backend.files.get(path, b""))
            digest = hashlib.md5(payload, usedforsecurity=False).hexdigest()
            self._respond(command, digest)
        elif command.startswith("storage read "):
            path = command.removeprefix("storage read ")
            payload = bytes(self.backend.files[path])
            body = f"Size: {len(payload)}\r\n" + payload.decode("utf-8")
            self._respond(command, body)
        elif command.startswith('loader open "') and command.endswith('"'):
            self.backend.running_name = self.backend.display_name
            self.backend.running_ticks = 1
            self._respond(command, "")
        elif command == "loader info":
            self._loader_info(command)
        elif command == "loader close":
            self.backend.loader_close_count += 1
            self.backend.running_name = None
            self._respond(command, "Application was closed")
        return len(data)

    def _loader_info(self, command: str) -> None:
        if self.backend.running_name is None:
            self._respond(command, "No application is running")
            return
        if not self.backend.auto_exit or self.backend.running_ticks > 0:
            name = self.backend.running_name
            if self.backend.auto_exit:
                self.backend.running_ticks -= 1
            self._respond(command, f'Application "{name}" is running')
            return
        self.backend.running_name = None
        result_path = generated_result_path("hpa_gen_gpio_sample")
        self.backend.files[result_path] = bytearray(self.backend.prepared_result)
        self._respond(command, "No application is running")

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


def serial_factory(backend: GeneratedDeviceBackend):
    def build(**kwargs: Any) -> GeneratedFakeSerial:
        return GeneratedFakeSerial(backend=backend, **kwargs)

    return build


def manifest(*, runtime_seconds: float = 1.0) -> GeneratedAppManifest:
    return GeneratedAppManifest(
        app_id="hpa_gen_gpio_sample",
        display_name="HPA GPIO Sample",
        capability_id="generated.gpio.sample",
        declared_interfaces=("gpio",),
        declared_action_class=ActionClass.OBSERVE,
        requested_api_groups=("gpio",),
        max_runtime_seconds=runtime_seconds,
        expected_evidence=("GPIO level",),
    )


def build_artifact(tmp_path: Path) -> BuildArtifact:
    project = GeneratedProjectWriter(tmp_path / "generated").write(manifest(), SAFE_SOURCE)

    def runner(command, **kwargs):
        if command == ["ufbt"]:
            dist = Path(kwargs["cwd"]) / "dist"
            dist.mkdir()
            (dist / "hpa_gen_gpio_sample.fap").write_bytes(b"generated-fap-payload")
            return subprocess.CompletedProcess(command, 0, stdout="build ok\n", stderr="")
        if command == ["ufbt", "--version"]:
            return subprocess.CompletedProcess(command, 0, stdout="ufbt test\n", stderr="")
        raise AssertionError(command)

    return UfbTBuilder(runner=runner, timeout_seconds=10).build(project)


def approved_action() -> Action:
    return Action(
        action_id="generated-run-1",
        capability_id="generated.gpio.sample",
        target_id="lab-target",
        action_class=ActionClass.OBSERVE,
        requires_approval=True,
    )


def test_generated_capability_is_ephemeral_implemented_not_hardware_verified(
    tmp_path: Path,
) -> None:
    backend = GeneratedDeviceBackend()
    adapter = GeneratedFlipperAdapter(
        "/dev/fake",
        manifest=manifest(),
        artifact=build_artifact(tmp_path),
        serial_factory=serial_factory(backend),
    )

    descriptor = adapter.capabilities()[0]

    assert descriptor.capability_id == "generated.gpio.sample"
    assert descriptor.maturity is CapabilityMaturity.IMPLEMENTED
    assert descriptor.constraints["generated"] is True
    assert descriptor.constraints["requires_approval"] is True
    assert descriptor.quality["hardware_verified"] is False


def test_generated_first_execution_requires_explicit_approval_flag(tmp_path: Path) -> None:
    adapter = GeneratedFlipperAdapter(
        "/dev/fake",
        manifest=manifest(),
        artifact=build_artifact(tmp_path),
        serial_factory=serial_factory(GeneratedDeviceBackend()),
    )
    action = Action(
        action_id="generated-run-1",
        capability_id="generated.gpio.sample",
        target_id="lab-target",
        action_class=ActionClass.OBSERVE,
    )

    validation = adapter.validate(action)

    assert validation.valid is False
    assert "operator approval" in (validation.reason or "")


def test_generated_execution_deploys_reads_evidence_and_cleans_up(tmp_path: Path) -> None:
    backend = GeneratedDeviceBackend()
    artifact = build_artifact(tmp_path)
    adapter = GeneratedFlipperAdapter(
        "/dev/fake",
        manifest=manifest(),
        artifact=artifact,
        serial_factory=serial_factory(backend),
    )

    result = adapter.execute(approved_action())

    assert result.status is ExecutionStatus.SUCCESS
    assert result.normalized["observations"] == {"PA7": 1}
    assert result.raw["generated_app"]["artifact_sha256"] == artifact.artifact_sha256
    assert result.raw["generated_app"]["source_tree_sha256"] == artifact.source_tree_sha256
    assert generated_app_path("hpa_gen_gpio_sample") not in backend.files
    assert generated_result_path("hpa_gen_gpio_sample") not in backend.files
    cleanup = result.raw["cleanup"]
    assert cleanup == {
        "attempted": True,
        "app_removed": True,
        "result_removed": True,
        "errors": (),
    }
    assert b"storage mkdir /ext/apps/NullSquare\r" in backend.writes
    assert any(
        item.startswith(
            f"storage write_chunk {generated_app_path('hpa_gen_gpio_sample')} ".encode()
        )
        for item in backend.writes
    )
    assert not any(b"/ext/apps/GPIO/" in item for item in backend.writes)


def test_cleanup_is_reported_failed_when_device_files_persist(tmp_path: Path) -> None:
    # The device acknowledges "storage remove" but the files remain. Cleanup must not be inferred
    # from the absence of an exception: the re-stat has to surface the persistence.
    backend = GeneratedDeviceBackend(ignore_removes=True)
    adapter = GeneratedFlipperAdapter(
        "/dev/fake",
        manifest=manifest(),
        artifact=build_artifact(tmp_path),
        serial_factory=serial_factory(backend),
    )

    result = adapter.execute(approved_action())

    # The observation itself was read successfully, but cleanup is reported as failed.
    assert result.status is ExecutionStatus.SUCCESS
    cleanup = result.raw["cleanup"]
    assert cleanup["attempted"] is True
    assert cleanup["app_removed"] is False
    assert cleanup["result_removed"] is False
    assert cleanup["errors"]
    assert any("still present after removal" in message for message in cleanup["errors"])
    assert any("cleanup reported" in limitation for limitation in result.limitations)


def test_generated_runtime_clears_stale_result_before_launch(tmp_path: Path) -> None:
    result_path = generated_result_path("hpa_gen_gpio_sample")
    backend = GeneratedDeviceBackend(files={result_path: bytearray(b"stale")})
    adapter = GeneratedFlipperAdapter(
        "/dev/fake",
        manifest=manifest(),
        artifact=build_artifact(tmp_path),
        serial_factory=serial_factory(backend),
        cleanup=False,
    )

    result = adapter.execute(approved_action())

    assert result.status is ExecutionStatus.SUCCESS
    remove_command = f"storage remove {result_path}\r".encode()
    app_path = generated_app_path("hpa_gen_gpio_sample")
    launch_command = f'loader open "{app_path}"\r'.encode()
    assert backend.writes.index(remove_command) < backend.writes.index(launch_command)


def test_artifact_tamper_blocks_before_hardware_deployment(tmp_path: Path) -> None:
    backend = GeneratedDeviceBackend()
    artifact = build_artifact(tmp_path)
    artifact.artifact_path.write_bytes(b"tampered")
    adapter = GeneratedFlipperAdapter(
        "/dev/fake",
        manifest=manifest(),
        artifact=artifact,
        serial_factory=serial_factory(backend),
    )

    result = adapter.execute(approved_action())

    assert result.status is ExecutionStatus.BLOCKED
    assert "hash no longer matches" in (result.error or "")
    assert not any(item.startswith(b"storage write_chunk") for item in backend.writes)


def test_generated_runtime_refuses_to_interrupt_other_running_app(tmp_path: Path) -> None:
    backend = GeneratedDeviceBackend(running_name="NFC", auto_exit=False)
    adapter = GeneratedFlipperAdapter(
        "/dev/fake",
        manifest=manifest(),
        artifact=build_artifact(tmp_path),
        serial_factory=serial_factory(backend),
    )

    result = adapter.execute(approved_action())

    assert result.status is ExecutionStatus.FAILED
    assert "while 'NFC' is running" in (result.error or "")
    assert not any(item.startswith(b"storage write_chunk") for item in backend.writes)


def test_generated_runtime_timeout_closes_and_removes_generated_app(tmp_path: Path) -> None:
    backend = GeneratedDeviceBackend(auto_exit=False)
    ticks = iter((0.0, 0.0, 2.1))
    adapter = GeneratedFlipperAdapter(
        "/dev/fake",
        manifest=manifest(runtime_seconds=1.0),
        artifact=build_artifact(tmp_path),
        serial_factory=serial_factory(backend),
        clock=lambda: next(ticks),
        sleeper=lambda _: None,
    )

    result = adapter.execute(approved_action())

    assert result.status is ExecutionStatus.FAILED
    assert "runtime bound" in (result.error or "")
    assert backend.loader_close_count == 1
    assert generated_app_path("hpa_gen_gpio_sample") not in backend.files


def test_malformed_result_fails_and_generated_files_are_cleaned(tmp_path: Path) -> None:
    backend = GeneratedDeviceBackend(
        prepared_result=b'{"schema_version":"1","status":"success"}'
    )
    adapter = GeneratedFlipperAdapter(
        "/dev/fake",
        manifest=manifest(),
        artifact=build_artifact(tmp_path),
        serial_factory=serial_factory(backend),
    )

    result = adapter.execute(approved_action())

    assert result.status is ExecutionStatus.FAILED
    assert "observations" in (result.error or "")
    assert result.normalized == {}
    assert generated_app_path("hpa_gen_gpio_sample") not in backend.files
    assert generated_result_path("hpa_gen_gpio_sample") not in backend.files


def test_generated_path_helpers_reject_arbitrary_app_ids() -> None:
    with pytest.raises(FlipperProtocolError, match="reserved hpa_gen_"):
        generated_app_path("../../marauder")
    with pytest.raises(FlipperProtocolError, match="reserved hpa_gen_"):
        generated_result_path("esp32_wifi_marauder")
