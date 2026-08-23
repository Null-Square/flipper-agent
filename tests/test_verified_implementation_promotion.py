from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hardware_pentest.core.hardware import HardwareDescriptor, HardwareIdentity
from hardware_pentest.core.models import (
    Action,
    ActionClass,
    CapabilityMaturity,
    InstrumentIdentity,
)
from hardware_pentest.synthesis import (
    BuildArtifact,
    CapabilityImplementationRecord,
    FlipperImplementationPromoter,
    FlipperStoredImplementationCodec,
    GeneratedAppManifest,
    LocalCapabilityImplementationStore,
    VerifiedGeneratedFlipperAdapter,
)
from hardware_pentest.verification import LocalVerificationStore


def _identity(*, firmware: str = "1.4.2") -> InstrumentIdentity:
    return InstrumentIdentity(
        instrument_id="flipper:LAB123",
        kind="flipper-zero",
        model="Flipper Zero",
        transport="usb-cli",
        firmware_version=firmware,
        adapter_version="0.3.0-dev",
    )


def _descriptor(
    identity: InstrumentIdentity,
    *,
    marker: str = "stable",
) -> HardwareDescriptor:
    return HardwareDescriptor(
        identity=HardwareIdentity(
            provider_id=identity.instrument_id,
            kind=identity.kind,
            model=identity.model,
            transport=identity.transport,
            firmware_version=identity.firmware_version,
            provider_version=identity.adapter_version,
        ),
        architecture="stm32wb55rg",
        interfaces=(),
        artifact_types=("fap",),
        limits={"fixture_marker": marker},
    )


def _manifest() -> GeneratedAppManifest:
    return GeneratedAppManifest(
        app_id="hpa_gen_uart_autodetect",
        display_name="HPA UART Autodetect",
        capability_id="internal.uart.autodetect",
        declared_interfaces=("uart",),
        declared_action_class=ActionClass.OBSERVE,
        requested_api_groups=("gpio", "logging"),
        max_runtime_seconds=5.0,
        expected_evidence=("Candidate UART framing observations",),
    )


def _artifact(tmp_path: Path, payload: bytes = b"compiled-uart-helper") -> BuildArtifact:
    project = tmp_path / "build"
    project.mkdir(parents=True, exist_ok=True)
    artifact_path = project / "hpa_gen_uart_autodetect.fap"
    artifact_path.write_bytes(payload)
    return BuildArtifact(
        app_id="hpa_gen_uart_autodetect",
        project_root=project,
        artifact_path=artifact_path,
        artifact_sha256=hashlib.sha256(payload).hexdigest(),
        source_sha256="1" * 64,
        source_tree_sha256="2" * 64,
        app_manifest_sha256="3" * 64,
        synthesis_manifest_sha256="4" * 64,
        builder="ufbt",
        builder_version="ufbt 0.2-test",
        build_command=("ufbt",),
        build_log_sha256="5" * 64,
        build_log_path=project / "build.log",
    )


def _implementation(
    artifact: BuildArtifact,
    descriptor: HardwareDescriptor,
) -> CapabilityImplementationRecord:
    return CapabilityImplementationRecord(
        request_id="req-uart-1",
        capability_id="internal.uart.autodetect",
        target_id="camera-1",
        backend_id="flipper-fap-v1",
        provider_id=descriptor.identity.provider_id,
        hardware_descriptor_sha256=descriptor.fingerprint,
        artifact_type="fap",
        artifact_sha256=artifact.artifact_sha256,
        action_class=ActionClass.OBSERVE,
        required_interfaces=("uart",),
        build_provider_id="ufbt",
        build_provider_version=artifact.builder_version,
        deployment_provider_id="flipper-generated-fap",
        evidence_channel_ids=("generated-app-json",),
        maturity=CapabilityMaturity.IMPLEMENTED,
        limitations=("Needs exact HIL verification",),
    )


def _stored(tmp_path: Path):
    identity = _identity()
    descriptor = _descriptor(identity)
    artifact = _artifact(tmp_path)
    record = _implementation(artifact, descriptor)
    store = LocalCapabilityImplementationStore(tmp_path / "implementations")
    stored = FlipperStoredImplementationCodec.persist(
        store,
        record=record,
        manifest=_manifest(),
        artifact=artifact,
    )
    return identity, descriptor, stored


def _evidence(tmp_path: Path, name: str, content: bytes = b"hil-pass") -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def _record_exact_verification(
    verification: LocalVerificationStore,
    *,
    identity: InstrumentIdentity,
    stored,
    descriptor: HardwareDescriptor,
    evidence: Path,
    passed: bool = True,
    tested_at: datetime | None = None,
):
    return verification.record(
        identity=identity,
        capability_id=stored.record.capability_id,
        procedure_id="generated.flipper.hil.v1",
        procedure_version="1",
        passed=passed,
        evidence_path=evidence,
        tested_at=tested_at,
        implementation_id=stored.record.implementation_id,
        implementation_artifact_sha256=stored.record.artifact_sha256,
        hardware_descriptor_sha256=descriptor.fingerprint,
    )


def test_exact_verified_stored_implementation_promotes_after_restart(tmp_path: Path) -> None:
    identity, descriptor, stored = _stored(tmp_path)
    verification = LocalVerificationStore(tmp_path / "verification")
    record = _record_exact_verification(
        verification,
        identity=identity,
        stored=stored,
        descriptor=descriptor,
        evidence=_evidence(tmp_path, "pass.json"),
    )

    restarted_store = LocalCapabilityImplementationStore(tmp_path / "implementations")
    restarted = restarted_store.load(stored.record.implementation_id)
    adapter = FlipperImplementationPromoter(verification).bind(
        restarted,
        descriptor=descriptor,
        identity=identity,
        port="COM_TEST",
    )

    assert isinstance(adapter, VerifiedGeneratedFlipperAdapter)
    capability = adapter.capabilities()[0]
    assert capability.maturity is CapabilityMaturity.HARDWARE_VERIFIED
    assert capability.quality["hardware_verified"] is True
    assert capability.quality["verification_record_id"] == record.record_id
    validation = adapter.validate(
        Action(
            action_id="uart-autodetect",
            capability_id="internal.uart.autodetect",
            target_id="camera-1",
            action_class=ActionClass.OBSERVE,
        )
    )
    assert validation.valid is True


def test_same_capability_different_artifact_does_not_inherit_verification(tmp_path: Path) -> None:
    identity, descriptor, stored = _stored(tmp_path)
    verification = LocalVerificationStore(tmp_path / "verification")
    _record_exact_verification(
        verification,
        identity=identity,
        stored=stored,
        descriptor=descriptor,
        evidence=_evidence(tmp_path, "pass.json"),
    )

    second_artifact = _artifact(tmp_path / "second", b"different-compiled-helper")
    second_record = _implementation(second_artifact, descriptor)
    second_store = LocalCapabilityImplementationStore(tmp_path / "second-store")
    second = FlipperStoredImplementationCodec.persist(
        second_store,
        record=second_record,
        manifest=_manifest(),
        artifact=second_artifact,
    )

    promoter = FlipperImplementationPromoter(verification)
    assert promoter.verification_record(
        second,
        descriptor=descriptor,
        identity=identity,
    ) is None


def test_descriptor_drift_revokes_verified_implementation(tmp_path: Path) -> None:
    identity, descriptor, stored = _stored(tmp_path)
    verification = LocalVerificationStore(tmp_path / "verification")
    _record_exact_verification(
        verification,
        identity=identity,
        stored=stored,
        descriptor=descriptor,
        evidence=_evidence(tmp_path, "pass.json"),
    )
    changed_descriptor = _descriptor(identity, marker="changed")

    promoter = FlipperImplementationPromoter(verification)
    assert promoter.verification_record(
        stored,
        descriptor=changed_descriptor,
        identity=identity,
    ) is None


def test_firmware_drift_revokes_verified_implementation(tmp_path: Path) -> None:
    identity, descriptor, stored = _stored(tmp_path)
    verification = LocalVerificationStore(tmp_path / "verification")
    _record_exact_verification(
        verification,
        identity=identity,
        stored=stored,
        descriptor=descriptor,
        evidence=_evidence(tmp_path, "pass.json"),
    )
    changed_identity = _identity(firmware="1.5.0")
    changed_descriptor = _descriptor(changed_identity)

    promoter = FlipperImplementationPromoter(verification)
    assert promoter.verification_record(
        stored,
        descriptor=changed_descriptor,
        identity=changed_identity,
    ) is None


def test_newer_failed_exact_verification_revokes_older_pass(tmp_path: Path) -> None:
    identity, descriptor, stored = _stored(tmp_path)
    verification = LocalVerificationStore(tmp_path / "verification")
    first = datetime(2026, 8, 23, 8, 0, tzinfo=UTC)
    _record_exact_verification(
        verification,
        identity=identity,
        stored=stored,
        descriptor=descriptor,
        evidence=_evidence(tmp_path, "pass.json"),
        passed=True,
        tested_at=first,
    )
    _record_exact_verification(
        verification,
        identity=identity,
        stored=stored,
        descriptor=descriptor,
        evidence=_evidence(tmp_path, "fail.json", b"hil-fail"),
        passed=False,
        tested_at=first + timedelta(minutes=1),
    )

    promoter = FlipperImplementationPromoter(verification)
    assert promoter.verification_record(
        stored,
        descriptor=descriptor,
        identity=identity,
    ) is None


def test_tampered_hil_evidence_revokes_verified_implementation(tmp_path: Path) -> None:
    identity, descriptor, stored = _stored(tmp_path)
    verification = LocalVerificationStore(tmp_path / "verification")
    record = _record_exact_verification(
        verification,
        identity=identity,
        stored=stored,
        descriptor=descriptor,
        evidence=_evidence(tmp_path, "pass.json"),
    )
    (verification.root / record.evidence_reference).write_bytes(b"tampered")

    promoter = FlipperImplementationPromoter(verification)
    assert promoter.verification_record(
        stored,
        descriptor=descriptor,
        identity=identity,
    ) is None


def test_unbound_capability_verification_never_promotes_generated_artifact(tmp_path: Path) -> None:
    identity, descriptor, stored = _stored(tmp_path)
    verification = LocalVerificationStore(tmp_path / "verification")
    verification.record(
        identity=identity,
        capability_id=stored.record.capability_id,
        procedure_id="legacy-capability-hil",
        procedure_version="1",
        passed=True,
        evidence_path=_evidence(tmp_path, "legacy.json"),
    )

    promoter = FlipperImplementationPromoter(verification)
    assert promoter.verification_record(
        stored,
        descriptor=descriptor,
        identity=identity,
    ) is None


def test_partial_generated_verification_binding_is_rejected(tmp_path: Path) -> None:
    identity, descriptor, stored = _stored(tmp_path)
    verification = LocalVerificationStore(tmp_path / "verification")

    with pytest.raises(ValueError, match="requires implementation ID"):
        verification.record(
            identity=identity,
            capability_id=stored.record.capability_id,
            procedure_id="generated.flipper.hil.v1",
            procedure_version="1",
            passed=True,
            evidence_path=_evidence(tmp_path, "partial.json"),
            implementation_id=stored.record.implementation_id,
        )
