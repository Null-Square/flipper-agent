from __future__ import annotations

from dataclasses import dataclass

import hardware_pentest.adapters.marauder.adapter as adapter_module
from hardware_pentest.adapters.marauder import (
    MARAUDER_WIFI_ARP_DISCOVER,
    MARAUDER_WIFI_NETWORK_JOIN,
    MARAUDER_WIFI_PING_DISCOVER,
    MARAUDER_WIFI_PORTS_SCAN,
    MarauderAdapter,
)
from hardware_pentest.adapters.marauder.transport import (
    MarauderDeviceInfo,
    MarauderIPAddress,
    MarauderNetworkCapture,
    MarauderNetworkJoin,
    MarauderObservationCapture,
)
from hardware_pentest.core.models import Action, ActionClass, ExecutionStatus


@dataclass
class FakeNetworkTransport:
    port: str
    serial_factory: object | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def probe(self) -> MarauderDeviceInfo:
        return MarauderDeviceInfo(
            firmware_version="v1.12.1",
            banner="ESP32 Marauder v1.12.1",
            help_text="sniffbeacon stopscan list -a",
        )

    def join_access_point(self, ap_index: int, password: str) -> MarauderNetworkJoin:
        assert password == "LabSecret42!"
        return MarauderNetworkJoin(
            ap_index=ap_index,
            ssid="NULLSQUARE-LAB",
            ip_address="192.168.50.20",
            gateway="192.168.50.1",
            netmask="255.255.255.0",
            output="Password: <redacted-secret>",
        )

    def ping_scan(self, duration_seconds: float) -> MarauderNetworkCapture:
        return _network_capture("ping-discovery")

    def arp_scan(self, duration_seconds: float) -> MarauderNetworkCapture:
        return _network_capture("arp-discovery")

    def port_scan(
        self,
        duration_seconds: float,
        *,
        ip_index: int | None = None,
        service: str | None = None,
    ) -> MarauderNetworkCapture:
        assert ip_index == 1 or service == "https"
        return _network_capture("port-scan")


def _network_capture(operation: str) -> MarauderNetworkCapture:
    return MarauderNetworkCapture(
        operation=operation,
        discovered_ips=(MarauderIPAddress(index=1, address="192.168.50.10"),),
        observation=MarauderObservationCapture(
            operation=operation,
            start_output=f"Starting {operation}",
            stream_output="network observation",
            stop_output="Stopping WiFi tran/recv",
            list_outputs={"list -i": "[1] 192.168.50.10"},
        ),
    )


def _adapter(monkeypatch, capabilities: set[str]) -> MarauderAdapter:
    monkeypatch.setattr(adapter_module, "MarauderSerialTransport", FakeNetworkTransport)
    return MarauderAdapter(
        "/dev/fake",
        serial_number="BOARD123",
        verified_capabilities=capabilities,
        allow_verification_override=True,
    )


def _action(capability: str, inputs: dict[str, object]) -> Action:
    return Action(
        action_id="network-action",
        capability_id=capability,
        target_id="authorized-lab",
        action_class=ActionClass.TRANSMIT,
        inputs=inputs,
        requires_approval=True,
    )


def test_network_capabilities_are_transmit_class_and_not_receive_only(monkeypatch) -> None:
    capabilities = {
        MARAUDER_WIFI_NETWORK_JOIN,
        MARAUDER_WIFI_PING_DISCOVER,
        MARAUDER_WIFI_ARP_DISCOVER,
        MARAUDER_WIFI_PORTS_SCAN,
    }
    adapter = _adapter(monkeypatch, capabilities)

    descriptors = {item.capability_id: item for item in adapter.capabilities()}

    assert set(descriptors) == capabilities
    assert all(item.action_class is ActionClass.TRANSMIT for item in descriptors.values())
    assert all(item.constraints["receive_only"] is False for item in descriptors.values())
    assert descriptors[MARAUDER_WIFI_NETWORK_JOIN].constraints["credential_persisted"] is False


def test_join_resolves_password_from_environment_without_returning_secret(
    monkeypatch,
) -> None:
    monkeypatch.setenv("HPA_WIFI_PASSWORD", "LabSecret42!")
    adapter = _adapter(monkeypatch, {MARAUDER_WIFI_NETWORK_JOIN})

    result = adapter.execute(
        _action(
            MARAUDER_WIFI_NETWORK_JOIN,
            {"ap_index": 0, "password_env": "HPA_WIFI_PASSWORD"},
        )
    )

    assert result.status is ExecutionStatus.SUCCESS
    assert result.normalized["credential_reference"] == "HPA_WIFI_PASSWORD"
    assert result.normalized["ssid"] == "NULLSQUARE-LAB"
    assert "LabSecret42!" not in str(result.raw)
    assert "LabSecret42!" not in str(result.normalized)


def test_join_rejects_literal_password_input(monkeypatch) -> None:
    monkeypatch.setenv("HPA_WIFI_PASSWORD", "LabSecret42!")
    adapter = _adapter(monkeypatch, {MARAUDER_WIFI_NETWORK_JOIN})

    result = adapter.execute(
        _action(
            MARAUDER_WIFI_NETWORK_JOIN,
            {"ap_index": 0, "password": "LabSecret42!"},
        )
    )

    assert result.status is ExecutionStatus.BLOCKED
    assert "Unsupported inputs" in (result.error or "")


def test_join_requires_credential_reference_to_exist(monkeypatch) -> None:
    adapter = _adapter(monkeypatch, {MARAUDER_WIFI_NETWORK_JOIN})

    result = adapter.execute(
        _action(
            MARAUDER_WIFI_NETWORK_JOIN,
            {"ap_index": 0, "password_env": "MISSING_WIFI_SECRET"},
        )
    )

    assert result.status is ExecutionStatus.BLOCKED
    assert "not set" in (result.error or "")


def test_ping_arp_and_port_results_keep_discovered_ip_indices(monkeypatch) -> None:
    capabilities = {
        MARAUDER_WIFI_PING_DISCOVER,
        MARAUDER_WIFI_ARP_DISCOVER,
        MARAUDER_WIFI_PORTS_SCAN,
    }
    adapter = _adapter(monkeypatch, capabilities)

    ping = adapter.execute(
        _action(MARAUDER_WIFI_PING_DISCOVER, {"duration_seconds": 0.05})
    )
    arp = adapter.execute(
        _action(MARAUDER_WIFI_ARP_DISCOVER, {"duration_seconds": 0.05})
    )
    ports = adapter.execute(
        _action(
            MARAUDER_WIFI_PORTS_SCAN,
            {"duration_seconds": 0.05, "ip_index": 1},
        )
    )

    for result in (ping, arp, ports):
        assert result.status is ExecutionStatus.SUCCESS
        assert result.normalized["discovered_ips"] == [
            {"index": 1, "address": "192.168.50.10"}
        ]


def test_network_capability_rejects_observe_action_class(monkeypatch) -> None:
    adapter = _adapter(monkeypatch, {MARAUDER_WIFI_PING_DISCOVER})
    action = Action(
        action_id="wrong-class",
        capability_id=MARAUDER_WIFI_PING_DISCOVER,
        target_id="authorized-lab",
        action_class=ActionClass.OBSERVE,
        inputs={"duration_seconds": 0.05},
    )

    result = adapter.execute(action)

    assert result.status is ExecutionStatus.BLOCKED
    assert "TRANSMIT" in (result.error or "")
