from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hardware_pentest.core.models import (
    Action,
    ActionClass,
    Engagement,
    ExecutionResult,
    ExecutionStatus,
)
from hardware_pentest.evidence.store import EvidenceStoreError, LocalEvidenceStore


def engagement(identifier: str = "evidence-lab") -> Engagement:
    now = datetime.now(UTC)
    return Engagement(
        engagement_id=identifier,
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(minutes=10),
        target_ids=frozenset({"target-a"}),
        allowed_capabilities=("infrared.observe",),
        denied_capabilities=(),
        max_action_class=ActionClass.OBSERVE,
    )


def action() -> Action:
    return Action(
        action_id="action-1",
        capability_id="infrared.observe",
        target_id="target-a",
        action_class=ActionClass.OBSERVE,
        inputs={"duration_seconds": 1.0},
    )


def result() -> ExecutionResult:
    return ExecutionResult(
        status=ExecutionStatus.SUCCESS,
        instrument_id="simulator-1",
        capability_id="infrared.observe",
        raw={"sample": "raw"},
        normalized={"signal_count": 1},
    )


def test_raw_artifact_reference_is_persisted_and_reloads(tmp_path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    now = datetime.now(UTC)

    record = store.record(
        engagement=engagement(),
        action=action(),
        result=result(),
        adapter_version="sim-1",
        started_at=now,
        finished_at=now + timedelta(seconds=1),
    )
    restored = store.get("evidence-lab", record.evidence_id)

    assert record.raw_artifact_reference
    assert restored == record
    assert store.raw_artifact_is_intact(record) is True


def test_tampered_raw_artifact_fails_integrity(tmp_path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    now = datetime.now(UTC)
    record = store.record(
        engagement=engagement(),
        action=action(),
        result=result(),
        adapter_version="sim-1",
        started_at=now,
        finished_at=now,
    )
    assert record.raw_artifact_reference is not None
    raw_path = store.root / record.raw_artifact_reference
    raw_path.write_text('{"tampered":true}\n', encoding="utf-8")

    assert store.raw_artifact_is_intact(record) is False


def test_unsafe_engagement_identifier_cannot_escape_evidence_root(tmp_path) -> None:
    store = LocalEvidenceStore(tmp_path / "evidence")
    now = datetime.now(UTC)

    with pytest.raises(EvidenceStoreError, match="engagement_id"):
        store.record(
            engagement=engagement("../escape"),
            action=action(),
            result=result(),
            adapter_version="sim-1",
            started_at=now,
            finished_at=now,
        )
