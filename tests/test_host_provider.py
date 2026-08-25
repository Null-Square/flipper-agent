from hardware_pentest.core.hardware import HardwareDescriptor, HardwareRequirement
from hardware_pentest.providers import (
    HostEnvironmentSnapshot,
    HostHardwareProvider,
    baseline_provider_registry,
)


def _snapshot() -> HostEnvironmentSnapshot:
    return HostEnvironmentSnapshot(
        system="Linux",
        release="6.8.0-test",
        architecture="x86_64",
        python_version="3.11.9",
    )


def test_host_provider_is_stable_provider_zero() -> None:
    provider = HostHardwareProvider(snapshot=_snapshot())

    identity = provider.probe_hardware()
    descriptor = provider.describe_hardware()

    assert identity.provider_id == "host.local"
    assert identity.kind == "host"
    assert identity.transport == "local-runtime"
    assert descriptor.identity == identity
    assert descriptor.architecture == "x86_64"
    assert descriptor.interface_kinds() == frozenset({"filesystem", "process"})


def test_host_descriptor_round_trips_with_stable_fingerprint() -> None:
    descriptor = HostHardwareProvider(snapshot=_snapshot()).describe_hardware()
    restored = HardwareDescriptor.from_dict(descriptor.to_dict())

    assert restored.to_dict() == descriptor.to_dict()
    assert restored.fingerprint == descriptor.fingerprint
    assert HostHardwareProvider(snapshot=_snapshot()).describe_hardware().fingerprint == descriptor.fingerprint


def test_host_descriptor_does_not_claim_raw_shell_or_arbitrary_paths() -> None:
    descriptor = HostHardwareProvider(snapshot=_snapshot()).describe_hardware()
    interfaces = {item.interface_id: item for item in descriptor.interfaces}

    assert interfaces["host.process"].attributes["shell_passthrough"] is False
    assert interfaces["host.filesystem"].attributes["arbitrary_path_access"] is False
    assert descriptor.artifact_types == ()


def test_baseline_provider_registry_always_contains_host() -> None:
    registry = baseline_provider_registry()

    assert registry.provider_ids() == ["host.local"]
    assert registry.descriptor("host.local").identity.provider_id == "host.local"


def test_baseline_registry_can_match_host_resources() -> None:
    registry = baseline_provider_registry()
    routes = registry.compatible(
        HardwareRequirement(required_interface_kinds=frozenset({"filesystem"}))
    )

    assert len(routes) == 1
    assert routes[0].descriptor.identity.provider_id == "host.local"
    assert routes[0].compatibility.compatible is True
