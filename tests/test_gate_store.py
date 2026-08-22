from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from hardware_pentest.service.gates import GateKind, LocalGateStore


def test_gate_grant_is_one_shot_and_bound_to_exact_step(tmp_path) -> None:
    store = LocalGateStore(tmp_path)
    now = datetime.now(UTC)
    grant = store.grant(
        assessment_id="assessment-1",
        step_id="assessment-1:wifi",
        kind=GateKind.APPROVAL,
        ttl=timedelta(minutes=5),
        now=now,
    )

    assert store.available(
        assessment_id="assessment-1",
        step_id="assessment-1:wifi",
        kind=GateKind.APPROVAL,
        now=now,
    ) == grant
    assert store.available(
        assessment_id="assessment-1",
        step_id="assessment-1:other",
        kind=GateKind.APPROVAL,
        now=now,
    ) is None

    consumed = store.consume(
        assessment_id="assessment-1",
        step_id="assessment-1:wifi",
        kind=GateKind.APPROVAL,
        now=now,
    )
    assert consumed == grant
    assert store.consume(
        assessment_id="assessment-1",
        step_id="assessment-1:wifi",
        kind=GateKind.APPROVAL,
        now=now,
    ) is None


def test_expired_gate_grant_is_not_available(tmp_path) -> None:
    store = LocalGateStore(tmp_path)
    now = datetime.now(UTC)
    store.grant(
        assessment_id="assessment-1",
        step_id="assessment-1:wifi",
        kind=GateKind.APPROVAL,
        ttl=timedelta(seconds=1),
        now=now,
    )

    assert store.available(
        assessment_id="assessment-1",
        step_id="assessment-1:wifi",
        kind=GateKind.APPROVAL,
        now=now + timedelta(seconds=2),
    ) is None


def test_tampered_gate_grant_never_satisfies_gate(tmp_path) -> None:
    store = LocalGateStore(tmp_path)
    now = datetime.now(UTC)
    grant = store.grant(
        assessment_id="assessment-1",
        step_id="assessment-1:wifi",
        kind=GateKind.HUMAN_ACTION,
        now=now,
    )
    path = store.pending_dir / f"{grant.grant_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["step_id"] = "assessment-1:other"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert store.available(
        assessment_id="assessment-1",
        step_id="assessment-1:wifi",
        kind=GateKind.HUMAN_ACTION,
        now=now,
    ) is None
