from __future__ import annotations

from dataclasses import dataclass

import pytest

from hardware_pentest.core.hardware import (
    DeploymentMethod,
    EvidenceChannel,
    HardwareDescriptor,
    HardwareDirection,
    HardwareIdentity,
    HardwareInterface,
    HardwareRequirement,
    ToolchainDescriptor,
)
from hardware_pentest.core.models import InstrumentIdentity
from hardware_pentest.providers import (
    FlipperHardwareProvider,
    HardwareProviderRegistry,
    SimulatedHardwareProvider,
)


def _descriptor() -> HardwareDescriptor:
    return HardwareDescriptor(
        identity=HardwareIdentity(
            provider_id="board:1",
            kind="development-board",
            model="Example Board",
            transport="usb",
            firmware_version="1.0",
            provider_version="0.1",
        ),
        architecture="example-mcu",
        interfaces=(
            HardwareInterface(
                interface_id="header.uart0",
                kind="uart",
                direction=HardwareDirection.BIDIRECTIONAL,
                attributes={"pins": ["TX", "RX"], "logic_volts": 3.3},
            ),
            HardwareInterface(
                interface_id="header.spi0",
                kind="spi",
                direction=HardwareDirection.BIDIRECTIONAL,
            ),
        ),
        artifact_types=("firmware-bin",),
        toolchains=(
            ToolchainDescriptor(
                toolchain_id="example-sdk",
                artifact_types=("firmware-bin",),
                languages=("c",),
                available=True,
            ),
        ),
        deployment_methods=(
            DeploymentMethod(
                method_id="usb-flash",
                artifact_types=("firmware-bin",),
                transport="usb",
                recoverable=True,
            ),
        ),
        evidence_channels=(
            EvidenceChannel(
                channel_id="serial-json",
                transport="usb-cdc",
                media_type="application/json",
                max_bytes=4096,
            ),
        ),
        limits={"logic_volts": 3.3},
        limitations=("Lab descriptor",),
    )


def test_hardware_descriptor_round_trips_with_stable_fingerprint() -> None:
    descriptor = _descriptor()
    restored = HardwareDescriptor.from_dict(descriptor.to_dict())

    assert restored == descriptor
    assert restored.fingerprint == descriptor.fingerprint
    assert len(descriptor.fingerprint) == 64


def test_hardware_descriptor_top_level_metadata_is_immutable() -> None:
    descriptor = _descriptor()

    with pytest.raises(TypeError):
        descriptor.limits["logic_volts"] = 5.0  # type: ignore[index]
    with pytest.raises(TypeError):
        descriptor.interfaces[0].attributes["logic_volts"] = 5.0  # type: ignore[index]


def test_hardware_descriptor_rejects_unknown_schema_and_duplicate_resources() -> None:
    payload = _descriptor().to_dict()
    payload["schema_version"] = "999"
    with pytest.raises(ValueError, match="Unsupported hardware descriptor schema"):
        HardwareDescriptor.from_dict(payload)

    interface = HardwareInterface(
        interface_id="same",
        kind="uart",
        direction=HardwareDirection.BIDIRECTIONAL,
    )
    with pytest.raises(ValueError, match="Duplicate interface_id"):
        HardwareDescriptor(
            identity=_descriptor().identity,
            architecture="example-mcu",
            interfaces=(interface, interface),
            artifact_types=("bin",),
        )


def test_compatibility_reports_missing_physical_requirements() -> None:
    descriptor = _descriptor()
    requirement = HardwareRequirement(
        required_interface_kinds=frozenset({"uart", "can"}),
        accepted_artifact_types=frozenset({"uf2"}),
        accepted_architectures=frozenset({"rp2040"}),
    )

    result = descriptor.compatibility(requirement)

    assert result.compatible is False
    assert any("can" in reason for reason in result.reasons)
    assert any("artifact" in reason for reason in result.reasons)
    assert any("architecture" in reason for reason in result.reasons)


def test_simulated_provider_can_be_discovered_without_vendor_specific_logic() -> None:
    registry = HardwareProviderRegistry()
    registry.register(SimulatedHardwareProvider())

    assert registry.provider_ids() == ["simulator-1"]
    descriptor = registry.descriptors()[0]
    assert descriptor.architecture == "simulated"
    assert {"uart", "spi", "i2c", "gpio"}.issubset(descriptor.interface_kinds())

    routes = registry.compatible(
        HardwareRequirement(
            required_interface_kinds=frozenset({"uart"}),
            accepted_artifact_types=frozenset({"simulated-action"}),
        )
    )
    assert [route.descriptor.identity.provider_id for route in routes] == ["simulator-1"]


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


def test_flipper_is_provider_one_not_a_fixed_capability_catalog() -> None:
    provider = FlipperHardwareProvider(_FakeFlipperAdapter())  # type: ignore[arg-type]
    descriptor = provider.describe_hardware()

    assert descriptor.identity.provider_id == "flipper:LAB123"
    assert descriptor.architecture == "stm32wb55rg"
    assert {"gpio", "uart", "spi", "i2c", "nfc", "subghz", "infrared"}.issubset(
        descriptor.interface_kinds()
    )
    assert "fap" in descriptor.artifact_types
    assert descriptor.compatibility(
        HardwareRequirement(
            required_interface_kinds=frozenset({"uart"}),
            accepted_artifact_types=frozenset({"fap"}),
        )
    ).compatible


@dataclass
class _IdentityMismatchProvider:
    def probe_hardware(self) -> HardwareIdentity:
        return HardwareIdentity("provider:a", "test", "A", "in-process")

    def describe_hardware(self) -> HardwareDescriptor:
        return HardwareDescriptor(
            identity=HardwareIdentity("provider:b", "test", "B", "in-process"),
            architecture="test",
            interfaces=(),
            artifact_types=(),
        )


def test_provider_registry_fails_closed_on_identity_mismatch() -> None:
    registry = HardwareProviderRegistry()

    with pytest.raises(ValueError, match="identity changed"):
        registry.register(_IdentityMismatchProvider())
