from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hardware_pentest.adapters.simulated import SimulatedAdapter
from hardware_pentest.assessment import AssessmentPlanner, AssessmentRunner, LocalAssessmentStore
from hardware_pentest.assessment.models import AssessmentStatus, StepStatus, TestCase
from hardware_pentest.core.models import (
    ActionClass,
    CapabilityMaturity,
    Engagement,
    Observation,
    Target,
)
from hardware_pentest.core.registry import CapabilityRegistry
from hardware_pentest.synthesis import (
    CapabilityImplementationRecord,
    LocalCapabilityImplementationStore,
)


def _implementation(artifact_sha256: str) -> CapabilityImplementationRecord:
    return CapabilityImplementationRecord(
        request_id="req-uart-1",
        capability_id="internal.uart.autodetect",
        target_id="camera-1",
        backend_id="flipper-fap-v1",
        provider_id="flipper:LAB123",
        hardware_descriptor_sha256="a" * 64,
        artifact_type="fap",
        artifact_sha256=artifact_sha256,
        action_class=ActionClass.OBSERVE,
        required_interfaces=("uart",),
        build_provider_id="ufbt",
        build_provider_version="ufbt 0.2-test",
        deployment_provider_id="flipper-generated-fap",
        evidence_channel_ids=("generated-app-json",),
        maturity=CapabilityMaturity.IMPLEMENTED,
        limitations=("Needs HIL verification",),
    )


def test_implementation_store_survives_process_restart_and_rechecks_artifact(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "generated.fap"
    artifact.write_bytes(b"compiled-uart-helper")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    record = _implementation(digest)
    root = tmp_path / "implementations"

    first = LocalCapabilityImplementationStore(root)
    saved = first.save(
        record,
        artifact_path=artifact,
        backend_payload={
            "manifest": {"app_id": "hpa_gen_uart_autodetect"},
            "build": {"source_sha256": "b" * 64},
        },
    )

    second = LocalCapabilityImplementationStore(root)
    restored = second.load(record.implementation_id)

    assert saved.record == record
    assert restored.record == record
    assert restored.artifact_path.read_bytes() == b"compiled-uart-helper"
    assert restored.backend_payload["manifest"]["app_id"] == "hpa_gen_uart_autodetect"
    matches = second.find("internal.uart.autodetect")
    assert matches[0].record.implementation_id == record.implementation_id


def test_implementation_store_detects_artifact_tampering(tmp_path: Path) -> None:
    artifact = tmp_path / "generated.fap"
    artifact.write_bytes(b"trusted")
    record = _implementation(hashlib.sha256(b"trusted").hexdigest())
    store = LocalCapabilityImplementationStore(tmp_path / "store")
    saved = store.save(record, artifact_path=artifact)

    saved.artifact_path.write_bytes(b"tampered")

    with pytest.raises(ValueError, match="artifact integrity"):
        store.load(record.implementation_id)


def test_implementation_store_detects_metadata_tampering(tmp_path: Path) -> None:
    artifact = tmp_path / "generated.fap"
    artifact.write_bytes(b"trusted")
    record = _implementation(hashlib.sha256(b"trusted").hexdigest())
    store = LocalCapabilityImplementationStore(tmp_path / "store")
    store.save(record, artifact_path=artifact)

    record_file = next((tmp_path / "store" / "records").glob("*.json"))
    payload = json.loads(record_file.read_text(encoding="utf-8"))
    payload["record"]["capability_id"] = "changed.capability"
    record_file.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="metadata integrity"):
        store.load(record.implementation_id)


def _engagement(
    *,
    denied_capabilities: tuple[str, ...] = (),
) -> Engagement:
    now = datetime.now(UTC)
    return Engagement(
        engagement_id="gap-lab",
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(hours=1),
        target_ids=frozenset({"camera-1"}),
        allowed_capabilities=("internal.uart.*",),
        denied_capabilities=denied_capabilities,
        max_action_class=ActionClass.OBSERVE,
    )


def _uart_test() -> TestCase:
    return TestCase(
        test_case_id="lab.uart.autodetect.v1",
        title="Autodetect exposed UART",
        purpose="Characterize an operator-prepared UART-like header.",
        required_capability="internal.uart.autodetect",
        action_class=ActionClass.OBSERVE,
        prerequisites=("Target is authorized",),
        expected_evidence=("Candidate baud/framing observations",),
        stop_conditions=("Observation window expires",),
        result_rules=("No readable signal is inconclusive",),
        default_inputs={"fixture_profile": "uart-rx-only"},
    )


def _implemented_uart_registry() -> CapabilityRegistry:
    implemented = CapabilityRegistry()
    implemented.register(
        SimulatedAdapter(
            scripted_results={"internal.uart.autodetect": {}},
            capability_classes={"internal.uart.autodetect": ActionClass.OBSERVE},
        )
    )
    return implemented


def test_missing_implementation_persists_intended_action_and_pauses(tmp_path: Path) -> None:
    state = AssessmentPlanner().plan(
        engagement=_engagement(),
        target=Target("camera-1", "Lab camera"),
        registry=CapabilityRegistry(),
        test_cases=(_uart_test(),),
        assessment_id="gap-assessment",
    )

    step = state.steps[0]
    assert step.status is StepStatus.CAPABILITY_GAP
    assert step.required_capability == "internal.uart.autodetect"
    assert step.action is not None
    assert step.action.inputs == {"fixture_profile": "uart-rx-only"}
    assert step.executable is False

    class ForbiddenExecutor:
        def execute(self, *args, **kwargs):
            raise AssertionError("capability gap must pause before execution")

    store = LocalAssessmentStore(tmp_path / "assessments")
    store.save(state)
    restored = store.load("gap-assessment")
    assert restored.steps[0].action == step.action

    result = AssessmentRunner(executor=ForbiddenExecutor(), store=store).run_next(
        _engagement(),
        restored,
    )

    assert result.paused is True
    assert result.state.status is AssessmentStatus.CAPABILITY_GAP
    assert "internal.uart.autodetect" in (result.reason or "")
    assert store.load("gap-assessment").status is AssessmentStatus.CAPABILITY_GAP


def test_in_place_gap_refresh_preserves_state_and_resolves_verified_route() -> None:
    created_at = datetime(2026, 8, 23, 8, 0, tzinfo=UTC)
    initial = AssessmentPlanner().plan(
        engagement=_engagement(),
        target=Target("camera-1", "Lab camera"),
        registry=CapabilityRegistry(),
        test_cases=(_uart_test(),),
        assessment_id="gap-same-assessment",
        created_at=created_at,
    )
    observation = Observation(
        observation_id="obs-prior",
        evidence_ids=("evidence-prior",),
        statement="Prior unrelated evidence remains attached.",
        confidence="observed",
    )
    initial = replace(initial, observations=(observation,))

    refreshed = AssessmentPlanner().refresh_capability_gaps(
        state=initial,
        engagement=_engagement(),
        registry=_implemented_uart_registry(),
    )

    assert refreshed.assessment_id == initial.assessment_id
    assert refreshed.created_at == initial.created_at
    assert refreshed.observations == (observation,)
    assert refreshed.steps[0].status is StepStatus.READY
    assert refreshed.steps[0].action == initial.steps[0].action
    assert refreshed.steps[0].instrument_id == "simulator-1"


def test_gap_refresh_re_evaluates_current_engagement_policy() -> None:
    initial = AssessmentPlanner().plan(
        engagement=_engagement(),
        target=Target("camera-1", "Lab camera"),
        registry=CapabilityRegistry(),
        test_cases=(_uart_test(),),
        assessment_id="gap-policy-refresh",
    )

    refreshed = AssessmentPlanner().refresh_capability_gaps(
        state=initial,
        engagement=_engagement(denied_capabilities=("internal.uart.*",)),
        registry=_implemented_uart_registry(),
    )

    assert refreshed.steps[0].status is StepStatus.BLOCKED
    assert "denied" in refreshed.steps[0].reason.lower()


def test_unresolved_gap_keeps_intended_action_unchanged() -> None:
    initial = AssessmentPlanner().plan(
        engagement=_engagement(),
        target=Target("camera-1", "Lab camera"),
        registry=CapabilityRegistry(),
        test_cases=(_uart_test(),),
        assessment_id="gap-unresolved",
    )

    refreshed = AssessmentPlanner().refresh_capability_gaps(
        state=initial,
        engagement=_engagement(),
        registry=CapabilityRegistry(),
    )

    assert refreshed.status is AssessmentStatus.CAPABILITY_GAP
    assert refreshed.steps[0].status is StepStatus.CAPABILITY_GAP
    assert refreshed.steps[0].action == initial.steps[0].action


def test_fresh_replan_resolves_gap_after_implementation_is_registered() -> None:
    first = AssessmentPlanner().plan(
        engagement=_engagement(),
        target=Target("camera-1", "Lab camera"),
        registry=CapabilityRegistry(),
        test_cases=(_uart_test(),),
        assessment_id="gap-before",
    )
    assert first.steps[0].status is StepStatus.CAPABILITY_GAP

    replanned = AssessmentPlanner().plan(
        engagement=_engagement(),
        target=Target("camera-1", "Lab camera"),
        registry=_implemented_uart_registry(),
        test_cases=(_uart_test(),),
        assessment_id="gap-after",
    )

    assert replanned.steps[0].status is StepStatus.READY
    assert replanned.steps[0].action is not None
    assert replanned.steps[0].action.capability_id == "internal.uart.autodetect"
