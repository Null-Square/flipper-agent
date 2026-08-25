from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import hardware_pentest.service.candidate_facade as candidate_facade_module
import hardware_pentest.service.execution as execution_module
from hardware_pentest.adapters.host_usb import HostUsbMetadataAdapter
from hardware_pentest.core.engagement_store import LocalEngagementStore
from hardware_pentest.core.models import Action, ActionClass, Engagement, ExecutionStatus, Target
from hardware_pentest.evidence.store import LocalEvidenceStore
from hardware_pentest.preflight.usb import metadata_for_usb_candidate, usb_devices
from hardware_pentest.service import HardwarePentestService
from hardware_pentest.service.execution import HarnessAssessmentExecutor, InstrumentSelection
from hardware_pentest.service.planning import HarnessAssessmentPlanner


def _fake_usb_devices():
    return [
        SimpleNamespace(
            bus=1,
            address=7,
            port_number=3,
            port_numbers=(2, 3),
            idVendor=0x1209,
            idProduct=0x0001,
            bDeviceClass=2,
            bDeviceSubClass=0,
            bDeviceProtocol=0,
            speed=3,
        ),
        SimpleNamespace(
            bus=1,
            address=4,
            port_number=2,
            port_numbers=(2, 2),
            idVendor=0x2E8A,
            idProduct=0x000A,
            bDeviceClass=0,
            bDeviceSubClass=0,
            bDeviceProtocol=0,
            speed=3,
        ),
    ]


def _candidate_id() -> str:
    return "usb:1:7:2.3:1209:0001"


def _inspect_action(candidate_id: str | None = None) -> Action:
    return Action(
        action_id="interface.usb.inspect.v1:board-1",
        capability_id="interface.usb.inspect",
        target_id="board-1",
        action_class=ActionClass.OBSERVE,
        inputs={"usb_candidate_id": candidate_id or _candidate_id()},
    )


def test_usb_discovery_normalizes_and_sorts_bounded_candidates() -> None:
    candidates = usb_devices(_fake_usb_devices)

    assert [item.candidate_id for item in candidates] == [
        "usb:1:4:2.2:2e8a:000a",
        "usb:1:7:2.3:1209:0001",
    ]
    selected = metadata_for_usb_candidate(_candidate_id(), _fake_usb_devices)
    assert selected is not None
    assert selected.vid == 0x1209
    assert selected.pid == 0x0001
    assert selected.device_class == 2
    assert selected.port_numbers == (2, 3)


def test_usb_adapter_is_metadata_only_and_never_exposes_active_usb_operations() -> None:
    adapter = HostUsbMetadataAdapter(enumerator=_fake_usb_devices)

    descriptors = {item.capability_id: item for item in adapter.capabilities()}

    assert set(descriptors) == {"interface.usb.enumerate", "interface.usb.inspect"}
    for descriptor in descriptors.values():
        assert descriptor.action_class is ActionClass.OBSERVE
        assert descriptor.instrument_id == "host.local"
        assert descriptor.constraints["opens_device"] is False
        assert descriptor.constraints["control_transfers"] is False
        assert descriptor.constraints["endpoint_reads"] is False
        assert descriptor.constraints["endpoint_writes"] is False
        assert descriptor.constraints["driver_detach"] is False
        assert descriptor.constraints["device_reset"] is False
        assert descriptor.constraints["string_descriptor_reads"] is False
        assert descriptor.constraints["raw_usb_passthrough"] is False


def test_usb_inspect_requires_an_exact_current_candidate() -> None:
    adapter = HostUsbMetadataAdapter(enumerator=_fake_usb_devices)

    result = adapter.execute(_inspect_action())
    stale = adapter.execute(_inspect_action("usb:9:9:9:ffff:ffff"))

    assert result.status is ExecutionStatus.SUCCESS
    assert result.instrument_id == "host.local"
    assert result.normalized["candidate_id"] == _candidate_id()
    assert result.normalized["vid"] == 0x1209
    assert result.raw == {
        "inspection": "usb-enumeration-candidate",
        "device_opened": False,
        "control_transfers": 0,
        "endpoint_io": 0,
    }
    assert stale.status is ExecutionStatus.FAILED
    assert "not present in discovery" in str(stale.error)


def test_usb_enumerate_returns_bounded_current_metadata() -> None:
    adapter = HostUsbMetadataAdapter(enumerator=_fake_usb_devices)
    action = Action(
        action_id="interface.usb.enumerate.v1:board-1",
        capability_id="interface.usb.enumerate",
        target_id="board-1",
        action_class=ActionClass.OBSERVE,
        inputs={},
    )

    result = adapter.execute(action)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.normalized["candidate_count"] == 2
    assert len(result.normalized["candidates"]) == 2
    assert result.raw["device_opened"] is False


def test_usb_assessment_routes_to_host_and_produces_evidence(tmp_path: Path, monkeypatch) -> None:
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
        engagement_id="eng-usb",
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
        target_ids=frozenset({"board-1"}),
        allowed_capabilities=("interface.usb.inspect",),
        denied_capabilities=(),
        max_action_class=ActionClass.OBSERVE,
    )
    target = Target(target_id="board-1", description="Authorized USB development board")
    LocalEngagementStore(roots["engagement"]).save(engagement, (target,))

    monkeypatch.setattr(execution_module, "usb_discovery_available", lambda: True)
    monkeypatch.setattr(
        execution_module,
        "HostUsbMetadataAdapter",
        lambda: HostUsbMetadataAdapter(enumerator=_fake_usb_devices),
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
        usb_candidate_id=_candidate_id(),
        assessment_id="assessment-usb",
    )

    step = state.step("assessment-usb:interface.usb.inspect.v1")
    assert step.status.value == "ready"
    assert step.instrument_id == "host.local"
    assert step.action is not None
    assert step.action.inputs == {"usb_candidate_id": _candidate_id()}

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
    result = executor.execute_next(state.assessment_id)

    assert result["execution_status"] == ExecutionStatus.SUCCESS.value
    records = LocalEvidenceStore(roots["evidence"]).records(engagement.engagement_id)
    usb_records = [record for record in records if record.capability_id == "interface.usb.inspect"]
    assert len(usb_records) == 1
    record = usb_records[0]
    assert record.target_id == "board-1"
    assert record.instrument_id == "host.local"
    assert record.normalized_observation["candidate_id"] == _candidate_id()


def test_missing_usb_backend_becomes_capability_gap(tmp_path: Path, monkeypatch) -> None:
    roots = {
        "assessment": tmp_path / "assessments",
        "engagement": tmp_path / "engagements",
        "verification": tmp_path / "verification",
        "preflight": tmp_path / "preflight",
        "implementation": tmp_path / "implementations",
        "artifact_scope": tmp_path / "artifact-scopes",
    }
    now = datetime.now(UTC)
    engagement = Engagement(
        engagement_id="eng-usb-gap",
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
        target_ids=frozenset({"board-1"}),
        allowed_capabilities=("interface.usb.inspect",),
        denied_capabilities=(),
        max_action_class=ActionClass.OBSERVE,
    )
    target = Target(target_id="board-1", description="Authorized USB board")
    LocalEngagementStore(roots["engagement"]).save(engagement, (target,))
    monkeypatch.setattr(execution_module, "usb_discovery_available", lambda: False)

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
        usb_candidate_id=_candidate_id(),
        assessment_id="assessment-usb-gap",
    )

    step = state.step("assessment-usb-gap:interface.usb.inspect.v1")
    assert step.status.value == "capability_gap"
    assert step.required_capability == "interface.usb.inspect"
    assert step.instrument_id is None


def test_service_discovery_exposes_usb_candidates_without_active_operations(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(candidate_facade_module, "usb_discovery_available", lambda: True)
    monkeypatch.setattr(
        candidate_facade_module,
        "usb_devices",
        lambda: usb_devices(_fake_usb_devices),
    )
    service = HardwarePentestService(
        assessment_root=tmp_path / "assessments",
        engagement_root=tmp_path / "engagements",
        evidence_root=tmp_path / "evidence",
        verification_root=tmp_path / "verification",
        preflight_root=tmp_path / "preflight",
        gate_root=tmp_path / "gates",
        implementation_root=tmp_path / "implementations",
        artifact_scope_root=tmp_path / "artifact-scopes",
        generated_project_root=tmp_path / "generated",
    )

    result = service.hardware_discover()

    assert result["side_effects"] == "none"
    assert result["usb_discovery_available"] is True
    assert len(result["usb_candidates"]) == 2
    assert result["usb_candidates"][1]["candidate_id"] == _candidate_id()
