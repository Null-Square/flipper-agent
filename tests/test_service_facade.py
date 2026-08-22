from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hardware_pentest.assessment.models import (
    AssessmentState,
    AssessmentStatus,
    PlannedStep,
    StepStatus,
)
from hardware_pentest.core.models import Action, ActionClass, Observation, Target
from hardware_pentest.service import HardwarePentestService


def _service(tmp_path) -> HardwarePentestService:
    return HardwarePentestService(
        assessment_root=tmp_path / "assessments",
        engagement_root=tmp_path / "engagements",
        evidence_root=tmp_path / "evidence",
        verification_root=tmp_path / "verification",
        preflight_root=tmp_path / "preflight",
        gate_root=tmp_path / "gates",
    )


def _state() -> AssessmentState:
    timestamp = datetime(2026, 8, 23, 0, 0, tzinfo=UTC)
    action = Action(
        action_id="wifi-observe:camera-1",
        capability_id="wireless.wifi.environment.scan",
        target_id="camera-1",
        action_class=ActionClass.OBSERVE,
    )
    return AssessmentState(
        schema_version="1",
        assessment_id="assessment-1",
        engagement_id="engagement-1",
        target=Target(
            target_id="camera-1",
            description="Authorized lab camera",
            metadata={"site": "lab", "operator_secret": "must-not-leak"},
        ),
        status=AssessmentStatus.PLANNED,
        created_at=timestamp,
        updated_at=timestamp,
        steps=(
            PlannedStep(
                step_id="assessment-1:wifi-observe",
                test_case_id="wifi-observe",
                action=action,
                status=StepStatus.READY,
                reason="Passive test is ready",
                instrument_id="flipper-marauder:test",
            ),
            PlannedStep(
                step_id="assessment-1:missing",
                test_case_id="missing",
                action=None,
                status=StepStatus.BLOCKED,
                reason="No route",
            ),
        ),
        observations=(
            Observation(
                observation_id="obs-1",
                evidence_ids=("ev-1",),
                statement="Known lab AP observed",
                confidence="high",
            ),
        ),
    )


def test_service_context_is_compact_durable_domain_state(tmp_path) -> None:
    service = _service(tmp_path)
    service.assessments.save(_state())

    context = service.assessment_context("assessment-1")

    assert context["assessment_id"] == "assessment-1"
    assert context["next_step"]["capability_id"] == "wireless.wifi.environment.scan"
    assert context["progress"]["total_steps"] == 2
    assert context["progress"]["remaining_steps"] == 1
    assert context["target"]["metadata_keys"] == ["operator_secret", "site"]
    assert "must-not-leak" not in repr(context)
    assert context["blocked_steps"][0]["reason"] == "No route"
    assert context["observations"][0]["evidence_ids"] == ["ev-1"]


def test_service_lists_assessments_without_loading_agent_conversation_state(tmp_path) -> None:
    service = _service(tmp_path)
    service.assessments.save(_state())

    payload = service.assessment_list()

    assert payload == {"count": 1, "assessment_ids": ["assessment-1"]}


def test_service_info_makes_outer_harness_boundary_explicit(tmp_path) -> None:
    payload = _service(tmp_path).service_info()

    assert "llm_inference" in payload["outer_harness_owns"]
    assert "assessment_state" in payload["runtime_owns"]
    assert "engagement_scope" in payload["runtime_owns"]
    assert "operator_gate_grants" in payload["runtime_owns"]
    assert "policy_and_scope" in payload["runtime_owns"]


@pytest.mark.parametrize("value", [0, 101, True, "20"])
def test_context_limit_fails_closed(tmp_path, value) -> None:
    service = _service(tmp_path)
    service.assessments.save(_state())

    with pytest.raises(ValueError, match="limit"):
        service.assessment_context("assessment-1", max_items=value)
