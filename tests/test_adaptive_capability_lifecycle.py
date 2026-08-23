from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from hardware_pentest.adapters.simulated import SimulatedAdapter
from hardware_pentest.assessment import (
    AssessmentPlanner,
    CapabilityGapRefresher,
    Finding,
    FindingStatus,
    LocalAssessmentStore,
    StepStatus,
    TestCase,
    adaptive_hardware_test_catalog,
)
from hardware_pentest.core.hardware import (
    HardwareDescriptor,
    HardwareDirection,
    HardwareIdentity,
    HardwareInterface,
)
from hardware_pentest.core.models import (
    ActionClass,
    CapabilityMaturity,
    Engagement,
    InstrumentIdentity,
    Observation,
    Target,
)
from hardware_pentest.core.registry import CapabilityRegistry
from hardware_pentest.synthesis.hil import ImplementationHILRecorder
from hardware_pentest.synthesis.models import CapabilityImplementationRecord
from hardware_pentest.synthesis.store import LocalCapabilityImplementationStore
from hardware_pentest.verification.store import LocalVerificationStore


def _engagement(*, denied: tuple[str, ...] = ()) -> Engagement:
    now = datetime.now(UTC)
    return Engagement(
        engagement_id="adaptive-lab",
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(hours=1),
        target_ids=frozenset({"target-a"}),
        allowed_capabilities=("internal.*",),
        denied_capabilities=denied,
        max_action_class=ActionClass.OBSERVE,
    )


def _target() -> Target:
    return Target(target_id="target-a", description="Operator-owned UART fixture")


def _registry(*capabilities: str) -> CapabilityRegistry:
    registry = CapabilityRegistry()
    if capabilities:
        registry.register(
            SimulatedAdapter(
                scripted_results={capability: {} for capability in capabilities},
                capability_classes={capability: ActionClass.OBSERVE for capability in capabilities},
            )
        )
    return registry


def test_capability_gap_preserves_normalized_action_and_round_trips(tmp_path) -> None:
    test_case = adaptive_hardware_test_catalog()[0]
    state = AssessmentPlanner().plan(
        engagement=_engagement(),
        target=_target(),
        registry=_registry(),
        test_cases=(test_case,),
        assessment_id="assessment-gap",
    )
    gap = state.steps[0]

    assert gap.status is StepStatus.CAPABILITY_GAP
    assert gap.action is not None
    assert gap.action.capability_id == "internal.uart.autodetect"
    assert gap.action.inputs == {
        "duration_seconds": 5.0,
        "max_sample_bytes": 2048,
        "max_candidates": 8,
    }
    assert gap.action.requires_human_action is True

    store = LocalAssessmentStore(tmp_path / "assessments")
    store.save(state)
    assert store.load("assessment-gap") == state


def test_adaptive_uart_gap_refreshes_to_human_action_without_execution() -> None:
    test_case = adaptive_hardware_test_catalog()[0]
    state = AssessmentPlanner().plan(
        engagement=_engagement(),
        target=_target(),
        registry=_registry(),
        test_cases=(test_case,),
        assessment_id="assessment-uart",
    )

    refreshed = CapabilityGapRefresher().refresh(
        state,
        engagement=_engagement(),
        registry=_registry("internal.uart.autodetect"),
    )

    step = refreshed.steps[0]
    assert step.status is StepStatus.HUMAN_ACTION_REQUIRED
    assert step.instrument_id == "simulator-1"
    assert step.action == state.steps[0].action
    assert step.evidence_ids == ()


def test_gap_refresh_can_become_ready_and_preserves_domain_history() -> None:
    test_case = TestCase(
        test_case_id="adaptive.readonly.v1",
        title="Adaptive read-only helper",
        purpose="Read a bounded prepared signal",
        required_capability="internal.custom.observe",
        action_class=ActionClass.OBSERVE,
        prerequisites=(),
        expected_evidence=("bounded sample",),
        stop_conditions=("sample complete",),
        result_rules=("do not infer beyond evidence",),
        default_inputs={"samples": 4},
    )
    state = AssessmentPlanner().plan(
        engagement=_engagement(),
        target=_target(),
        registry=_registry(),
        test_cases=(test_case,),
        assessment_id="assessment-ready",
    )
    observation = Observation(
        observation_id="obs-prior",
        evidence_ids=("ev-prior",),
        statement="Prior bounded observation",
        confidence="high",
    )
    finding = Finding(
        finding_id="finding-prior",
        title="Prior candidate",
        statement="Prior evidence remains attached",
        status=FindingStatus.CANDIDATE,
        evidence_ids=("ev-prior",),
        observation_ids=("obs-prior",),
    )
    state = replace(state, observations=(observation,), findings=(finding,))

    refreshed = CapabilityGapRefresher().refresh(
        state,
        engagement=_engagement(),
        registry=_registry("internal.custom.observe"),
    )

    assert refreshed.steps[0].status is StepStatus.READY
    assert refreshed.steps[0].action is not None
    assert refreshed.steps[0].action.inputs == {"samples": 4}
    assert refreshed.created_at == state.created_at
    assert refreshed.observations == state.observations
    assert refreshed.findings == state.findings


def test_refresh_re_evaluates_policy_instead_of_inheriting_old_allow() -> None:
    test_case = TestCase(
        test_case_id="adaptive.policy.v1",
        title="Policy refresh test",
        purpose="Verify fresh policy evaluation",
        required_capability="internal.custom.observe",
        action_class=ActionClass.OBSERVE,
        prerequisites=(),
        expected_evidence=(),
        stop_conditions=(),
        result_rules=(),
    )
    state = AssessmentPlanner().plan(
        engagement=_engagement(),
        target=_target(),
        registry=_registry(),
        test_cases=(test_case,),
        assessment_id="assessment-policy",
    )

    refreshed = CapabilityGapRefresher().refresh(
        state,
        engagement=_engagement(denied=("internal.custom.observe",)),
        registry=_registry("internal.custom.observe"),
    )

    assert refreshed.steps[0].status is StepStatus.BLOCKED
    assert "deny" in refreshed.steps[0].reason.lower()


def _descriptor(provider_id: str) -> HardwareDescriptor:
    return HardwareDescriptor(
        identity=HardwareIdentity(
            provider_id=provider_id,
            kind="flipper",
            model="Flipper Zero",
            transport="usb-cdc",
            firmware_version="1.4.2",
            provider_version="0.7.0-dev",
        ),
        architecture="stm32wb55rg",
        interfaces=(
            HardwareInterface(
                interface_id="external.uart",
                kind="uart",
                direction=HardwareDirection.INPUT,
            ),
        ),
        artifact_types=("fap",),
    )


def _identity(provider_id: str) -> InstrumentIdentity:
    return InstrumentIdentity(
        instrument_id=provider_id,
        kind="flipper",
        model="Flipper Zero",
        transport="usb-cdc",
        firmware_version="1.4.2",
        adapter_version="0.7.0-dev",
    )


def test_hil_recorder_binds_evidence_to_exact_implementation_and_descriptor(tmp_path) -> None:
    provider_id = "flipper:serial-123"
    descriptor = _descriptor(provider_id)
    artifact = tmp_path / "uart-helper.fap"
    artifact.write_bytes(b"bounded generated fap fixture")
    artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    implementation = CapabilityImplementationRecord(
        request_id="request-uart",
        capability_id="internal.uart.autodetect",
        target_id="target-a",
        backend_id="flipper-fap",
        provider_id=provider_id,
        hardware_descriptor_sha256=descriptor.fingerprint,
        artifact_type="fap",
        artifact_sha256=artifact_sha,
        action_class=ActionClass.OBSERVE,
        required_interfaces=("uart",),
        build_provider_id="ufbt",
        build_provider_version="0.2-test",
        deployment_provider_id="flipper-storage-loader",
        evidence_channel_ids=("generated-app-json",),
        maturity=CapabilityMaturity.IMPLEMENTED,
    )
    implementations = LocalCapabilityImplementationStore(tmp_path / "implementations")
    stored = implementations.save(implementation, artifact_path=artifact)
    evidence = tmp_path / "physical-evidence.json"
    evidence.write_text('{"fixture":"operator-supplied"}\n', encoding="utf-8")
    verification = LocalVerificationStore(tmp_path / "verification")
    recorder = ImplementationHILRecorder(
        implementations=implementations,
        verification=verification,
    )

    with pytest.raises(PermissionError, match="operator confirmation"):
        recorder.record(
            implementation_id=stored.record.implementation_id,
            descriptor=descriptor,
            identity=_identity(provider_id),
            evidence_path=evidence,
            passed=True,
            operator_confirmed=False,
        )

    record = recorder.record(
        implementation_id=stored.record.implementation_id,
        descriptor=descriptor,
        identity=_identity(provider_id),
        evidence_path=evidence,
        passed=True,
        operator_confirmed=True,
    )

    assert record.implementation_bound is True
    assert record.implementation_id == stored.record.implementation_id
    assert record.implementation_artifact_sha256 == artifact_sha
    assert record.hardware_descriptor_sha256 == descriptor.fingerprint
    assert verification.evidence_is_intact(record) is True
    assert verification.verified_implementation(
        _identity(provider_id),
        capability_id="internal.uart.autodetect",
        implementation_id=stored.record.implementation_id,
        implementation_artifact_sha256=artifact_sha,
        hardware_descriptor_sha256=descriptor.fingerprint,
    ) == record


def test_hil_recorder_rejects_descriptor_drift(tmp_path) -> None:
    provider_id = "flipper:serial-123"
    descriptor = _descriptor(provider_id)
    artifact = tmp_path / "helper.fap"
    artifact.write_bytes(b"artifact")
    implementation = CapabilityImplementationRecord(
        request_id="request-drift",
        capability_id="internal.uart.autodetect",
        target_id="target-a",
        backend_id="flipper-fap",
        provider_id=provider_id,
        hardware_descriptor_sha256=descriptor.fingerprint,
        artifact_type="fap",
        artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
        action_class=ActionClass.OBSERVE,
        required_interfaces=("uart",),
        build_provider_id="ufbt",
        build_provider_version=None,
        deployment_provider_id="flipper-storage-loader",
        evidence_channel_ids=("generated-app-json",),
    )
    implementations = LocalCapabilityImplementationStore(tmp_path / "implementations")
    stored = implementations.save(implementation, artifact_path=artifact)
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")
    drifted = replace(descriptor, architecture="different-mcu")

    with pytest.raises(ValueError, match="descriptor"):
        ImplementationHILRecorder(
            implementations=implementations,
            verification=LocalVerificationStore(tmp_path / "verification"),
        ).record(
            implementation_id=stored.record.implementation_id,
            descriptor=drifted,
            identity=_identity(provider_id),
            evidence_path=evidence,
            passed=True,
            operator_confirmed=True,
        )
