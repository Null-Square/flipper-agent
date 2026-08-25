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


def _serial_action(device: str = "/dev/ttyACM0") -> Action:
    return Action(
        action_id="interface.serial.inspect.v1:target-1",
        capability_id="interface.serial.inspect",
        target_id="target-1",
        action_class=ActionClass.OBSERVE,
        inputs={"serial_device": device},
    )


def test_serial_adapter_returns_metadata_without_opening_device() -> None:
    adapter = HostSerialMetadataAdapter(ports_provider=_fake_ports)

    result = adapter.execute(_serial_action())

    assert result.status is ExecutionStatus.SUCCESS
    assert result.instrument_id == "host.local"
    assert result.raw == {
        "inspection": "serial-discovery-metadata",
        "device_opened": False,
    }
    assert result.normalized == {
        "device": "/dev/ttyACM0",
        "description": "USB Serial Device",
        "manufacturer": "NullSquare Lab",
        "product": "Demo Board CDC",
        "serial_number": "BOARD-001",
        "vid": 0x1209,
        "pid": 0x0001,
    }
    assert adapter.capabilities()[0].constraints["opens_device"] is False
    assert adapter.capabilities()[0].constraints["reads_device"] is False
    assert adapter.capabilities()[0].constraints["writes_device"] is False


def test_serial_adapter_rejects_unknown_candidate() -> None:
    adapter = HostSerialMetadataAdapter(ports_provider=_fake_ports)

    validation = adapter.validate(_serial_action("/dev/not-present"))

    assert validation.valid is False
    assert "not present" in str(validation.reason)


def test_serial_assessment_routes_to_host_and_records_target_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
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
        engagement_id="eng-serial",
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
        target_ids=frozenset({"board-1"}),
        allowed_capabilities=("interface.serial.inspect",),
        denied_capabilities=(),
        max_action_class=ActionClass.OBSERVE,
    )
    target = Target(target_id="board-1", description="Authorized USB development board")
    LocalEngagementStore(roots["engagement"]).save(engagement, (target,))

    monkeypatch.setattr(execution_module, "serial_discovery_available", lambda: True)
    monkeypatch.setattr(
        execution_module,
        "HostSerialMetadataAdapter",
        lambda: HostSerialMetadataAdapter(ports_provider=_fake_ports),
    )

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
        assessment_id="assessment-serial",
    )

    step = state.step("assessment-serial:interface.serial.inspect.v1")
    assert step.instrument_id == "host.local"
    assert step.status.value == "ready"
    assert step.action is not None
    assert step.action.inputs == {"serial_device": "/dev/ttyACM0"}

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
    summary = executor.execute_next(
        state.assessment_id,
        instrument=InstrumentSelection(backend="simulator"),
    )

    assert summary["execution_status"] == ExecutionStatus.SUCCESS.value
    records = LocalEvidenceStore(roots["evidence"]).records(engagement.engagement_id)
    assert len(records) == 1
    record = records[0]
    assert record.target_id == "board-1"
    assert record.capability_id == "interface.serial.inspect"
    assert record.instrument_id == "host.local"
    assert record.normalized_inputs == {"serial_device": "/dev/ttyACM0"}
    assert record.normalized_observation["serial_number"] == "BOARD-001"
    assert record.normalized_observation["vid"] == 0x1209
    assert record.normalized_observation["pid"] == 0x0001


def test_missing_serial_backend_becomes_capability_gap(tmp_path: Path, monkeypatch) -> None:
    now = datetime.now(UTC)
    engagement = Engagement(
        engagement_id="eng-no-serial",
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
        target_ids=frozenset({"board-1"}),
        allowed_capabilities=("interface.serial.inspect",),
        denied_capabilities=(),
        max_action_class=ActionClass.OBSERVE,
    )
    target = Target(target_id="board-1", description="Authorized USB development board")
    engagement_root = tmp_path / "engagements"
    LocalEngagementStore(engagement_root).save(engagement, (target,))

    monkeypatch.setattr(execution_module, "serial_discovery_available", lambda: False)
    planner = HarnessAssessmentPlanner(
        assessment_root=tmp_path / "assessments",
        engagement_root=engagement_root,
        verification_root=tmp_path / "verification",
        preflight_root=tmp_path / "preflight",
        implementation_root=tmp_path / "implementations",
        artifact_scope_root=tmp_path / "artifact-scopes",
    )
    state = planner.create(
        engagement_id=engagement.engagement_id,
        target_id=target.target_id,
        instrument=InstrumentSelection(backend="simulator"),
        serial_device="/dev/ttyACM0",
        assessment_id="assessment-no-serial",
    )

    step = state.step("assessment-no-serial:interface.serial.inspect.v1")
    assert step.status.value == "capability_gap"
    assert step.required_capability == "interface.serial.inspect"
    assert step.instrument_id is None
