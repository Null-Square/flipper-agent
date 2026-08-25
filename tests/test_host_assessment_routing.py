from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import hardware_pentest.service.execution as execution_module
import hardware_pentest.service.facade as facade_module
from hardware_pentest.core.artifact_scope import LocalArtifactScopeStore
from hardware_pentest.core.engagement_store import LocalEngagementStore
from hardware_pentest.core.models import (
    ActionClass,
    CapabilityDescriptor,
    CapabilityMaturity,
    Engagement,
    ExecutionStatus,
    InstrumentIdentity,
    Target,
)
from hardware_pentest.evidence.store import LocalEvidenceStore
from hardware_pentest.preflight.store import LocalPreflightStore
from hardware_pentest.service.execution import HarnessAssessmentExecutor, InstrumentSelection
from hardware_pentest.service.facade import HardwarePentestService
from hardware_pentest.service.planning import HarnessAssessmentPlanner
from hardware_pentest.verification import LocalVerificationStore


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


class _FakeFlipperAdapter:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def probe(self) -> InstrumentIdentity:
        return InstrumentIdentity(
            instrument_id="flipper.fake",
            kind="flipper",
            model="Flipper Zero",
            transport="usb",
            firmware_version="test",
            adapter_version="test",
        )

    def capabilities(self) -> list[CapabilityDescriptor]:
        return [
            CapabilityDescriptor(
                capability_id="infrared.observe",
                description="Fake Flipper observation route",
                action_class=ActionClass.OBSERVE,
                maturity=CapabilityMaturity.IMPLEMENTED,
                instrument_id="flipper.fake",
            )
        ]


def test_flipper_selection_keeps_host_routes(tmp_path: Path, monkeypatch) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    (artifact_root / "fw.bin").write_bytes(b"firmware")
    scopes = LocalArtifactScopeStore(tmp_path / "artifact-scopes")
    scopes.save(engagement_id="eng-flipper", artifact_root=artifact_root)

    monkeypatch.setattr(
        execution_module,
        "resolve_flipper_serial_port",
        lambda explicit_port=None: SimpleNamespace(
            device="/dev/fake-flipper",
            serial_number="fake-serial",
        ),
    )
    monkeypatch.setattr(execution_module, "FlipperAdapter", _FakeFlipperAdapter)

    registry = execution_module.build_registry(
        InstrumentSelection(backend="flipper"),
        verification=LocalVerificationStore(tmp_path / "verification"),
        preflight=LocalPreflightStore(tmp_path / "preflight"),
        implementations=None,
        engagement_id="eng-flipper",
        artifact_scopes=scopes,
    )

    assert registry.instruments() == ["flipper.fake", "host.local"]
    assert registry.choose("artifact.firmware.inspect").capability.instrument_id == "host.local"
    assert registry.choose("infrared.observe").capability.instrument_id == "flipper.fake"
