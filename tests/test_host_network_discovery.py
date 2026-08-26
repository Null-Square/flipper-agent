from __future__ import annotations

from pathlib import Path

import hardware_pentest.preflight.network as network_module
import hardware_pentest.service.candidate_facade as candidate_facade
import hardware_pentest.service.execution as execution_module
import hardware_pentest.service.facade as base_facade
from hardware_pentest.adapters.host_network import HostNetworkMetadataAdapter
from hardware_pentest.core.models import Action, ActionClass, ExecutionStatus
from hardware_pentest.preflight.network import (
    NetworkAddress,
    NetworkInterfaceCandidate,
    NetworkNeighborCandidate,
    _linux_neighbors,
    _parse_windows_arp,
    network_interfaces,
    network_neighbors,
)
from hardware_pentest.preflight.store import LocalPreflightStore
from hardware_pentest.service import HardwarePentestService
from hardware_pentest.service.execution import InstrumentSelection, build_registry
from hardware_pentest.verification import LocalVerificationStore


def _interface() -> NetworkInterfaceCandidate:
    return NetworkInterfaceCandidate(
        name="Ethernet",
        is_up=True,
        mtu=1500,
        addresses=(
            NetworkAddress(
                family="ipv4",
                address="192.168.1.20",
                netmask="255.255.255.0",
            ),
        ),
    )


def _neighbor() -> NetworkNeighborCandidate:
    return NetworkNeighborCandidate(
        candidate_id="network:192.168.1.87:aa:bb:cc:dd:ee:ff:192.168.1.20",
        ip_address="192.168.1.87",
        mac_address="aa:bb:cc:dd:ee:ff",
        interface="192.168.1.20",
        state="dynamic",
        source="windows-arp-cache",
    )


def _action(capability_id: str) -> Action:
    return Action(
        action_id=f"{capability_id}:target-1",
        capability_id=capability_id,
        target_id="target-1",
        action_class=ActionClass.OBSERVE,
        inputs={},
    )


def test_injected_network_state_is_bounded_and_deterministic() -> None:
    interfaces = network_interfaces(lambda: [_interface()])
    neighbors = network_neighbors(lambda: [_neighbor()])

    assert interfaces == (_interface(),)
    assert neighbors == (_neighbor(),)


def test_windows_arp_parser_reads_cache_without_target_probe() -> None:
    candidates = _parse_windows_arp(
        """
Interface: 192.168.1.20 --- 0x7
  Internet Address      Physical Address      Type
  192.168.1.1           00-11-22-33-44-55     dynamic
  192.168.1.87          aa-bb-cc-dd-ee-ff     dynamic
"""
    )

    assert [item.ip_address for item in candidates] == ["192.168.1.1", "192.168.1.87"]
    assert candidates[1].mac_address == "aa:bb:cc:dd:ee:ff"
    assert candidates[1].interface == "192.168.1.20"
    assert candidates[1].source == "windows-arp-cache"


def test_linux_arp_parser_reads_existing_proc_cache(tmp_path: Path) -> None:
    arp = tmp_path / "arp"
    arp.write_text(
        "IP address       HW type     Flags       HW address            Mask     Device\n"
        "192.168.1.87     0x1         0x2         aa:bb:cc:dd:ee:ff     *        eth0\n",
        encoding="utf-8",
    )

    candidates = _linux_neighbors(arp)

    assert len(candidates) == 1
    assert candidates[0].ip_address == "192.168.1.87"
    assert candidates[0].interface == "eth0"
    assert candidates[0].state == "complete"
    assert candidates[0].source == "linux-proc-arp-cache"


def test_host_network_adapter_never_exposes_active_probe_surface() -> None:
    adapter = HostNetworkMetadataAdapter(
        interface_provider=lambda: [_interface()],
        neighbor_provider=lambda: [_neighbor()],
        interface_available=True,
        neighbor_available=True,
    )

    capabilities = {item.capability_id: item for item in adapter.capabilities()}
    assert set(capabilities) == {
        "network.interface.enumerate",
        "network.neighbor.enumerate",
    }
    for capability in capabilities.values():
        assert capability.instrument_id == "host.local"
        assert capability.action_class is ActionClass.OBSERVE
        assert capability.constraints["active_network_probe"] is False
        assert capability.constraints["subnet_scan"] is False
        assert capability.constraints["port_scan"] is False
        assert capability.constraints["raw_socket_passthrough"] is False
        assert capability.constraints["shell_passthrough"] is False

    result = adapter.execute(_action("network.neighbor.enumerate"))
    assert result.status is ExecutionStatus.SUCCESS
    assert result.raw["active_network_probe"] is False
    assert result.raw["packets_sent"] == 0
    assert result.normalized["neighbor_count"] == 1


def test_network_capabilities_are_additive_host_routes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(execution_module, "network_interface_discovery_available", lambda: True)
    monkeypatch.setattr(execution_module, "network_neighbor_discovery_available", lambda: True)
    monkeypatch.setattr(execution_module, "serial_discovery_available", lambda: False)
    monkeypatch.setattr(execution_module, "usb_discovery_available", lambda: False)

    registry = build_registry(
        InstrumentSelection(backend="simulator"),
        verification=LocalVerificationStore(tmp_path / "verification"),
        preflight=LocalPreflightStore(tmp_path / "preflight"),
    )

    assert registry.choose("network.interface.enumerate").capability.instrument_id == "host.local"
    assert registry.choose("network.neighbor.enumerate").capability.instrument_id == "host.local"


def test_service_discovery_exposes_passive_network_candidates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(base_facade, "serial_discovery_available", lambda: False)
    monkeypatch.setattr(candidate_facade, "usb_discovery_available", lambda: False)
    monkeypatch.setattr(candidate_facade, "network_interface_discovery_available", lambda: True)
    monkeypatch.setattr(candidate_facade, "network_neighbor_discovery_available", lambda: True)
    monkeypatch.setattr(candidate_facade, "network_interfaces", lambda: (_interface(),))
    monkeypatch.setattr(candidate_facade, "network_neighbors", lambda: (_neighbor(),))

    service = HardwarePentestService(
        assessment_root=tmp_path / "assessments",
        engagement_root=tmp_path / "engagements",
        evidence_root=tmp_path / "evidence",
        verification_root=tmp_path / "verification",
        preflight_root=tmp_path / "preflight",
        gate_root=tmp_path / "gates",
        implementation_root=tmp_path / "implementations",
        generated_project_root=tmp_path / "generated",
    )

    result = service.hardware_discover()

    assert result["network_discovery_available"] is True
    assert result["network_interface_discovery_available"] is True
    assert result["network_neighbor_discovery_available"] is True
    assert result["network_interfaces"][0]["name"] == "Ethernet"
    assert result["network_neighbors"][0]["ip_address"] == "192.168.1.87"
    assert result["network_side_effects"] == "host-state-only; no discovery packets sent"


def test_interface_backend_unavailable_without_optional_dependency(monkeypatch) -> None:
    monkeypatch.setattr(network_module, "psutil", None)

    assert network_module.network_interface_discovery_available() is False
