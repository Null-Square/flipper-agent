from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import hardware_pentest.service.execution as execution_module
from hardware_pentest.adapters.host_serial import HostSerialMetadataAdapter
from hardware_pentest.core.engagement_store import LocalEngagementStore
from hardware_pentest.core.models import Action, ActionClass, Engagement, ExecutionStatus, Target
from hardware_pentest.evidence.store import LocalEvidenceStore
from hardware_pentest.service.execution import HarnessAssessmentExecutor, InstrumentSelection
from hardware_pentest.service.gates import GateKind, LocalGateStore
from hardware_pentest.service.planning import HarnessAssessmentPlanner


def _fake_ports():
    return [
        SimpleNamespace(
            device="/dev/ttyACM0",
            description="USB Serial Device",
            manufacturer="NullSquare Lab",
            product="Demo Board CDC",
            serial_number="BOARD-001",
            vid=0x1209,
            pid=0x0001,
        )
    ]


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FakeReadOnlySerial:
    def __init__(self, clock: FakeClock, payload: bytes) -> None:
        self.clock = clock
        self.payload = bytearray(payload)
        self.closed = False
        self.write_calls = 0

    def read(self, size: int = 1) -> bytes:
        self.clock.advance(0.05)
        if not self.payload:
            return b""
        chunk = bytes(self.payload[:size])
        del self.payload[:size]
        return chunk

    def write(self, data: bytes) -> int:
        self.write_calls += 1
        raise AssertionError("read-only serial adapter must never write")

    def close(self) -> None:
        self.closed = True


def _observe_action(**overrides) -> Action:
    inputs = {
        "serial_device": "/dev/ttyACM0",
        "baudrate": 115200,
        "duration_seconds": 1.0,
        "max_bytes": 4096,
    }
    inputs.update(overrides)
    return Action(
        action_id="interface.serial.observe.v1:board-1",
        capability_id="interface.serial.observe",
        target_id="board-1",
        action_class=ActionClass.INTERACT,
        inputs=inputs,
        requires_approval=True,
    )


def test_serial_observe_is_interact_bounded_and_read_only() -> None:
    clock = FakeClock()
    stream = FakeReadOnlySerial(clock, b"boot: ready\r\n")
    factory_calls = []

    def factory(device: str, baudrate: int, timeout: float):
        factory_calls.append((device, baudrate, timeout))
        return stream

    adapter = HostSerialMetadataAdapter(
        ports_provider=_fake_ports,
        serial_factory=factory,
        clock=clock,
    )

    descriptor = next(
        item for item in adapter.capabilities() if item.capability_id == "interface.serial.observe"
    )
    assert descriptor.action_class is ActionClass.INTERACT
    assert descriptor.constraints["writes_device"] is False
    assert descriptor.constraints["operator_approval_required"] is True

    result = adapter.execute(_observe_action())

    assert result.status is ExecutionStatus.SUCCESS
    assert factory_calls == [("/dev/ttyACM0", 115200, 0.1)]
    assert stream.write_calls == 0
    assert stream.closed is True
    assert result.normalized["byte_count"] == len(b"boot: ready\r\n")
    assert result.normalized["text_preview"] == "boot: ready\r\n"
    assert result.raw["writes_performed"] == 0


def test_serial_observe_enforces_byte_ceiling_and_closes() -> None:
    clock = FakeClock()
    stream = FakeReadOnlySerial(clock, b"abcdefghij")
    adapter = HostSerialMetadataAdapter(
        ports_provider=_fake_ports,
        serial_factory=lambda _device, _baudrate, _timeout: stream,
        clock=clock,
    )

    result = adapter.execute(_observe_action(max_bytes=5))

    assert result.status is ExecutionStatus.SUCCESS
    assert result.normalized["byte_count"] == 5
    assert result.normalized["text_preview"] == "abcde"
    assert result.normalized["byte_ceiling_hit"] is True
    assert stream.closed is True
    assert stream.write_calls == 0


def test_serial_observe_rejects_invalid_bounds_before_open() -> None:
    opened = False

    def factory(_device: str, _baudrate: int, _timeout: float):
        nonlocal opened
        opened = True
        raise AssertionError("invalid action must not open the port")

    adapter = HostSerialMetadataAdapter(ports_provider=_fake_ports, serial_factory=factory)

    assert adapter.validate(_observe_action(baudrate=299)).valid is False
    assert adapter.validate(_observe_action(baudrate=1_000_001)).valid is False
    assert adapter.validate(_observe_action(duration_seconds=5.1)).valid is False
    assert adapter.validate(_observe_action(max_bytes=65537)).valid is False
    assert adapter.validate(_observe_action(serial_device="/dev/not-present")).valid is False
    assert opened is False


def test_serial_observe_requires_gate_and_records_evidence(tmp_path: Path, monkeypatch) -> None:
    roots = {
        "assessment": tmp_path / "assessments",
        "engagement": tmp_path / "engagements",
        "evidence": tmp_path / "evidence",
        "verification": tmp_path / "verification",
        "preflight": tmp_path / "preflight",
        "gate": tmp_path / "gates",
        "implementation": tmp_path / "implementations",
        "artifact_scope": tmp_path / "artifact-scopes",
    }
    now = datetime.now(UTC)
    engagement = Engagement(
        engagement_id="eng-serial-observe",
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
        target_ids=frozenset({"board-1"}),
        allowed_capabilities=("interface.serial.inspect", "interface.serial.observe"),
        denied_capabilities=(),
        max_action_class=ActionClass.INTERACT,
    )
    target = Target(target_id="board-1", description="Authorized USB development board")
    LocalEngagementStore(roots["engagement"]).save(engagement, (target,))

    clock = FakeClock()
    streams: list[FakeReadOnlySerial] = []

    def adapter_factory():
        def serial_factory(_device: str, _baudrate: int, _timeout: float):
            stream = FakeReadOnlySerial(clock, b"READY\r\n")
            streams.append(stream)
            return stream

        return HostSerialMetadataAdapter(
            ports_provider=_fake_ports,
            serial_factory=serial_factory,
            clock=clock,
        )

    monkeypatch.setattr(execution_module, "serial_discovery_available", lambda: True)
    monkeypatch.setattr(execution_module, "HostSerialMetadataAdapter", adapter_factory)

    planner = HarnessAssessmentPlanner(
        assessment_root=roots["assessment"],
        engagement_root=roots["engagement"],
        verification_root=roots["verification"],
        preflight_root=roots["preflight"],
        implementation_root=roots["implementation"],
        artifact_scope_root=roots["artifact_scope"],
    )
    state = planner.create(
        engagement_id=engagement.engagement_id,
        target_id=target.target_id,
        instrument=InstrumentSelection(backend="simulator"),
        serial_device="/dev/ttyACM0",
        serial_baudrate=115200,
        serial_duration_seconds=1.0,
        serial_max_bytes=64,
        assessment_id="assessment-serial-observe",
    )

    inspect_step = state.step("assessment-serial-observe:interface.serial.inspect.v1")
    observe_step = state.step("assessment-serial-observe:interface.serial.observe.v1")
    assert inspect_step.status.value == "ready"
    assert observe_step.status.value == "approval_required"
    assert observe_step.instrument_id == "host.local"
    assert observe_step.action is not None
    assert observe_step.action.requires_approval is True

    executor = HarnessAssessmentExecutor(
        assessment_root=roots["assessment"],
        engagement_root=roots["engagement"],
        evidence_root=roots["evidence"],
        verification_root=roots["verification"],
        preflight_root=roots["preflight"],
        gate_root=roots["gate"],
        implementation_root=roots["implementation"],
        artifact_scope_root=roots["artifact_scope"],
    )

    first = executor.execute_next(state.assessment_id)
    assert first["execution_status"] == ExecutionStatus.SUCCESS.value

    blocked = executor.execute_next(state.assessment_id)
    assert blocked["paused"] is True
    assert blocked["policy"]["decision"] == "require_approval"
    assert streams == []

    LocalGateStore(roots["gate"]).grant(
        assessment_id=state.assessment_id,
        step_id=observe_step.step_id,
        kind=GateKind.APPROVAL,
    )
    captured = executor.execute_next(state.assessment_id)
    assert captured["execution_status"] == ExecutionStatus.SUCCESS.value
    assert len(streams) == 1
    assert streams[0].closed is True
    assert streams[0].write_calls == 0

    records = LocalEvidenceStore(roots["evidence"]).records(engagement.engagement_id)
    observe_records = [
        record for record in records if record.capability_id == "interface.serial.observe"
    ]
    assert len(observe_records) == 1
    record = observe_records[0]
    assert record.target_id == "board-1"
    assert record.instrument_id == "host.local"
    assert record.normalized_observation["byte_count"] == len(b"READY\r\n")
    assert record.normalized_observation["text_preview"] == "READY\r\n"
