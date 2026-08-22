from datetime import UTC, datetime, timedelta

from hardware_pentest.core.models import (
    Action,
    ActionClass,
    Engagement,
    PolicyDecision,
)
from hardware_pentest.policy.engine import PolicyEngine


def engagement() -> Engagement:
    now = datetime.now(UTC)
    return Engagement(
        engagement_id="test-engagement",
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(minutes=30),
        target_ids=frozenset({"target-a"}),
        allowed_capabilities=("wireless.nfc.*",),
        denied_capabilities=("wireless.nfc.emulate",),
        max_action_class=ActionClass.OBSERVE,
    )


def test_allows_scoped_observation() -> None:
    action = Action(
        action_id="a1",
        capability_id="wireless.nfc.identify",
        target_id="target-a",
        action_class=ActionClass.OBSERVE,
    )
    assert PolicyEngine().evaluate(engagement(), action).decision is PolicyDecision.ALLOW


def test_deny_rule_overrides_allow_pattern() -> None:
    action = Action(
        action_id="a2",
        capability_id="wireless.nfc.emulate",
        target_id="target-a",
        action_class=ActionClass.EMULATE,
    )
    result = PolicyEngine().evaluate(engagement(), action)
    assert result.decision is PolicyDecision.DENY
    assert "deny" in result.reason.lower()


def test_denies_out_of_scope_target() -> None:
    action = Action(
        action_id="a3",
        capability_id="wireless.nfc.identify",
        target_id="other-target",
        action_class=ActionClass.OBSERVE,
    )
    assert PolicyEngine().evaluate(engagement(), action).decision is PolicyDecision.DENY


def test_denies_action_above_maximum_class() -> None:
    action = Action(
        action_id="a4",
        capability_id="wireless.nfc.identify",
        target_id="target-a",
        action_class=ActionClass.INTERACT,
    )
    assert PolicyEngine().evaluate(engagement(), action).decision is PolicyDecision.DENY
