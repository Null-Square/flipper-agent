from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

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


def test_raw_artifact_hash_matches_exact_persisted_bytes(tmp_path) -> None:
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
    expected = b'{"sample":"raw"}\n'

    assert raw_path.read_bytes() == expected
    assert record.raw_artifact_hash == hashlib.sha256(expected).hexdigest()


def test_raw_artifact_never_uses_platform_text_newline_translation(
    tmp_path, monkeypatch
) -> None:
    original_write_text = Path.write_text

    def guarded_write_text(path: Path, data: str, *args, **kwargs) -> int:
        if path.name.endswith(".raw.json"):
            raise AssertionError("raw evidence must be persisted as exact bytes, not text")
        return original_write_text(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", guarded_write_text)
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
    raw_path.write_bytes(b'{"tampered":true}\r\n')

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
