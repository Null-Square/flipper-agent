from datetime import UTC, datetime, timedelta

from hardware_pentest.adapters.simulated import SimulatedAdapter
from hardware_pentest.core.models import Action, ActionClass, Engagement, PolicyDecision
from hardware_pentest.core.registry import CapabilityRegistry
from hardware_pentest.evidence.store import LocalEvidenceStore
from hardware_pentest.policy.engine import PolicyEngine
from hardware_pentest.runtime.executor import AssessmentExecutor


def active_engagement() -> Engagement:
    now = datetime.now(UTC)
    return Engagement(
        engagement_id="runtime-test",
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(minutes=30),
        target_ids=frozenset({"target-a"}),
        allowed_capabilities=("wireless.*", "infrared.*"),
        denied_capabilities=("*.emulate", "*.transmit"),
        max_action_class=ActionClass.OBSERVE,
    )


def test_registry_routes_to_simulator() -> None:
    registry = CapabilityRegistry()
    registry.register(SimulatedAdapter())

    route = registry.choose("wireless.nfc.identify")
    assert route.capability.instrument_id == "simulator-1"


def test_executor_runs_allowed_action_and_records_evidence(tmp_path) -> None:
    registry = CapabilityRegistry()
    registry.register(SimulatedAdapter())
    executor = AssessmentExecutor(
        registry=registry,
        policy=PolicyEngine(),
        evidence=LocalEvidenceStore(tmp_path),
    )
    action = Action(
        action_id="act-1",
        capability_id="wireless.nfc.identify",
        target_id="target-a",
        action_class=ActionClass.OBSERVE,
    )

    result = executor.execute(active_engagement(), action)

    assert result.policy.decision is PolicyDecision.ALLOW
    assert result.execution is not None
    assert result.evidence is not None
    assert result.evidence.raw_artifact_hash


def test_executor_blocks_unavailable_capability(tmp_path) -> None:
    registry = CapabilityRegistry()
    registry.register(SimulatedAdapter())
    executor = AssessmentExecutor(
        registry=registry,
        policy=PolicyEngine(),
        evidence=LocalEvidenceStore(tmp_path),
    )
    action = Action(
        action_id="act-2",
        capability_id="wireless.ble.observe",
        target_id="target-a",
        action_class=ActionClass.OBSERVE,
    )

    result = executor.execute(active_engagement(), action)

    assert result.policy.decision is PolicyDecision.DENY
    assert result.evidence is None
