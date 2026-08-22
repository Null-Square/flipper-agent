from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from hardware_pentest.core.engagement_store import EngagementStoreError, LocalEngagementStore
from hardware_pentest.core.models import ActionClass, Engagement, Target


def _engagement() -> tuple[Engagement, tuple[Target, ...]]:
    now = datetime.now(UTC)
    target = Target(
        target_id="camera-1",
        description="Authorized lab camera",
        metadata={"site": "lab", "secret_ref": "wifi/lab"},
    )
    engagement = Engagement(
        engagement_id="engagement-1",
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
        target_ids=frozenset({target.target_id}),
        allowed_capabilities=("infrared.observe",),
        denied_capabilities=(),
        max_action_class=ActionClass.OBSERVE,
    )
    return engagement, (target,)


def test_engagement_store_round_trips_operator_scope(tmp_path) -> None:
    store = LocalEngagementStore(tmp_path)
    engagement, targets = _engagement()

    store.save(engagement, targets)
    loaded, loaded_targets = store.load(engagement.engagement_id)

    assert loaded == engagement
    assert loaded_targets == targets
    assert store.list_ids() == ("engagement-1",)


def test_engagement_store_rejects_target_scope_mismatch(tmp_path) -> None:
    store = LocalEngagementStore(tmp_path)
    engagement, _targets = _engagement()

    with pytest.raises(EngagementStoreError, match="exactly match"):
        store.save(
            engagement,
            (Target(target_id="other", description="Other"),),
        )


def test_engagement_store_detects_tampering(tmp_path) -> None:
    store = LocalEngagementStore(tmp_path)
    engagement, targets = _engagement()
    path = store.save(engagement, targets)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["engagement"]["mode"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EngagementStoreError, match="Invalid stored engagement"):
        store.load(engagement.engagement_id)
