from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import hardware_pentest.service.facade as facade_module
from hardware_pentest.core.artifact_scope import LocalArtifactScopeStore
from hardware_pentest.core.engagement_store import LocalEngagementStore
from hardware_pentest.core.models import ActionClass, Engagement, ExecutionStatus, Target
from hardware_pentest.evidence.store import LocalEvidenceStore
from hardware_pentest.service.execution import HarnessAssessmentExecutor, InstrumentSelection
from hardware_pentest.service.facade import HardwarePentestService
from hardware_pentest.service.planning import HarnessAssessmentPlanner


def test_host_artifact_route_is_additive_and_produces_evidence(tmp_path: Path) -> None:
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
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    firmware = artifact_root / "drone-fw.bin"
    content = b"DRONEFW\x00\x01payload"
    firmware.write_bytes(content)

    now = datetime.now(UTC)
    engagement = Engagement(
        engagement_id="eng-host-route",
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
        target_ids=frozenset({"drone-1"}),
        allowed_capabilities=("artifact.firmware.inspect",),
        denied_capabilities=(),
        max_action_class=ActionClass.OBSERVE,
    )
    target = Target(target_id="drone-1", description="Authorized lab drone")
    LocalEngagementStore(roots["engagement"]).save(engagement, (target,))
    LocalArtifactScopeStore(roots["artifact_scope"]).save(
        engagement_id=engagement.engagement_id,
        artifact_root=artifact_root,
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
        artifact_path="drone-fw.bin",
        assessment_id="assessment-host-route",
    )

    artifact_step = state.step("assessment-host-route:artifact.firmware.inspect.v1")
    assert artifact_step.instrument_id == "host.local"
    assert artifact_step.status.value == "ready"
    assert artifact_step.action is not None
    assert artifact_step.action.inputs == {"artifact_path": "drone-fw.bin"}

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
    evidence = LocalEvidenceStore(roots["evidence"]).records(engagement.engagement_id)
    assert len(evidence) == 1
    record = evidence[0]
    assert record.target_id == target.target_id
    assert record.capability_id == "artifact.firmware.inspect"
    assert record.instrument_id == "host.local"
    assert record.normalized_inputs == {"artifact_path": "drone-fw.bin"}
    assert record.normalized_observation["sha256"] == hashlib.sha256(content).hexdigest()


def test_service_discovery_always_reports_host_provider(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(facade_module, "serial_ports", lambda: ())
    monkeypatch.setattr(facade_module, "discover_flipper_ports", lambda: [])
    service = HardwarePentestService(
        assessment_root=tmp_path / "assessments",
        engagement_root=tmp_path / "engagements",
        evidence_root=tmp_path / "evidence",
        verification_root=tmp_path / "verification",
        preflight_root=tmp_path / "preflight",
        gate_root=tmp_path / "gates",
        implementation_root=tmp_path / "implementations",
        artifact_scope_root=tmp_path / "artifact-scopes",
    )

    result = service.hardware_discover()

    assert result["side_effects"] == "none"
    assert result["serial_ports"] == []
    assert result["flipper_candidates"] == []
    assert result["providers"][0]["identity"]["provider_id"] == "host.local"
