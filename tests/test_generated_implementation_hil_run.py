from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from hardware_pentest.core.hardware import HardwareDescriptor, HardwareIdentity
from hardware_pentest.core.models import (
    Action,
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


def _identity(*, firmware: str = "mntm-010") -> InstrumentIdentity:
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


def _manifest(capability_id: str = "internal.uart.autodetect") -> GeneratedAppManifest:
    return GeneratedAppManifest(
        app_id="hpa_gen_uart_hil",
        display_name="HPA UART HIL",
        capability_id=capability_id,
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
        build_log_path=artifact_path,
    )


def _stored(tmp_path: Path, *, capability_id: str = "internal.uart.autodetect"):
    identity = _identity()
    descriptor = _descriptor(identity)
    artifact = _artifact(tmp_path)
    record = CapabilityImplementationRecord(
        request_id="req-uart-hil",
        capability_id=capability_id,
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
        manifest=_manifest(capability_id),
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


def _success_result(
    artifact_sha256: str,
    *,
    instrument_id: str = "flipper:LAB123",
    capability_id: str = "internal.uart.autodetect",
    baud: int = 115200,
    sample_bytes: int = 64,
    cleanup: dict | None = None,
    normalized: dict | None = None,
) -> ExecutionResult:
    if normalized is None:
        normalized = {
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
        }
    if cleanup is None:
        cleanup = {
            "attempted": True,
            "app_removed": True,
            "result_removed": True,
            "errors": (),
        }
    return ExecutionResult(
        status=ExecutionStatus.SUCCESS,
        instrument_id=instrument_id,
        capability_id=capability_id,
        raw={
            "generated_app": {"artifact_sha256": artifact_sha256},
            "cleanup": cleanup,
        },
        normalized=normalized,
    )


def _runner(tmp_path: Path, implementations, result: ExecutionResult, calls: list[dict]):
    verification = LocalVerificationStore(tmp_path / "verification")
    runner = GeneratedImplementationHILRunner(
        implementations=implementations,
        verification=verification,
        evidence_root=tmp_path / "hil-evidence",
        adapter_factory=_adapter_factory(result, calls),
    )
    return runner, verification


def test_default_hil_adapter_validates_persisted_fap_without_mutable_build_tree(
    tmp_path: Path,
) -> None:
    identity, descriptor, implementations, stored = _stored(tmp_path)
    manifest, artifact = FlipperStoredImplementationCodec.restore(stored)
    runner = GeneratedImplementationHILRunner(
        implementations=implementations,
        verification=LocalVerificationStore(tmp_path / "verification-default"),
    )
    adapter = runner.adapter_factory(
        "COM_TEST",
        manifest=manifest,
        artifact=artifact,
        cleanup=True,
    )

    validation = adapter.validate(
        Action(
            action_id="hil:stored",
            capability_id=stored.record.capability_id,
            target_id=stored.record.target_id,
            action_class=stored.record.action_class,
            requires_approval=True,
            requires_human_action=True,
        )
    )

    assert identity.instrument_id == descriptor.identity.provider_id
    assert validation.valid is True
    assert not (artifact.project_root / "main.c").exists()


def test_hil_run_executes_exact_artifact_and_records_runtime_owned_uart_procedure(
    tmp_path: Path,
) -> None:
    identity, descriptor, implementations, stored = _stored(tmp_path)
    calls: list[dict] = []
    runner, verification = _runner(
        tmp_path,
        implementations,
        _success_result(stored.record.artifact_sha256),
        calls,
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
    assert result["procedure_id"] == "adaptive.generated-implementation.uart-autodetect"
    assert result["procedure_version"] == "2"
    assert Path(str(result["evidence_path"])).is_file()
    assert calls[0]["artifact"].artifact_sha256 == stored.record.artifact_sha256
    assert calls[0]["cleanup"] is True
    record = verification.verified_implementation(
        identity,
        capability_id=stored.record.capability_id,
        implementation_id=stored.record.implementation_id,
        implementation_artifact_sha256=stored.record.artifact_sha256,
        hardware_descriptor_sha256=descriptor.fingerprint,
    )
    assert record is not None
    assert record.record_id == result["verification_record_id"]
    evidence = json.loads(Path(str(result["evidence_path"])).read_text(encoding="utf-8"))
    assert evidence["procedure"]["procedure_id"] == result["procedure_id"]
    assert all(item["passed"] for item in result["checks"])


@pytest.mark.parametrize(
    ("baud", "sample_bytes", "failed_check"),
    [
        (57600, 64, "uart.expected_baud"),
        (115200, 4, "uart.minimum_sample_bytes"),
    ],
)
def test_uart_fixture_mismatch_records_failure_not_promotion(
    tmp_path: Path,
    baud: int,
    sample_bytes: int,
    failed_check: str,
) -> None:
    identity, descriptor, implementations, stored = _stored(tmp_path)
    runner, verification = _runner(
        tmp_path,
        implementations,
        _success_result(stored.record.artifact_sha256, baud=baud, sample_bytes=sample_bytes),
        [],
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


@pytest.mark.parametrize(
    ("result_factory", "failed_check"),
    [
        (
            lambda sha: _success_result(sha, instrument_id="flipper:OTHER"),
            "execution.instrument",
        ),
        (
            lambda sha: _success_result(sha, capability_id="internal.spi.capture"),
            "execution.capability",
        ),
        (
            lambda sha: _success_result("f" * 64),
            "execution.implementation_artifact",
        ),
    ],
)
def test_execution_binding_mismatch_cannot_promote(
    tmp_path: Path,
    result_factory,
    failed_check: str,
) -> None:
    identity, descriptor, implementations, stored = _stored(tmp_path)
    execution = result_factory(stored.record.artifact_sha256)
    runner, verification = _runner(tmp_path, implementations, execution, [])

    result = runner.run(
        implementation_id=stored.record.implementation_id,
        port="COM_TEST",
        descriptor=descriptor,
        identity=identity,
        operator_confirmed=True,
        expected_uart_baud=115200,
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


def test_malformed_uart_result_schema_cannot_promote(tmp_path: Path) -> None:
    identity, descriptor, implementations, stored = _stored(tmp_path)
    malformed = {
        "schema_version": "2",
        "status": "success",
        "observations": {
            "sample_bytes": 64,
            "candidates": [{"baud": 115200, "parity": "wat", "data_bits": 8}],
        },
    }
    runner, _verification = _runner(
        tmp_path,
        implementations,
        _success_result(stored.record.artifact_sha256, normalized=malformed),
        [],
    )

    result = runner.run(
        implementation_id=stored.record.implementation_id,
        port="COM_TEST",
        descriptor=descriptor,
        identity=identity,
        operator_confirmed=True,
        expected_uart_baud=115200,
    )

    checks = {item["check_id"]: item["passed"] for item in result["checks"]}
    assert result["passed"] is False
    assert checks["result.schema_version"] is False
    assert checks["uart.candidates_schema"] is False


def test_cleanup_must_be_confirmed_before_promotion(tmp_path: Path) -> None:
    identity, descriptor, implementations, stored = _stored(tmp_path)
    cleanup = {
        "attempted": True,
        "app_removed": False,
        "result_removed": True,
        "errors": ("app still present",),
    }
    runner, verification = _runner(
        tmp_path,
        implementations,
        _success_result(stored.record.artifact_sha256, cleanup=cleanup),
        [],
    )

    result = runner.run(
        implementation_id=stored.record.implementation_id,
        port="COM_TEST",
        descriptor=descriptor,
        identity=identity,
        operator_confirmed=True,
        expected_uart_baud=115200,
    )

    checks = {item["check_id"]: item["passed"] for item in result["checks"]}
    assert result["passed"] is False
    assert checks["cleanup.app_removed"] is False
    assert checks["cleanup.errors_empty"] is False
    assert verification.verified_implementation(
        identity,
        capability_id=stored.record.capability_id,
        implementation_id=stored.record.implementation_id,
        implementation_artifact_sha256=stored.record.artifact_sha256,
        hardware_descriptor_sha256=descriptor.fingerprint,
    ) is None


def test_unknown_generated_capability_has_no_generic_hil_pass_path(tmp_path: Path) -> None:
    identity, descriptor, implementations, stored = _stored(
        tmp_path,
        capability_id="generated.gpio.sample",
    )
    calls: list[dict] = []
    runner, _verification = _runner(
        tmp_path,
        implementations,
        _success_result(
            stored.record.artifact_sha256,
            capability_id="generated.gpio.sample",
        ),
        calls,
    )

    with pytest.raises(ValueError, match="No registered HIL verification procedure"):
        runner.run(
            implementation_id=stored.record.implementation_id,
            port="COM_TEST",
            descriptor=descriptor,
            identity=identity,
            operator_confirmed=True,
            expected_uart_baud=115200,
        )

    assert calls == []


def test_descriptor_or_firmware_drift_stops_before_generated_execution(tmp_path: Path) -> None:
    identity, _descriptor_before, implementations, stored = _stored(tmp_path)
    changed_descriptor = _descriptor(identity, marker="changed")
    calls: list[dict] = []
    runner, _verification = _runner(
        tmp_path,
        implementations,
        _success_result(stored.record.artifact_sha256),
        calls,
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

    firmware_descriptor = replace(
        changed_descriptor,
        identity=replace(changed_descriptor.identity, firmware_version="different"),
    )
    with pytest.raises(ValueError, match="firmware differs"):
        runner.run(
            implementation_id=stored.record.implementation_id,
            port="COM_TEST",
            descriptor=firmware_descriptor,
            identity=identity,
            operator_confirmed=True,
            expected_uart_baud=115200,
        )
    assert calls == []


def test_zero_strength_uart_fixture_is_rejected_before_execution(tmp_path: Path) -> None:
    identity, descriptor, implementations, stored = _stored(tmp_path)
    calls: list[dict] = []
    runner, _verification = _runner(
        tmp_path,
        implementations,
        _success_result(stored.record.artifact_sha256),
        calls,
    )

    with pytest.raises(ValueError, match="between 1 and 1000000"):
        runner.run(
            implementation_id=stored.record.implementation_id,
            port="COM_TEST",
            descriptor=descriptor,
            identity=identity,
            operator_confirmed=True,
            expected_uart_baud=115200,
            min_sample_bytes=0,
        )
    assert calls == []


def test_hil_run_requires_operator_fixture_confirmation(tmp_path: Path) -> None:
    identity, descriptor, implementations, stored = _stored(tmp_path)
    runner, _verification = _runner(
        tmp_path,
        implementations,
        _success_result(stored.record.artifact_sha256),
        [],
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


def test_tampered_verification_artifact_revokes_promotion(tmp_path: Path) -> None:
    identity, descriptor, implementations, stored = _stored(tmp_path)
    runner, verification = _runner(
        tmp_path,
        implementations,
        _success_result(stored.record.artifact_sha256),
        [],
    )
    result = runner.run(
        implementation_id=stored.record.implementation_id,
        port="COM_TEST",
        descriptor=descriptor,
        identity=identity,
        operator_confirmed=True,
        expected_uart_baud=115200,
    )
    assert result["passed"] is True

    record = verification.records()[0]
    artifact_path = verification.root / record.evidence_reference
    artifact_path.write_bytes(b"tampered")

    assert verification.verified_implementation(
        identity,
        capability_id=stored.record.capability_id,
        implementation_id=stored.record.implementation_id,
        implementation_artifact_sha256=stored.record.artifact_sha256,
        hardware_descriptor_sha256=descriptor.fingerprint,
    ) is None
