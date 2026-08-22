from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hardware_pentest.adapters.simulated import SimulatedAdapter
from hardware_pentest.assessment import (
    AssessmentPlanner,
    AssessmentRunner,
    AssessmentStatus,
    LocalAssessmentStore,
    StepStatus,
    TestCase,
    flipper_mvp_test_catalog,
)
from hardware_pentest.core.models import ActionClass, Engagement, ExecutionStatus, Target
from hardware_pentest.core.registry import CapabilityRegistry
from hardware_pentest.evidence.store import LocalEvidenceStore
from hardware_pentest.policy.engine import PolicyEngine
from hardware_pentest.runtime.executor import AssessmentExecutor


def engagement() -> Engagement:
    now = datetime.now(UTC)
    return Engagement(
        engagement_id="runner-lab",
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(hours=1),
        target_ids=frozenset({"target-a"}),
        allowed_capabilities=("infrared.*", "wireless.*", "internal.gpio.*"),
        denied_capabilities=("*.transmit", "*.emulate", "*.write"),
        max_action_class=ActionClass.INTERACT,
    )


def target() -> Target:
    return Target(target_id="target-a", description="Lab-owned target")


def runtime(tmp_path, adapter: SimulatedAdapter | None = None):
    registry = CapabilityRegistry()
    registry.register(adapter or SimulatedAdapter())
    state_store = LocalAssessmentStore(tmp_path / "assessments")
    executor = AssessmentExecutor(
        registry=registry,
        policy=PolicyEngine(),
        evidence=LocalEvidenceStore(tmp_path / "evidence"),
    )
    runner = AssessmentRunner(executor=executor, store=state_store)
    return registry, state_store, runner


def single_test_case(capability_id: str) -> tuple[TestCase, ...]:
    return tuple(
        item
        for item in flipper_mvp_test_catalog()
        if item.required_capability == capability_id
    )


def test_multi_step_assessment_pauses_for_gpio_and_resumes_from_disk(tmp_path) -> None:
    registry, store, runner = runtime(tmp_path)
    state = AssessmentPlanner().plan(
        engagement=engagement(),
        target=target(),
        registry=registry,
        test_cases=flipper_mvp_test_catalog(),
        test_inputs={"flipper.gpio.inspect.v1": {"pin": "PA7"}},
        assessment_id="assessment-e2e",
    )
    store.save(state)

    first = runner.run_next(engagement(), state)
    first_reloaded = store.load("assessment-e2e")
    assert first_reloaded == first.state
    assert first.state.steps[0].status is StepStatus.SUCCESS
    assert len(first.state.steps[0].evidence_ids) == 1
    assert first.state.observations[0].evidence_ids == first.state.steps[0].evidence_ids

    second = runner.run_next(engagement(), first_reloaded)
    assert second.state.steps[1].status is StepStatus.SUCCESS

    paused = runner.run_next(engagement(), second.state)
    assert paused.paused is True
    assert paused.runtime is None
    assert paused.state.status is AssessmentStatus.HUMAN_ACTION_REQUIRED
    gpio = paused.state.steps[2]
    assert gpio.status is StepStatus.HUMAN_ACTION_REQUIRED
    assert gpio.evidence_ids == ()

    resumed = store.load("assessment-e2e")
    gpio_result = runner.run_next(
        engagement(),
        resumed,
        human_action_complete=True,
    )
    assert gpio_result.state.steps[2].status is StepStatus.SUCCESS
    assert len(gpio_result.state.steps[2].evidence_ids) == 1

    nfc_result = runner.run_next(engagement(), gpio_result.state)
    assert nfc_result.state.steps[3].status is StepStatus.SUCCESS
    assert nfc_result.state.status is AssessmentStatus.COMPLETED
    assert all(step.evidence_ids for step in nfc_result.state.steps)
    assert len(nfc_result.state.observations) == 4
    assert nfc_result.state.findings == ()


def test_inconclusive_result_remains_inconclusive_and_is_evidence_linked(tmp_path) -> None:
    adapter = SimulatedAdapter(
        scripted_results={
            "infrared.observe": {
                "status": ExecutionStatus.INCONCLUSIVE,
                "normalized": {"signal_count": 0},
                "limitations": ("No signal observed during bounded window",),
            }
        }
    )
    registry, store, runner = runtime(tmp_path, adapter)
    state = AssessmentPlanner().plan(
        engagement=engagement(),
        target=target(),
        registry=registry,
        test_cases=single_test_case("infrared.observe"),
        assessment_id="assessment-inconclusive",
    )
    store.save(state)

    result = runner.run_next(engagement(), state)

    step = result.state.steps[0]
    assert step.status is StepStatus.INCONCLUSIVE
    assert len(step.evidence_ids) == 1
    assert result.state.status is AssessmentStatus.COMPLETED
    assert result.state.observations[0].confidence == "inconclusive"
    assert result.state.findings == ()


def test_blocked_execution_remains_blocked_and_does_not_create_observation(tmp_path) -> None:
    adapter = SimulatedAdapter(
        scripted_results={
            "infrared.observe": {
                "status": ExecutionStatus.BLOCKED,
                "normalized": {},
            }
        }
    )
    registry, store, runner = runtime(tmp_path, adapter)
    state = AssessmentPlanner().plan(
        engagement=engagement(),
        target=target(),
        registry=registry,
        test_cases=single_test_case("infrared.observe"),
        assessment_id="assessment-blocked-execution",
    )
    store.save(state)

    result = runner.run_next(engagement(), state)

    assert result.state.steps[0].status is StepStatus.BLOCKED
    assert result.state.steps[0].evidence_ids
    assert result.state.observations == ()
    assert result.state.status is AssessmentStatus.COMPLETED


def test_approval_gate_pauses_without_execution_then_resumes(tmp_path) -> None:
    registry, store, runner = runtime(tmp_path)
    approved_test = TestCase(
        test_case_id="approval-test",
        title="Approval-gated IR observation",
        purpose="Exercise persisted approval gating.",
        required_capability="infrared.observe",
        action_class=ActionClass.OBSERVE,
        prerequisites=(),
        expected_evidence=("Evidence record",),
        stop_conditions=(),
        result_rules=("Do not infer a vulnerability.",),
        requires_approval=True,
    )
    state = AssessmentPlanner().plan(
        engagement=engagement(),
        target=target(),
        registry=registry,
        test_cases=(approved_test,),
        assessment_id="assessment-approval",
    )
    assert state.steps[0].status is StepStatus.APPROVAL_REQUIRED
    store.save(state)

    paused = runner.run_next(engagement(), state)

    assert paused.paused is True
    assert paused.runtime is None
    assert paused.state.status is AssessmentStatus.APPROVAL_REQUIRED
    assert paused.state.steps[0].evidence_ids == ()

    restored = store.load("assessment-approval")
    completed = runner.run_next(
        engagement(),
        restored,
        approval_present=True,
    )

    assert completed.runtime is not None
    assert completed.state.steps[0].status is StepStatus.SUCCESS
    assert completed.state.status is AssessmentStatus.COMPLETED
    assert completed.state.steps[0].evidence_ids


def test_runtime_policy_denial_after_planning_does_not_create_evidence(tmp_path) -> None:
    registry, store, runner = runtime(tmp_path)
    planned_engagement = engagement()
    state = AssessmentPlanner().plan(
        engagement=planned_engagement,
        target=target(),
        registry=registry,
        test_cases=single_test_case("infrared.observe"),
        assessment_id="assessment-policy-change",
    )
    store.save(state)

    now = datetime.now(UTC)
    expired = Engagement(
        engagement_id=planned_engagement.engagement_id,
        valid_from=now - timedelta(hours=2),
        valid_until=now - timedelta(hours=1),
        target_ids=planned_engagement.target_ids,
        allowed_capabilities=planned_engagement.allowed_capabilities,
        denied_capabilities=planned_engagement.denied_capabilities,
        max_action_class=planned_engagement.max_action_class,
    )

    result = runner.run_next(expired, state)

    assert result.runtime is not None
    assert result.runtime.evidence is None
    assert result.state.steps[0].status is StepStatus.BLOCKED
    assert result.state.steps[0].evidence_ids == ()
    assert result.state.status is AssessmentStatus.COMPLETED
