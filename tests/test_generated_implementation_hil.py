from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from hardware_pentest.core.hardware import HardwareDescriptor, HardwareIdentity
from hardware_pentest.core.models import ActionClass, CapabilityMaturity, InstrumentIdentity
from hardware_pentest.synthesis import (
    BuildArtifact,
    CapabilityImplementationRecord,
    FlipperStoredImplementationCodec,
    GeneratedAppManifest,
    LocalCapabilityImplementationStore,
)
from hardware_pentest.synthesis.hil import GeneratedFlipperHilRecorder
from hardware_pentest.verification import LocalVerificationStore


def _identity() -> InstrumentIdentity:
    return InstrumentIdentity(
        instrument_id="flipper:LAB-HIL",
        kind="flipper-zero",
        model="Flipper Zero",
        transport="usb-cli",
        firmware_version="1.4.2",
        adapter_version="0.7.0-dev",
    )


def _descriptor(identity: InstrumentIdentity, *, marker: str = "same") -> HardwareDescriptor:
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
        artifact_types=("fap",),
        limits={"marker": marker},
    )


def _stored(tmp_path: Path):
    identity = _identity()
    descriptor = _descriptor(identity)
    project = tmp_path / "project"
    project.mkdir()
    artifact_path = project / "hpa_gen_uart_autodetect.fap"
    artifact_path.write_bytes(b"generated-uart-helper")
    digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    artifact = BuildArtifact(
        app_id="hpa_gen_uart_autodetect",
        project_root=project,
        artifact_path=artifact_path,
        artifact_sha256=digest,
        source_sha256="1" * 64,
        source_tree_sha256="2" * 64,
        app_manifest_sha256="3" * 64,
        synthesis_manifest_sha256="4" * 64,
        builder="ufbt",
        builder_version="ufbt test",
        build_command=("ufbt",),
        build_log_sha256="5" * 64,
        build_log_path=project / "build.log",
    )
    manifest = GeneratedAppManifest(
        app_id="hpa_gen_uart_autodetect",
        display_name="UART Autodetect",
        capability_id="internal.uart.autodetect",
        declared_interfaces=("uart",),
        declared_action_class=ActionClass.OBSERVE,
        requested_api_groups=("gpio", "logging"),
        max_runtime_seconds=5.0,
        expected_evidence=("Candidate UART timing",),
    )
    implementation = CapabilityImplementationRecord(
        request_id="request-1",
        capability_id=manifest.capability_id,
        target_id="fixture-1",
        backend_id="flipper-fap-v1",
        provider_id=descriptor.identity.provider_id,
        hardware_descriptor_sha256=descriptor.fingerprint,
        artifact_type="fap",
        artifact_sha256=digest,
        action_class=ActionClass.OBSERVE,
        required_interfaces=("uart",),
        build_provider_id="ufbt",
        build_provider_version="ufbt test",
        deployment_provider_id="flipper-generated-fap",
        evidence_channel_ids=("generated-app-json",),
        maturity=CapabilityMaturity.IMPLEMENTED,
    )
    store = LocalCapabilityImplementationStore(tmp_path / "implementations")
    stored = FlipperStoredImplementationCodec.persist(
        store,
        record=implementation,
        manifest=manifest,
        artifact=artifact,
    )
    return identity, descriptor, store, stored


def test_hil_readiness_requires_exact_active_descriptor(tmp_path: Path) -> None:
    identity, descriptor, store, stored = _stored(tmp_path)
    recorder = GeneratedFlipperHilRecorder(
        implementations=store,
        verification=LocalVerificationStore(tmp_path / "verification"),
    )

    ready = recorder.readiness(
        stored.record.implementation_id,
        identity=identity,
        descriptor=descriptor,
    )
    changed = recorder.readiness(
        stored.record.implementation_id,
        identity=identity,
        descriptor=_descriptor(identity, marker="changed"),
    )

    assert ready.ready_for_hil is True
    assert ready.exact_verification_record_id is None
    assert changed.ready_for_hil is False
    assert changed.descriptor_matches is False


def test_hil_record_requires_explicit_operator_confirmation(tmp_path: Path) -> None:
    identity, descriptor, store, stored = _stored(tmp_path)
    verification = LocalVerificationStore(tmp_path / "verification")
    recorder = GeneratedFlipperHilRecorder(
        implementations=store,
        verification=verification,
    )
    evidence = tmp_path / "evidence.json"
    evidence.write_text('{"observed":true}', encoding="utf-8")

    with pytest.raises(PermissionError, match="Operator confirmation"):
        recorder.record(
            stored.record.implementation_id,
            identity=identity,
            descriptor=descriptor,
            evidence_path=evidence,
            passed=True,
            operator_confirmed=False,
            expected_fixture_confirmed=True,
        )


def test_passing_hil_requires_expected_fixture_behavior(tmp_path: Path) -> None:
    identity, descriptor, store, stored = _stored(tmp_path)
    recorder = GeneratedFlipperHilRecorder(
        implementations=store,
        verification=LocalVerificationStore(tmp_path / "verification"),
    )
    evidence = tmp_path / "evidence.json"
    evidence.write_text('{"observed":false}', encoding="utf-8")

    with pytest.raises(ValueError, match="expected fixture behavior"):
        recorder.record(
            stored.record.implementation_id,
            identity=identity,
            descriptor=descriptor,
            evidence_path=evidence,
            passed=True,
            operator_confirmed=True,
            expected_fixture_confirmed=False,
        )


def test_hil_record_binds_exact_implementation_artifact_and_descriptor(tmp_path: Path) -> None:
    identity, descriptor, store, stored = _stored(tmp_path)
    verification = LocalVerificationStore(tmp_path / "verification")
    recorder = GeneratedFlipperHilRecorder(
        implementations=store,
        verification=verification,
    )
    evidence = tmp_path / "evidence.json"
    evidence.write_text('{"fixture":"expected-uart-pattern"}', encoding="utf-8")

    record = recorder.record(
        stored.record.implementation_id,
        identity=identity,
        descriptor=descriptor,
        evidence_path=evidence,
        passed=True,
        operator_confirmed=True,
        expected_fixture_confirmed=True,
    )

    assert record.passed is True
    assert record.implementation_bound is True
    assert record.implementation_id == stored.record.implementation_id
    assert record.implementation_artifact_sha256 == stored.record.artifact_sha256
    assert record.hardware_descriptor_sha256 == descriptor.fingerprint
    assert verification.verified_implementation(
        identity,
        capability_id=stored.record.capability_id,
        implementation_id=stored.record.implementation_id,
        implementation_artifact_sha256=stored.record.artifact_sha256,
        hardware_descriptor_sha256=descriptor.fingerprint,
    ) == record


def test_hil_record_refuses_descriptor_drift(tmp_path: Path) -> None:
    identity, _descriptor_at_build, store, stored = _stored(tmp_path)
    recorder = GeneratedFlipperHilRecorder(
        implementations=store,
        verification=LocalVerificationStore(tmp_path / "verification"),
    )
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="not compatible"):
        recorder.record(
            stored.record.implementation_id,
            identity=identity,
            descriptor=_descriptor(identity, marker="changed"),
            evidence_path=evidence,
            passed=False,
            operator_confirmed=True,
            expected_fixture_confirmed=False,
        )
