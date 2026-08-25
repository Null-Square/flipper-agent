from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hardware_pentest.assessment.coverage import build_assessment_coverage
from hardware_pentest.assessment.models import (
    AssessmentState,
    AssessmentStatus,
    PlannedStep,
    StepStatus,
)
from hardware_pentest.core.models import Action, ActionClass, Target
from hardware_pentest.service import HardwarePentestService


def _action(capability: str, *, approval: bool = False) -> Action:
    return Action(
        action_id=f"{capability}:target-1",
        capability_id=capability,
        target_id="target-1",
        action_class=ActionClass.OBSERVE,
        inputs={},
        requires_approval=approval,
    )


def _state() -> AssessmentState:
    now = datetime.now(UTC)
    return AssessmentState(
        schema_version="1",
        assessment_id="assessment-coverage",
        engagement_id="eng-coverage",
        target=Target(target_id="target-1", description="Authorized embedded controller"),
        status=AssessmentStatus.PLANNED,
        created_at=now,
        updated_at=now,
        steps=(
            PlannedStep(
                step_id="assessment-coverage:artifact.firmware.inspect.v1",
                test_case_id="artifact.firmware.inspect.v1",
                action=_action("artifact.firmware.inspect"),
                status=StepStatus.READY,
                reason="Allowed by engagement policy",
                instrument_id="host.local",
                required_capability="artifact.firmware.inspect",
            ),
            PlannedStep(
                step_id="assessment-coverage:serial-observe",
                test_case_id="interface.serial.observe.v1",
                action=_action("interface.serial.observe", approval=True),
                status=StepStatus.APPROVAL_REQUIRED,
                reason="Operator approval is required",
                instrument_id="host.local",
                required_capability="interface.serial.observe",
            ),
            PlannedStep(
                step_id="assessment-coverage:tested",
                test_case_id="artifact.binary.identify.v1",
                action=_action("artifact.binary.identify"),
                status=StepStatus.SUCCESS,
                reason="Execution succeeded",
                instrument_id="host.local",
                evidence_ids=("evidence-1",),
                required_capability="artifact.binary.identify",
            ),
            PlannedStep(
                step_id="assessment-coverage:gap",
                test_case_id="future.swd.observe.v1",
                action=_action("internal.swd.observe"),
                status=StepStatus.CAPABILITY_GAP,
                reason="No current capability implementation provides internal.swd.observe",
                required_capability="internal.swd.observe",
            ),
            PlannedStep(
                step_id="assessment-coverage:blocked",
                test_case_id="future.input.required.v1",
                action=None,
                status=StepStatus.BLOCKED,
                reason="Missing required inputs for future.input.required.v1: pin",
                required_capability="internal.gpio.inspect",
            ),
            PlannedStep(
                step_id="assessment-coverage:interrupted",
                test_case_id="future.interrupted.v1",
                action=_action("interface.serial.observe"),
                status=StepStatus.INTERRUPTED,
                reason="Unknown hardware outcome",
                instrument_id="host.local",
                required_capability="interface.serial.observe",
            ),
        ),
    )


def test_coverage_separates_routes_gaps_blocks_and_operator_gates() -> None:
    result = build_assessment_coverage(_state())

    assert result["summary"] == {
        "total_tests": 6,
        "available_now": 1,
        "awaiting_operator": 1,
        "tested": 1,
        "attempted": 1,
        "capability_gaps": 1,
        "blocked": 1,
    }
    assert result["available_now"][0]["provider_route"] == "host.local"
    assert result["awaiting_operator"][0]["status"] == "approval_required"
    assert result["tested"][0]["evidence_ids"] == ["evidence-1"]
    assert result["attempted"][0]["status"] == "interrupted"

    gap = result["capability_gaps"][0]
    assert gap["required_capability"] == "internal.swd.observe"
    assert gap["provider_route"] is None
    assert gap["unlock"] == {
        "required_capability": "internal.swd.observe",
        "current_provider_routes": [],
    }

    blocked = result["blocked"][0]
    assert blocked["required_capability"] == "internal.gpio.inspect"
    assert "Missing required inputs" in blocked["reason"]
    assert "unlock" not in blocked


def test_coverage_limit_is_bounded() -> None:
    result = build_assessment_coverage(_state(), limit=1)

    assert result["limit"] == 1
    assert len(result["available_now"]) <= 1
    assert len(result["capability_gaps"]) <= 1


def test_public_service_exposes_persisted_coverage(tmp_path: Path) -> None:
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
    service.assessments.save(_state())

    result = service.assessment_coverage("assessment-coverage")

    assert result["target"]["target_id"] == "target-1"
    assert result["summary"]["capability_gaps"] == 1
    assert result["capability_gaps"][0]["unlock"]["required_capability"] == (
        "internal.swd.observe"
    )
