from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from hardware_pentest.adapters.flipper.adapter import (
    ADAPTER_VERSION,
    INFRARED_OBSERVE,
    FlipperAdapter,
)
from hardware_pentest.core.models import InstrumentIdentity
from hardware_pentest.verification import LocalVerificationStore, VerificationCheckResult


def identity(*, firmware: str = "1.4.3") -> InstrumentIdentity:
    return InstrumentIdentity(
        instrument_id="flipper:ABC123",
        kind="flipper-zero",
        model="Flipper Zero",
        transport="usb-cli",
        firmware_version=firmware,
        adapter_version=ADAPTER_VERSION,
    )


def evidence(tmp_path, name: str = "evidence.json", content: str = '{"passed":true}'):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def record_pass(store, tmp_path, *, at=None, instrument=None):
    return store.record(
        identity=instrument or identity(),
        capability_id=INFRARED_OBSERVE,
        procedure_id="flipper.infrared.observe.known-source",
        procedure_version="1",
        passed=True,
        evidence_path=evidence(tmp_path),
        checks=(VerificationCheckResult("signal_observed", True, "Known IR source decoded"),),
        tested_at=at,
    )


def test_passed_record_with_intact_evidence_enables_exact_capability(tmp_path) -> None:
    store = LocalVerificationStore(tmp_path / "verification")
    record_pass(store, tmp_path)

    assert store.verified_capabilities(
        identity(),
        {INFRARED_OBSERVE, "wireless.nfc.identify"},
    ) == frozenset({INFRARED_OBSERVE})


def test_tampered_stored_evidence_revokes_capability(tmp_path) -> None:
    store = LocalVerificationStore(tmp_path / "verification")
    record = record_pass(store, tmp_path)
    artifact = store.root / record.evidence_reference
    artifact.write_text("tampered", encoding="utf-8")

    assert store.verified_capabilities(identity(), {INFRARED_OBSERVE}) == frozenset()
    assert store.evidence_is_intact(record) is False


def test_firmware_or_adapter_state_must_match_exactly(tmp_path) -> None:
    store = LocalVerificationStore(tmp_path / "verification")
    record_pass(store, tmp_path)

    verified = store.verified_capabilities(
        identity(firmware="1.4.4"),
        {INFRARED_OBSERVE},
    )
    assert verified == frozenset()

    different_adapter = InstrumentIdentity(
        **{
            **identity().__dict__,
            "adapter_version": "future-adapter",
        }
    )
    assert store.verified_capabilities(different_adapter, {INFRARED_OBSERVE}) == frozenset()


def test_later_failed_record_revokes_earlier_pass(tmp_path) -> None:
    store = LocalVerificationStore(tmp_path / "verification")
    start = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
    record_pass(store, tmp_path, at=start)
    store.record(
        identity=identity(),
        capability_id=INFRARED_OBSERVE,
        procedure_id="flipper.infrared.observe.known-source",
        procedure_version="1",
        passed=False,
        evidence_path=evidence(tmp_path, "failed.json", '{"passed":false}'),
        tested_at=start + timedelta(seconds=1),
    )

    assert store.verified_capabilities(identity(), {INFRARED_OBSERVE}) == frozenset()


def test_unknown_or_unimplemented_capability_is_never_resolved(tmp_path) -> None:
    store = LocalVerificationStore(tmp_path / "verification")
    store.record(
        identity=identity(),
        capability_id="wireless.future.observe",
        procedure_id="test.future",
        procedure_version="1",
        passed=True,
        evidence_path=evidence(tmp_path),
    )

    assert store.verified_capabilities(identity(), {INFRARED_OBSERVE}) == frozenset()


def test_malformed_record_is_ignored_fail_closed(tmp_path) -> None:
    store = LocalVerificationStore(tmp_path / "verification")
    malformed = store.records_dir / "vr-malformed.json"
    malformed.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "record_id": "vr-malformed",
                "capability_id": INFRARED_OBSERVE,
                "tested_at": datetime.now(UTC).isoformat(),
                "passed": "true",
            }
        ),
        encoding="utf-8",
    )

    assert store.records() == ()
    assert store.verified_capabilities(identity(), {INFRARED_OBSERVE}) == frozenset()


def test_naive_verification_timestamp_is_rejected(tmp_path) -> None:
    store = LocalVerificationStore(tmp_path / "verification")
    with pytest.raises(ValueError, match="timezone-aware"):
        record_pass(store, tmp_path, at=datetime(2026, 8, 22, 10, 0))


def test_adapter_uses_resolver_not_string_override_for_production_gate(tmp_path) -> None:
    store = LocalVerificationStore(tmp_path / "verification")
    record_pass(store, tmp_path)

    class IdentityOnlyAdapter(FlipperAdapter):
        def probe(self) -> InstrumentIdentity:
            self._identity = identity()  # type: ignore[attr-defined]
            return self._identity

    adapter = IdentityOnlyAdapter("/dev/not-opened", verification_resolver=store)

    assert [item.capability_id for item in adapter.capabilities()] == [INFRARED_OBSERVE]


def test_string_override_is_blocked_without_explicit_test_opt_in() -> None:
    with pytest.raises(ValueError, match="test/development override"):
        FlipperAdapter(
            "/dev/not-opened",
            verified_capabilities={INFRARED_OBSERVE},
        )
