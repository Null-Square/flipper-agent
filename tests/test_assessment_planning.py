from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hardware_pentest.adapters.simulated import SimulatedAdapter
from hardware_pentest.assessment import (
    AssessmentPlanner,
    AssessmentStoreError,
    Finding,
    FindingStatus,
    LocalAssessmentStore,
    StepStatus,
    flipper_mvp_test_catalog,
)
from hardware_pentest.core.models import Action, ActionClass, Engagement, Target
from hardware_pentest.core.registry import CapabilityRegistry


def engagement(*, max_action_class: ActionClass = ActionClass.INTERACT) -> Engagement:
    now = datetime.now(UTC)
    return Engagement(
        engagement_id="assessment-lab",
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(hours=1),
        target_ids=frozenset({"target-a"}),
        allowed_capabilities=("infrared.*", "wireless.*", "internal.gpio.*"),
        denied_capabilities=("*.transmit", "*.emulate", "*.write"),
        max_action_class=max_action_class,
    )


def target() -> Target:
    return Target(target_id="target-a", description="Lab-owned device", metadata={"lab": True})


def registry(adapter: SimulatedAdapter | None = None) -> CapabilityRegistry:
    result = CapabilityRegistry()
    result.register(adapter or SimulatedAdapter())
    return result


def test_planner_builds_passive_first_plan_from_available_capabilities() -> None:
    state = AssessmentPlanner().plan(
        engagement=engagement(),
        target=target(),
        registry=registry(),
        test_cases=flipper_mvp_test_catalog(),
        test_inputs={"flipper.gpio.inspect.v1": {"pin": "PA7"}},
        assessment_id="assessment-001",
    )

    assert [step.test_case_id for step in state.steps] == [
        "flipper.ir.observe.v1",
        "flipper.subghz.observe.v1",
        "flipper.gpio.inspect.v1",
        "flipper.nfc.identify.v1",
    ]
    assert state.steps[0].status is StepStatus.READY
    assert state.steps[1].status is StepStatus.READY
    assert state.steps[2].status is StepStatus.HUMAN_ACTION_REQUIRED
    assert state.steps[3].status is StepStatus.READY
    assert all(step.executable for step in state.steps)


def test_unavailable_capabilities_are_visible_but_never_executable() -> None:
    simulator = SimulatedAdapter(scripted_results={"infrared.observe": {}})
    state = AssessmentPlanner().plan(
        engagement=engagement(),
        target=target(),
        registry=registry(simulator),
        test_cases=flipper_mvp_test_catalog(),
        assessment_id="assessment-002",
    )

    infrared = state.step("assessment-002:flipper.ir.observe.v1")
    nfc = state.step("assessment-002:flipper.nfc.identify.v1")

    assert infrared.status is StepStatus.READY
    assert nfc.status is StepStatus.BLOCKED
    assert nfc.executable is False
    assert nfc.action is None
    assert "No connected instrument" in nfc.reason


def test_nfc_is_blocked_when_engagement_allows_observe_only() -> None:
    state = AssessmentPlanner().plan(
        engagement=engagement(max_action_class=ActionClass.OBSERVE),
        target=target(),
        registry=registry(),
        test_cases=flipper_mvp_test_catalog(),
        assessment_id="assessment-003",
    )

    nfc = state.step("assessment-003:flipper.nfc.identify.v1")

    assert nfc.status is StepStatus.BLOCKED
    assert nfc.executable is False
    assert "exceeds" in nfc.reason


def test_gpio_requires_explicit_test_input_and_human_action() -> None:
    state = AssessmentPlanner().plan(
        engagement=engagement(),
        target=target(),
        registry=registry(),
        test_cases=flipper_mvp_test_catalog(),
        assessment_id="assessment-004",
    )

    gpio = state.step("assessment-004:flipper.gpio.inspect.v1")

    assert gpio.status is StepStatus.BLOCKED
    assert gpio.action is None
    assert "Missing required inputs" in gpio.reason


def test_assessment_state_round_trips_without_conversation_history(tmp_path) -> None:
    created_at = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
    state = AssessmentPlanner().plan(
        engagement=engagement(),
        target=target(),
        registry=registry(),
        test_cases=flipper_mvp_test_catalog(),
        test_inputs={"flipper.gpio.inspect.v1": {"pin": "PC0"}},
        assessment_id="assessment-resume",
        created_at=created_at,
    )
    store = LocalAssessmentStore(tmp_path / "assessments")

    path = store.save(state)
    restored = store.load("assessment-resume")

    assert path.is_file()
    assert restored == state
    assert restored.step("assessment-resume:flipper.gpio.inspect.v1").action is not None
    assert restored.step("assessment-resume:flipper.gpio.inspect.v1").action.inputs["pin"] == "PC0"


def test_assessment_store_rejects_path_like_identifier(tmp_path) -> None:
    store = LocalAssessmentStore(tmp_path / "assessments")

    with pytest.raises(AssessmentStoreError):
        store.load("../escape")


def test_confirmed_finding_requires_evidence_reference() -> None:
    with pytest.raises(ValueError, match="evidence ID"):
        Finding(
            finding_id="finding-1",
            title="Candidate issue",
            statement="An issue was confirmed.",
            status=FindingStatus.CONFIRMED,
        )


def test_simulator_uses_same_nfc_action_class_as_real_adapter() -> None:
    simulator = SimulatedAdapter()
    descriptors = {item.capability_id: item for item in simulator.capabilities()}
    assert descriptors["wireless.nfc.identify"].action_class is ActionClass.INTERACT

    wrong = simulator.validate(
        Action(
            action_id="wrong-nfc-class",
            capability_id="wireless.nfc.identify",
            target_id="target-a",
            action_class=ActionClass.OBSERVE,
        )
    )
    correct = simulator.validate(
        Action(
            action_id="correct-nfc-class",
            capability_id="wireless.nfc.identify",
            target_id="target-a",
            action_class=ActionClass.INTERACT,
        )
    )

    assert wrong.valid is False
    assert correct.valid is True
