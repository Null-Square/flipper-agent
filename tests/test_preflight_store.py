from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from hardware_pentest.core.models import InstrumentIdentity
from hardware_pentest.preflight import PreflightReport
from hardware_pentest.preflight.store import LocalPreflightStore


def identity(name: str = "composite:abc") -> InstrumentIdentity:
    return InstrumentIdentity(
        instrument_id=name,
        kind="flipper-marauder-composite",
        model="Flipper Zero + ESP32 Marauder",
        transport="usb+usb-serial",
        firmware_version="state-abc",
        adapter_version="composite-0.1",
    )


def report(*, ready_identity: InstrumentIdentity | None = None, ready: bool = True) -> PreflightReport:
    composite = ready_identity if ready else None
    return PreflightReport(
        checks=(),
        flipper_identity=None,
        marauder_identity=None,
        composite_identity=composite,
        composite_components=None,
        verified_capabilities={"flipper": (), "marauder": ()},
    )


def test_recent_matching_ready_record_opens_gate(tmp_path) -> None:
    store = LocalPreflightStore(tmp_path / "preflight")
    expected = identity()
    tested_at = datetime.now(UTC) - timedelta(minutes=1)
    record = store.record(report(ready_identity=expected), tested_at=tested_at)

    gate = store.require_recent_ready(
        expected,
        max_age=timedelta(minutes=15),
        now=tested_at + timedelta(minutes=2),
    )

    assert gate.valid is True
    assert gate.record is not None
    assert gate.record.record_id == record.record_id


def test_stale_record_fails_closed(tmp_path) -> None:
    store = LocalPreflightStore(tmp_path / "preflight")
    expected = identity()
    tested_at = datetime.now(UTC) - timedelta(minutes=30)
    store.record(report(ready_identity=expected), tested_at=tested_at)

    gate = store.require_recent_ready(
        expected,
        max_age=timedelta(minutes=15),
        now=tested_at + timedelta(minutes=20),
    )

    assert gate.valid is False
    assert "stale" in gate.reason.lower()


def test_different_composite_identity_does_not_open_gate(tmp_path) -> None:
    store = LocalPreflightStore(tmp_path / "preflight")
    store.record(report(ready_identity=identity("composite:one")))

    gate = store.require_recent_ready(identity("composite:two"))

    assert gate.valid is False
    assert gate.record is None


def test_tampered_record_is_ignored(tmp_path) -> None:
    store = LocalPreflightStore(tmp_path / "preflight")
    expected = identity()
    record = store.record(report(ready_identity=expected))
    path = store.records_dir / f"{record.record_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["ready"] = False
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert store.records() == ()
    gate = store.require_recent_ready(expected)
    assert gate.valid is False


def test_future_record_fails_closed(tmp_path) -> None:
    store = LocalPreflightStore(tmp_path / "preflight")
    expected = identity()
    current = datetime.now(UTC)
    store.record(report(ready_identity=expected), tested_at=current + timedelta(minutes=1))

    gate = store.require_recent_ready(expected, now=current)

    assert gate.valid is False
    assert "future" in gate.reason.lower()
