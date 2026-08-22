from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hardware_pentest.adapters.simulated import SimulatedAdapter
from hardware_pentest.assessment import (
    AssessmentPlanner,
    AssessmentRunner,
    AssessmentStateMachine,
    AssessmentStatus,
    LocalAssessmentStore,
    StepStatus,
    flipper_mvp_test_catalog,
)
from hardware_pentest.core.models import ActionClass, Engagement, Target
from hardware_pentest.core.registry import CapabilityRegistry
from hardware_pentest.evidence.store import LocalEvidenceStore
from hardware_pentest.policy.engine import PolicyEngine
from hardware_pentest.runtime.executor import AssessmentExecutor


def engagement() -> Engagement:
    now = datetime.now(UTC)
    return Engagement(
        engagement_id="routing-lab",
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(minutes=10),
        target_ids=frozenset({"target-a"}),
        allowed_capabilities=("infrared.observe",),
        denied_capabilities=(),
        max_action_class=ActionClass.OBSERVE,
    )


def target() -> Target:
    return Target(target_id="target-a", description="Lab target")


def infrared_test_case():
    return tuple(
        item
        for item in flipper_mvp_test_catalog()
        if item.required_capability == "infrared.observe"
    )


def executor_for(tmp_path, adapter: SimulatedAdapter) -> AssessmentExecutor:
    registry = CapabilityRegistry()
    registry.register(adapter)
    return AssessmentExecutor(
        registry=registry,
        policy=PolicyEngine(),
        evidence=LocalEvidenceStore(tmp_path / "evidence"),
    )


def test_execution_blocks_if_current_route_differs_from_planned_instrument(tmp_path) -> None:
    planning_registry = CapabilityRegistry()
    planning_registry.register(SimulatedAdapter(instrument_id="simulator-planned"))
    state = AssessmentPlanner().plan(
        engagement=engagement(),
        target=target(),
        registry=planning_registry,
        test_cases=infrared_test_case(),
        assessment_id="assessment-route-change",
    )
    store = LocalAssessmentStore(tmp_path / "assessments")
    runner = AssessmentRunner(
        executor=executor_for(tmp_path, SimulatedAdapter(instrument_id="simulator-other")),
        store=store,
    )

    result = runner.run_next(engagement(), state)

    assert result.runtime is not None
    assert result.runtime.evidence is None
    assert result.state.steps[0].status is StepStatus.BLOCKED
    assert "Planned instrument simulator-planned is unavailable" in result.state.steps[0].reason


def test_persisted_running_step_requires_explicit_recovery_and_is_not_retried(tmp_path) -> None:
    registry = CapabilityRegistry()
    registry.register(SimulatedAdapter())
    state = AssessmentPlanner().plan(
        engagement=engagement(),
        target=target(),
        registry=registry,
        test_cases=infrared_test_case(),
        assessment_id="assessment-crash",
    )
    machine = AssessmentStateMachine()
    running = machine.mark_running(state, state.steps[0].step_id)
    store = LocalAssessmentStore(tmp_path / "assessments")
    store.save(running)
    runner = AssessmentRunner(
        executor=executor_for(tmp_path, SimulatedAdapter()),
        store=store,
    )

    resumed = store.load("assessment-crash")
    paused = runner.run_next(engagement(), resumed)

    assert paused.paused is True
    assert paused.runtime is None
    assert paused.state.status is AssessmentStatus.INTERRUPTED
    assert paused.state.steps[0].status is StepStatus.RUNNING
    assert paused.state.steps[0].evidence_ids == ()

    recovered = runner.recover_interrupted(paused.state)

    assert recovered.steps[0].status is StepStatus.INTERRUPTED
    assert recovered.steps[0].evidence_ids == ()
    assert recovered.status is AssessmentStatus.COMPLETED
