from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hardware_pentest.core.hardware import (
    DeploymentMethod,
    EvidenceChannel,
    HardwareDescriptor,
    HardwareDirection,
    HardwareIdentity,
    HardwareInterface,
    ToolchainDescriptor,
)
from hardware_pentest.core.models import ActionClass
from hardware_pentest.synthesis import (
    CapabilitySynthesisRequest,
    FlipperStoredImplementationCodec,
    GeneratedAppBuildError,
    GeneratedProjectWriter,
    GeneratedSourcePolicy,
    LocalCapabilityImplementationStore,
    UfbTBuilder,
)
from hardware_pentest.synthesis.candidate import SynthesisCandidateBuilder
from hardware_pentest.synthesis.flipper_backend import (
    FlipperSynthesisCompatibilityBackend,
    evaluate_flipper_synthesis_compatibility,
)
from hardware_pentest.synthesis.router import SynthesisRoute
from hardware_pentest.synthesis.work_order import (
    SynthesisWorkOrder,
    SynthesisWorkOrderState,
)

SAFE_UART_SOURCE = r'''
#include <furi.h>
#include <furi_hal_serial.h>
#include "hpa_runtime.h"

int32_t hpa_generated_main(void* context) {
    UNUSED(context);
    const char* result =
        "{\"schema_version\":\"1\",\"status\":\"success\","
        "\"observations\":{\"sample_bytes\":0,\"candidates\":[]}}";
    return hpa_write_evidence_json(result) ? 0 : 1;
}
'''.strip()


def _descriptor(*, firmware: str = "1.0.0") -> HardwareDescriptor:
    return HardwareDescriptor(
        identity=HardwareIdentity(
            provider_id="flipper:LAB123",
            kind="flipper-zero",
            model="Flipper Zero",
            transport="usb-cli",
            firmware_version=firmware,
            provider_version="0.7.0-dev",
        ),
        architecture="stm32wb55rg",
        interfaces=(
            HardwareInterface(
                interface_id="external.uart",
                kind="uart",
                direction=HardwareDirection.BIDIRECTIONAL,
            ),
        ),
        artifact_types=("fap",),
        toolchains=(
            ToolchainDescriptor(
                toolchain_id="ufbt",
                artifact_types=("fap",),
                languages=("c",),
                available=True,
            ),
        ),
        deployment_methods=(
            DeploymentMethod(
                method_id="fap-storage-loader",
                artifact_types=("fap",),
                transport="usb-cli",
                recoverable=True,
            ),
        ),
        evidence_channels=(
            EvidenceChannel(
                channel_id="generated-app-json",
                transport="app-private-storage",
                media_type="application/json",
                max_bytes=4096,
            ),
        ),
    )


def _order(*, firmware: str = "1.0.0") -> SynthesisWorkOrder:
    descriptor = _descriptor(firmware=firmware)
    request = CapabilitySynthesisRequest(
        request_id="synth:assessment-1:adaptive.uart.autodetect.v1:internal.uart.autodetect",
        capability_id="internal.uart.autodetect",
        target_id="camera-1",
        objective="Passively characterize an operator-prepared UART-like signal.",
        requested_interfaces=("uart",),
        max_action_class=ActionClass.OBSERVE,
        expected_evidence=(
            "bounded sample duration and byte count",
            "candidate baud/parity/data-bit configurations with observed support",
        ),
        constraints={
            "assessment_id": "assessment-1",
            "step_id": "assessment-1:adaptive.uart.autodetect.v1",
            "test_case_id": "adaptive.uart.autodetect.v1",
            "action_inputs": {
                "duration_seconds": 5.0,
                "max_sample_bytes": 2048,
                "max_candidates": 8,
            },
        },
        accepted_artifact_types=("fap",),
        accepted_architectures=("stm32wb55rg",),
    )
    backend = FlipperSynthesisCompatibilityBackend()
    compatibility = evaluate_flipper_synthesis_compatibility(request, descriptor)
    route = SynthesisRoute(
        backend=backend,
        descriptor=descriptor,
        compatibility=compatibility,
    )
    return SynthesisWorkOrder(
        state=SynthesisWorkOrderState.GENERATE_CANDIDATE,
        assessment_id="assessment-1",
        step_id="assessment-1:adaptive.uart.autodetect.v1",
        test_case_id="adaptive.uart.autodetect.v1",
        capability_id="internal.uart.autodetect",
        request=request,
        selected_route=route,
        evaluated_routes=(route,),
        source_generation_contract={
            "language": "c",
            "capability_id": "internal.uart.autodetect",
            "target_id": "camera-1",
            "max_action_class": "OBSERVE",
            "declared_interfaces": ["uart"],
            "requested_api_groups": ["uart", "logging"],
            "authoritative_action_inputs": {
                "duration_seconds": 5.0,
                "max_sample_bytes": 2048,
                "max_candidates": 8,
            },
            "runtime_bounds": {
                "minimum_seconds": 0.1,
                "maximum_seconds": 60.0,
                "requested_duration_seconds": 5.0,
            },
            "result_contract": {
                "filename": "result.json",
                "format": "application/json",
                "writer": "hpa_write_evidence_json",
                "max_bytes": 4096,
            },
            "expected_evidence": list(request.expected_evidence),
        },
        next_action="generate_candidate_source",
    )


def _builder(tmp_path: Path, runner):
    store = LocalCapabilityImplementationStore(tmp_path / "implementations")
    return (
        SynthesisCandidateBuilder(
            project_writer=GeneratedProjectWriter(tmp_path / "generated"),
            builder=UfbTBuilder(runner=runner, timeout_seconds=10),
            implementations=store,
            policy=GeneratedSourcePolicy(),
        ),
        store,
    )


def _successful_runner(calls: list[list[str]]):
    def runner(command, **kwargs):
        calls.append(command)
        if command == ["ufbt"]:
            root = Path(kwargs["cwd"])
            dist = root / "dist"
            dist.mkdir()
            (dist / f"{root.name}.fap").write_bytes(b"compiled-uart-fap")
            return subprocess.CompletedProcess(command, 0, stdout="build ok\n", stderr="")
        if command == ["ufbt", "--version"]:
            return subprocess.CompletedProcess(command, 0, stdout="ufbt 0.2-test\n", stderr="")
        raise AssertionError(command)

    return runner


def test_candidate_build_derives_manifest_builds_and_persists_implemented_fap(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    builder, store = _builder(tmp_path, _successful_runner(calls))
    order = _order()

    result = builder.build(
        order,
        work_order_id=order.work_order_id,
        source=SAFE_UART_SOURCE,
    )

    assert result["state"] == "implemented"
    assert result["maturity"] == "implemented"
    assert result["work_order_id"] == order.work_order_id
    assert result["reused_existing"] is False
    assert result["next_action"] == "run_hil_verification"
    assert calls == [["ufbt"], ["ufbt", "--version"]]

    stored = store.load(str(result["implementation_id"]))
    manifest, artifact = FlipperStoredImplementationCodec.restore(stored)
    assert manifest.capability_id == "internal.uart.autodetect"
    assert manifest.declared_interfaces == ("uart",)
    assert manifest.declared_action_class is ActionClass.OBSERVE
    assert manifest.requested_api_groups == ("uart", "logging")
    assert manifest.max_runtime_seconds == 6.0
    assert artifact.artifact_sha256 == result["artifact_sha256"]
    assert stored.backend_payload["provenance"]["work_order_id"] == order.work_order_id
    assert stored.backend_payload["provenance"]["reviewed_source_sha256"] == result["source_sha256"]


def test_candidate_build_is_idempotent_for_same_work_order_and_source(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    builder, _store = _builder(tmp_path, _successful_runner(calls))
    order = _order()

    first = builder.build(order, work_order_id=order.work_order_id, source=SAFE_UART_SOURCE)
    second = builder.build(order, work_order_id=order.work_order_id, source=SAFE_UART_SOURCE)

    assert second["implementation_id"] == first["implementation_id"]
    assert second["reused_existing"] is True
    assert calls == [["ufbt"], ["ufbt", "--version"]]


def test_stale_work_order_fails_before_policy_or_build(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    builder, store = _builder(tmp_path, _successful_runner(calls))
    order = _order(firmware="2.0.0")
    stale_id = _order(firmware="1.0.0").work_order_id

    with pytest.raises(ValueError, match="stale"):
        builder.build(order, work_order_id=stale_id, source=SAFE_UART_SOURCE)

    assert calls == []
    assert store.records() == ()
    assert not (tmp_path / "generated").exists()


def test_policy_rejection_creates_no_project_build_or_implementation(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    builder, store = _builder(tmp_path, _successful_runner(calls))
    order = _order()
    prohibited = SAFE_UART_SOURCE + "\nvoid tx(void) { furi_hal_subghz_tx(); }"

    with pytest.raises(Exception, match="rejected"):
        builder.build(order, work_order_id=order.work_order_id, source=prohibited)

    assert calls == []
    assert store.records() == ()
    generated = tmp_path / "generated"
    assert not generated.exists() or list(generated.iterdir()) == []


def test_build_failure_creates_no_implementation_record(tmp_path: Path) -> None:
    def failed_runner(command, **kwargs):
        if command == ["ufbt"]:
            return subprocess.CompletedProcess(command, 2, stdout="", stderr="compile failed\n")
        raise AssertionError(command)

    builder, store = _builder(tmp_path, failed_runner)
    order = _order()

    with pytest.raises(GeneratedAppBuildError, match="exit code 2"):
        builder.build(order, work_order_id=order.work_order_id, source=SAFE_UART_SOURCE)

    assert store.records() == ()


def test_caller_has_no_manifest_authority_even_when_source_changes(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    builder, store = _builder(tmp_path, _successful_runner(calls))
    order = _order()
    source = SAFE_UART_SOURCE + "\n/* harmless candidate revision */"

    result = builder.build(order, work_order_id=order.work_order_id, source=source)
    stored = store.load(str(result["implementation_id"]))
    manifest, _artifact = FlipperStoredImplementationCodec.restore(stored)

    assert manifest.capability_id == order.capability_id
    assert manifest.declared_interfaces == order.request.requested_interfaces
    assert manifest.declared_action_class is order.request.max_action_class
    assert manifest.result_filename == "result.json"
    assert manifest.category == "NullSquare"
    assert manifest.app_id.startswith("hpa_gen_")
