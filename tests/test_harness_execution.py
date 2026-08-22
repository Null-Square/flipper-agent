from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hardware_pentest.assessment.models import (
    AssessmentState,
    AssessmentStatus,
    PlannedStep,
    StepStatus,
)
from hardware_pentest.assessment.store import LocalAssessmentStore
from hardware_pentest.core.engagement_store import LocalEngagementStore
from hardware_pentest.core.models import Action, ActionClass, Engagement, Target
from hardware_pentest.evidence.store import LocalEvidenceStore
from hardware_pentest.service.execution import HarnessAssessmentExecutor, InstrumentSelection
from hardware_pentest.service.gates import GateKind, LocalGateStore


def _roots(tmp_path: Path) -> dict[str, Path]:
    return {
        "assessment_root": tmp_path / "assessments",
        "engagement_root": tmp_path / "engagements",
        "evidence_root": tmp_path / "evidence",
        "verification_root": tmp_path / "verification",
        "preflight_root": tmp_path / "preflight",
        "gate_root": tmp_path / "gates",
    }


def _persist_assessment(tmp_path: Path, *, requires_approval: bool) -> None:
    roots = _roots(tmp_path)
    now = datetime.now(UTC)
    target = Target(target_id="camera-1", description="Authorized lab camera")
    engagement = Engagement(
        engagement_id="engagement-1",
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
        target_ids=frozenset({target.target_id}),
        allowed_capabilities=("infrared.observe",),
        denied_capabilities=(),
        max_action_class=ActionClass.OBSERVE,
    )
    LocalEngagementStore(roots["engagement_root"]).save(engagement, (target,))

    action = Action(
        action_id="ir:camera-1",
        capability_id="infrared.observe",
        target_id=target.target_id,
        action_class=ActionClass.OBSERVE,
        requires_approval=requires_approval,
    )
    state = AssessmentState(
        schema_version="1",
        assessment_id="assessment-1",
        engagement_id=engagement.engagement_id,
        target=target,
        status=AssessmentStatus.PLANNED,
        created_at=now,
        updated_at=now,
        steps=(
            PlannedStep(
                step_id="assessment-1:ir",
                test_case_id="ir",
                action=action,
                status=StepStatus.READY,
                reason="Ready",
                instrument_id="simulator-1",
            ),
        ),
    )
    LocalAssessmentStore(roots["assessment_root"]).save(state)


def test_outer_agent_cannot_self_approve_gated_step(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    _persist_assessment(tmp_path, requires_approval=True)
    executor = HarnessAssessmentExecutor(**roots)

    result = executor.execute_next("assessment-1", instrument=InstrumentSelection())

    assert result["paused"] is True
    assert result["assessment_status"] == "approval_required"
    assert LocalEvidenceStore(roots["evidence_root"]).records("engagement-1") == ()

    with pytest.raises(TypeError):
        executor.execute_next(  # type: ignore[call-arg]
            "assessment-1",
            instrument=InstrumentSelection(),
            approval_present=True,
        )


def test_operator_gate_is_consumed_then_step_executes_with_evidence(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    _persist_assessment(tmp_path, requires_approval=True)
    executor = HarnessAssessmentExecutor(**roots)

    executor.execute_next("assessment-1", instrument=InstrumentSelection())
    gates = LocalGateStore(roots["gate_root"])
    gates.grant(
        assessment_id="assessment-1",
        step_id="assessment-1:ir",
        kind=GateKind.APPROVAL,
    )

    result = executor.execute_next("assessment-1", instrument=InstrumentSelection())

    assert result["paused"] is False
    assert result["execution_status"] == "success"
    assert result["assessment_status"] == "completed"
    assert str(result["evidence_id"]).startswith("ev-")
    evidence = LocalEvidenceStore(roots["evidence_root"]).records("engagement-1")
    assert len(evidence) == 1
    assert evidence[0].capability_id == "infrared.observe"
    assert gates.available(
        assessment_id="assessment-1",
        step_id="assessment-1:ir",
        kind=GateKind.APPROVAL,
    ) is None


def test_execution_fails_closed_without_persisted_engagement(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    _persist_assessment(tmp_path, requires_approval=False)
    engagement_path = roots["engagement_root"] / "engagement-1.json"
    engagement_path.unlink()

    executor = HarnessAssessmentExecutor(**roots)

    with pytest.raises(ValueError, match="Stored engagement does not exist"):
        executor.execute_next("assessment-1", instrument=InstrumentSelection())


def test_recovery_requires_separate_operator_grant(tmp_path: Path) -> None:
    roots = _roots(tmp_path)
    _persist_assessment(tmp_path, requires_approval=False)
    store = LocalAssessmentStore(roots["assessment_root"])
    state = store.load("assessment-1")
    running_step = replace(state.steps[0], status=StepStatus.RUNNING, reason="Execution started")
    store.save(
        replace(
            state,
            status=AssessmentStatus.RUNNING,
            steps=(running_step,),
        )
    )
    executor = HarnessAssessmentExecutor(**roots)

    with pytest.raises(PermissionError, match="Operator recovery grant"):
        executor.recover_interrupted("assessment-1")

    LocalGateStore(roots["gate_root"]).grant(
        assessment_id="assessment-1",
        step_id="assessment-1:ir",
        kind=GateKind.RECOVERY,
    )
    recovered = executor.recover_interrupted("assessment-1")

    assert recovered["status"] in {"interrupted", "completed"}
    assert str(recovered["operator_gate_grant_id"]).startswith("gate-")
