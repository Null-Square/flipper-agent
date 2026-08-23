from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from hardware_pentest.core.hardware import HardwareDescriptor, HardwareIdentity
from hardware_pentest.core.models import (
    ActionClass,
    CapabilityMaturity,
    ExecutionResult,
    ExecutionStatus,
    InstrumentIdentity,
)
from hardware_pentest.synthesis import (
    BuildArtifact,
    CapabilityImplementationRecord,
    FlipperStoredImplementationCodec,
    GeneratedAppManifest,
    GeneratedImplementationHILRunner,
    LocalCapabilityImplementationStore,
)
from hardware_pentest.verification import LocalVerificationStore


def _identity(*, firmware: str = "1.4.3") -> InstrumentIdentity:
    return InstrumentIdentity(
        instrument_id="flipper:LAB123",
        kind="flipper-zero",
        model="Flipper Zero",
        transport="usb-cli",
        firmware_version=firmware,
        adapter_version="0.3.0-dev",
    )


def _descriptor(identity: InstrumentIdentity, *, marker: str = "stable") -> HardwareDescriptor:
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
        app_id="hpa_gen_uart_hil",
        display_name="HPA UART HIL",
        capability_id="internal.uart.autodetect",
        declared_interfaces=("uart",),
        declared_action_class=ActionClass.OBSERVE,
        requested_api_groups=("uart", "logging"),
        max_runtime_seconds=6.0,
        expected_evidence=("UART candidates",),
    )


def _artifact(tmp_path: Path) -> BuildArtifact:
    root = tmp_path / "build"
    root.mkdir()
    artifact_path = root / "hpa_gen_uart_hil.fap"
    artifact_path.write_bytes(b"compiled-uart-hil")
    return BuildArtifact(
        app_id="hpa_gen_uart_hil",
        project_root=root,
        artifact_path=artifact_path,
        artifact_sha256=hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
        source_sha256="1" * 64,
        source_tree_sha256="2" * 64,
        app_manifest_sha256="3" * 64,
        synthesis_manifest_sha256="4" * 64,
        builder="ufbt",
        builder_version="ufbt test",
        build_command=("ufbt",),
        build_log_sha256="5" * 64,
        build_log_path=root / "build.log",
    )


def _stored(tmp_path: Path):
    identity = _identity()
    descriptor = _descriptor(identity)
    artifact = _artifact(tmp_path)
    record = CapabilityImplementationRecord(
        request_id="req-uart-hil",
        capability_id="internal.uart.autodetect",
        target_id="camera-1",
        backend_id="flipper-fap-v1",
        provider_id=identity.instrument_id,
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
    )
    store = LocalCapabilityImplementationStore(tmp_path / "implementations")
    stored = FlipperStoredImplementationCodec.persist(
        store,
        record=record,
        manifest=_manifest(),
        artifact=artifact,
    )
    return identity, descriptor, store, stored


class _ResultAdapter:
    def __init__(self, result: ExecutionResult) -> None:
        self.result = result
        self.actions = []

    def execute(self, action):
        self.actions.append(action)
        return self.result


def _adapter_factory(result: ExecutionResult, calls: list[dict]):
    def factory(port: str, **kwargs):
        calls.append({"port": port, **kwargs})
        return _ResultAdapter(result)

    return factory


def _success_result(artifact_sha256: str, *, baud: int = 115200, sample_bytes: int = 64):
    return ExecutionResult(
        status=ExecutionStatus.SUCCESS,
        instrument_id="flipper:LAB123",
        capability_id="internal.uart.autodetect",
        raw={"generated_app": {"artifact_sha256": artifact_sha256}},
        normalized={
            "schema_version": "1",
            "status": "success",
            "observations": {
                "sample_bytes": sample_bytes,
                "candidates": [
                    {
                        "baud": baud,
                        "parity": "none",
                        "data_bits": 8,
                        "stop_bits": 1,
                    }
                ],
            },
        },
    )


def test_hil_run_executes_exact_artifact_and_records_passing_fixture(tmp_path: Path) -> None:
    identity, descriptor, implementations, stored = _stored(tmp_path)
    verification = LocalVerificationStore(tmp_path / "verification")
    calls: list[dict] = []
    runner = GeneratedImplementationHILRunner(
        implementations=implementations,
        verification=verification,
        evidence_root=tmp_path / "hil-evidence",
        adapter_factory=_adapter_factory(
            _success_result(stored.record.artifact_sha256),
            calls,
        ),
    )

    result = runner.run(
        implementation_id=stored.record.implementation_id,
        port="COM_TEST",
        descriptor=descriptor,
        identity=identity,
        operator_confirmed=True,
        expected_uart_baud=115200,
        min_sample_bytes=32,
    )

    assert result["passed"] is True
    assert result["next_action"] == "assessment_refresh"
    assert Path(str(result["evidence_path"])).is_file()
    assert calls[0]["artifact"].artifact_sha256 == stored.record.artifact_sha256
    record = verification.verified_implementation(
        identity,
        capability_id=stored.record.capability_id,
        implementation_id=stored.record.implementation_id,
        implementation_artifact_sha256=stored.record.artifact_sha256,
        hardware_descriptor_sha256=descriptor.fingerprint,
    )
    assert record is not None
    assert record.record_id == result["verification_record_id"]


@pytest.mark.parametrize(
    ("baud", "sample_bytes", "failed_check"),
    [
        (57600, 64, "uart.expected_baud"),
        (115200, 4, "uart.minimum_sample_bytes"),
    ],
)
def test_hil_fixture_mismatch_records_failure_not_promotion(
    tmp_path: Path,
    baud: int,
    sample_bytes: int,
    failed_check: str,
) -> None:
    identity, descriptor, implementations, stored = _stored(tmp_path)
    verification = LocalVerificationStore(tmp_path / "verification")
    runner = GeneratedImplementationHILRunner(
        implementations=implementations,
        verification=verification,
        evidence_root=tmp_path / "hil-evidence",
        adapter_factory=_adapter_factory(
            _success_result(stored.record.artifact_sha256, baud=baud, sample_bytes=sample_bytes),
            [],
        ),
    )

    result = runner.run(
        implementation_id=stored.record.implementation_id,
        port="COM_TEST",
        descriptor=descriptor,
        identity=identity,
        operator_confirmed=True,
        expected_uart_baud=115200,
        min_sample_bytes=32,
    )

    assert result["passed"] is False
    checks = {item["check_id"]: item["passed"] for item in result["checks"]}
    assert checks[failed_check] is False
    assert verification.verified_implementation(
        identity,
        capability_id=stored.record.capability_id,
        implementation_id=stored.record.implementation_id,
        implementation_artifact_sha256=stored.record.artifact_sha256,
        hardware_descriptor_sha256=descriptor.fingerprint,
    ) is None


def test_descriptor_drift_stops_before_generated_fap_execution(tmp_path: Path) -> None:
    identity, _descriptor_before, implementations, stored = _stored(tmp_path)
    changed_descriptor = _descriptor(identity, marker="changed")
    calls: list[dict] = []
    runner = GeneratedImplementationHILRunner(
        implementations=implementations,
        verification=LocalVerificationStore(tmp_path / "verification"),
        adapter_factory=_adapter_factory(
            _success_result(stored.record.artifact_sha256),
            calls,
        ),
    )

    with pytest.raises(ValueError, match="descriptor is stale"):
        runner.run(
            implementation_id=stored.record.implementation_id,
            port="COM_TEST",
            descriptor=changed_descriptor,
            identity=identity,
            operator_confirmed=True,
            expected_uart_baud=115200,
        )

    assert calls == []


def test_execution_failure_can_only_record_failed_hil(tmp_path: Path) -> None:
    identity, descriptor, implementations, stored = _stored(tmp_path)
    verification = LocalVerificationStore(tmp_path / "verification")
    failed = ExecutionResult(
        status=ExecutionStatus.FAILED,
        instrument_id=identity.instrument_id,
        capability_id=stored.record.capability_id,
        raw={"generated_app": {"artifact_sha256": stored.record.artifact_sha256}},
        error="generated helper timed out",
    )
    runner = GeneratedImplementationHILRunner(
        implementations=implementations,
        verification=verification,
        evidence_root=tmp_path / "hil-evidence",
        adapter_factory=_adapter_factory(failed, []),
    )

    result = runner.run(
        implementation_id=stored.record.implementation_id,
        port="COM_TEST",
        descriptor=descriptor,
        identity=identity,
        operator_confirmed=True,
        expected_uart_baud=115200,
    )

    assert result["passed"] is False
    assert result["execution_status"] == "failed"
    assert verification.verified_implementation(
        identity,
        capability_id=stored.record.capability_id,
        implementation_id=stored.record.implementation_id,
        implementation_artifact_sha256=stored.record.artifact_sha256,
        hardware_descriptor_sha256=descriptor.fingerprint,
    ) is None


def test_hil_run_requires_operator_fixture_confirmation(tmp_path: Path) -> None:
    identity, descriptor, implementations, stored = _stored(tmp_path)
    runner = GeneratedImplementationHILRunner(
        implementations=implementations,
        verification=LocalVerificationStore(tmp_path / "verification"),
    )

    with pytest.raises(PermissionError, match="operator fixture confirmation"):
        runner.run(
            implementation_id=stored.record.implementation_id,
            port="COM_TEST",
            descriptor=descriptor,
            identity=identity,
            operator_confirmed=False,
            expected_uart_baud=115200,
        )
