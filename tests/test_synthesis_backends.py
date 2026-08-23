from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from hardware_pentest.core.hardware import HardwareIdentity
from hardware_pentest.core.models import ActionClass, InstrumentIdentity
from hardware_pentest.providers import (
    FlipperHardwareProvider,
    HardwareProviderRegistry,
    SimulatedHardwareProvider,
)
from hardware_pentest.synthesis import (
    CapabilitySynthesisRequest,
    CapabilitySynthesisRouter,
    FlipperSynthesisBackend,
    GeneratedAppManifest,
    GeneratedProjectWriter,
    GeneratedSourcePolicy,
    SynthesisBackendRejected,
    UfbTBuilder,
)

SAFE_GPIO_SOURCE = r'''
#include <furi.h>
#include <furi_hal_gpio.h>
#include "hpa_runtime.h"

int32_t hpa_generated_main(void* context) {
    UNUSED(context);
    bool value = furi_hal_gpio_read(&gpio_ext_pa7);
    const char* result = value
        ? "{\"schema_version\":\"1\",\"status\":\"success\",\"observations\":{\"PA7\":1}}"
        : "{\"schema_version\":\"1\",\"status\":\"success\",\"observations\":{\"PA7\":0}}";
    return hpa_write_evidence_json(result) ? 0 : 1;
}
'''.strip()


def _request(
    *,
    interfaces: tuple[str, ...] = ("gpio",),
    artifacts: tuple[str, ...] = (),
    architectures: tuple[str, ...] = (),
) -> CapabilitySynthesisRequest:
    return CapabilitySynthesisRequest(
        request_id="req-provider-1",
        capability_id="generated.gpio.sample",
        target_id="lab-target",
        objective="Read one operator-prepared GPIO input and return structured evidence.",
        requested_interfaces=interfaces,
        max_action_class=ActionClass.OBSERVE,
        expected_evidence=("Observed GPIO input level",),
        accepted_artifact_types=artifacts,
        accepted_architectures=architectures,
    )


def _manifest() -> GeneratedAppManifest:
    return GeneratedAppManifest(
        app_id="hpa_gen_gpio_sample",
        display_name="HPA GPIO Sample",
        capability_id="generated.gpio.sample",
        declared_interfaces=("gpio",),
        declared_action_class=ActionClass.OBSERVE,
        requested_api_groups=("gpio", "logging"),
        max_runtime_seconds=5.0,
        expected_evidence=("Observed GPIO input level",),
    )


@dataclass
class _FakeFlipperAdapter:
    def probe(self) -> InstrumentIdentity:
        return InstrumentIdentity(
            instrument_id="flipper:LAB123",
            kind="flipper-zero",
            model="Flipper Zero",
            transport="usb-cli",
            firmware_version="1.3.4",
            adapter_version="0.7.0-dev",
        )


def _flipper_provider() -> FlipperHardwareProvider:
    return FlipperHardwareProvider(_FakeFlipperAdapter())  # type: ignore[arg-type]


def _backend(tmp_path: Path) -> FlipperSynthesisBackend:
    def runner(command, **kwargs):
        if command == ["ufbt"]:
            dist = Path(kwargs["cwd"]) / "dist"
            dist.mkdir()
            (dist / "hpa_gen_gpio_sample.fap").write_bytes(b"compiled-fap")
            return subprocess.CompletedProcess(command, 0, stdout="build ok\n", stderr="")
        if command == ["ufbt", "--version"]:
            return subprocess.CompletedProcess(command, 0, stdout="ufbt 0.2-test\n", stderr="")
        raise AssertionError(command)

    return FlipperSynthesisBackend(
        policy=GeneratedSourcePolicy(),
        project_writer=GeneratedProjectWriter(tmp_path / "generated"),
        builder=UfbTBuilder(runner=runner, timeout_seconds=10),
    )


def test_router_selects_compatible_provider_before_source_generation(tmp_path: Path) -> None:
    providers = HardwareProviderRegistry()
    providers.register(SimulatedHardwareProvider())
    providers.register(_flipper_provider())
    backend = _backend(tmp_path)
    router = CapabilitySynthesisRouter(providers=providers, backends=(backend,))

    routes = router.evaluate(_request())
    selected = router.select(_request())

    assert len(routes) == 2
    assert selected.descriptor.identity.provider_id == "flipper:LAB123"
    assert selected.compatibility.compatible is True
    assert selected.compatibility.artifact_type == "fap"
    simulated = next(
        route for route in routes if route.descriptor.identity.provider_id == "simulator-1"
    )
    assert simulated.compatibility.compatible is False
    assert any("architecture" in reason for reason in simulated.compatibility.reasons)


def test_request_can_exclude_flipper_without_generating_source(tmp_path: Path) -> None:
    providers = HardwareProviderRegistry()
    providers.register(_flipper_provider())
    router = CapabilitySynthesisRouter(providers=providers, backends=(_backend(tmp_path),))

    with pytest.raises(LookupError, match="No synthesis route"):
        router.select(_request(artifacts=("uf2",)))


def test_flipper_backend_rejects_missing_physical_interface_before_policy_or_build(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    descriptor = _flipper_provider().describe_hardware()
    request = _request(interfaces=("can",))

    with pytest.raises(SynthesisBackendRejected, match="missing interface"):
        backend.synthesize(request, descriptor, _manifest(), SAFE_GPIO_SOURCE)

    assert not (tmp_path / "generated" / _manifest().app_id).exists()


def test_flipper_backend_builds_provider_bound_implementation_record(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    descriptor = _flipper_provider().describe_hardware()

    result = backend.synthesize(_request(), descriptor, _manifest(), SAFE_GPIO_SOURCE)

    assert result.policy.allowed is True
    assert result.implementation is not None
    implementation = result.implementation
    assert implementation.provider_id == descriptor.identity.provider_id
    assert implementation.hardware_descriptor_sha256 == descriptor.fingerprint
    assert implementation.backend_id == "flipper-fap-v1"
    assert implementation.artifact_type == "fap"
    assert implementation.artifact_sha256 == result.artifact.artifact_sha256
    assert implementation.build_provider_id == "ufbt"
    assert implementation.deployment_provider_id == "flipper-generated-fap"
    assert implementation.evidence_channel_ids == ("generated-app-json",)
    assert implementation.maturity.value == "implemented"
    assert implementation.implementation_id.startswith("impl:")
    assert len(implementation.implementation_id) == 69


def test_deployment_binding_rejects_descriptor_drift_before_serial_access(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    descriptor = _flipper_provider().describe_hardware()
    result = backend.synthesize(_request(), descriptor, _manifest(), SAFE_GPIO_SOURCE)
    assert result.implementation is not None

    changed_identity = HardwareIdentity(
        provider_id=descriptor.identity.provider_id,
        kind=descriptor.identity.kind,
        model=descriptor.identity.model,
        transport=descriptor.identity.transport,
        firmware_version="changed-firmware",
        provider_version=descriptor.identity.provider_version,
    )
    changed = type(descriptor)(
        identity=changed_identity,
        architecture=descriptor.architecture,
        interfaces=descriptor.interfaces,
        artifact_types=descriptor.artifact_types,
        toolchains=descriptor.toolchains,
        deployment_methods=descriptor.deployment_methods,
        evidence_channels=descriptor.evidence_channels,
        limits=descriptor.limits,
        limitations=descriptor.limitations,
    )

    with pytest.raises(ValueError, match="descriptor changed"):
        backend.deployment_provider.bind(
            implementation=result.implementation,
            artifact=result.artifact,
            descriptor=changed,
            manifest=_manifest(),
            port="/dev/ttyACM0",
        )
