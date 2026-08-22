from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import hardware_pentest.interfaces.wifi_setup_cli as setup_cli
from hardware_pentest.adapters.flipper.usb import FlipperPortCandidate
from hardware_pentest.core.models import InstrumentIdentity
from hardware_pentest.preflight import PreflightReport
from hardware_pentest.preflight.ports import SerialPortMetadata

PASSIVE_VERIFIED = {
    "wireless.wifi.environment.scan",
    "wireless.wifi.beacons.observe",
}
NETWORK_VERIFIED = {
    "wireless.wifi.network.join",
    "wireless.wifi.network.ping_discover",
    "wireless.wifi.network.arp_discover",
    "wireless.wifi.network.ports.scan",
}
IMPLEMENTED = {
    *PASSIVE_VERIFIED,
    "wireless.wifi.raw_frames.observe",
    "wireless.wifi.probes.observe",
    "wireless.wifi.deauth_frames.observe",
    "wireless.wifi.pmkid.observe",
    "wireless.wifi.sae.observe",
    "wireless.wifi.packet_activity.observe",
    *NETWORK_VERIFIED,
}
_FAKE_VERIFIED = set(PASSIVE_VERIFIED)


class FakeRecord:
    def __init__(self, capability_id: str = "preflight") -> None:
        self.capability_id = capability_id
        self.passed = True

    def to_dict(self):
        return {"capability_id": self.capability_id, "passed": self.passed}


class FakeVerifier:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def verify_environment_scan(self, **kwargs):
        _FAKE_VERIFIED.add("wireless.wifi.environment.scan")
        return FakeRecord("wireless.wifi.environment.scan")

    def verify_beacon_observation(self, **kwargs):
        _FAKE_VERIFIED.add("wireless.wifi.beacons.observe")
        return FakeRecord("wireless.wifi.beacons.observe")

    def verify_network_profile(self, **kwargs):
        capabilities = {
            "wireless.wifi.network.join",
            "wireless.wifi.network.ping_discover",
            "wireless.wifi.network.arp_discover",
        }
        if kwargs.get("expected_service"):
            capabilities.add("wireless.wifi.network.ports.scan")
        _FAKE_VERIFIED.update(capabilities)
        return tuple(FakeRecord(item) for item in sorted(capabilities))


class FakeMarauderAdapter:
    def __init__(self, *args, **kwargs) -> None:
        self.implemented_capabilities = frozenset(IMPLEMENTED)

    def probe(self):
        return _marauder_identity()

    def capabilities(self):
        return [SimpleNamespace(capability_id=item) for item in sorted(_FAKE_VERIFIED)]


class FakePreflightRunner:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def run(self, **kwargs):
        return PreflightReport(
            checks=(),
            flipper_identity=InstrumentIdentity(
                instrument_id="flipper:F123",
                kind="flipper-zero",
                model="Flipper Zero",
                transport="usb-cli",
                firmware_version="1.4.3",
                adapter_version="0.7.0-dev",
            ),
            marauder_identity=_marauder_identity(),
            composite_identity=InstrumentIdentity(
                instrument_id="flipper-marauder:abc",
                kind="flipper-marauder-composite",
                model="Flipper Zero + ESP32 Marauder",
                transport="usb+usb-serial",
                firmware_version="state-abc",
                adapter_version="composite-0.1",
            ),
            composite_components={},
            verified_capabilities={"flipper": (), "marauder": ()},
        )


class FakePreflightStore:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def record(self, report):
        return FakeRecord("preflight")


def _marauder_identity() -> InstrumentIdentity:
    return InstrumentIdentity(
        instrument_id="marauder:BOARD123",
        kind="esp32-marauder",
        model="ESP32 Marauder",
        transport="usb-serial",
        firmware_version="v1.12.1",
        adapter_version="0.3.0-dev",
    )


def _patch_hardware(monkeypatch) -> None:
    _FAKE_VERIFIED.clear()
    _FAKE_VERIFIED.update(PASSIVE_VERIFIED)
    monkeypatch.setattr(
        setup_cli,
        "resolve_flipper_serial_port",
        lambda **kwargs: FlipperPortCandidate(
            device="/dev/flipper",
            description="Flipper",
            manufacturer="Flipper Devices",
            product="Flipper Zero",
            serial_number="F123",
            vid=0x0483,
            pid=0x5740,
        ),
    )
    monkeypatch.setattr(
        setup_cli,
        "resolve_companion_serial_port",
        lambda **kwargs: SerialPortMetadata(
            device="/dev/marauder",
            description="ESP32-S2",
            manufacturer="Espressif",
            product="USB Serial",
            serial_number="BOARD123",
            vid=0x303A,
            pid=0x0002,
        ),
    )
    monkeypatch.setattr(setup_cli, "FlipperMarauderPreflight", FakePreflightRunner)
    monkeypatch.setattr(setup_cli, "LocalPreflightStore", FakePreflightStore)
    monkeypatch.setattr(setup_cli, "MarauderCapabilityVerifier", FakeVerifier)
    monkeypatch.setattr(setup_cli, "MarauderAdapter", FakeMarauderAdapter)
    monkeypatch.setattr(setup_cli, "LocalVerificationStore", lambda root: object())


def test_setup_requires_explicit_authorized_lab_ap_confirmation() -> None:
    with pytest.raises(SystemExit, match="confirm-known-lab-ap"):
        setup_cli.main(["--expected-lab-ssid", "NULLSQUARE-HIL-AP"])


def test_successful_passive_setup_reports_ready_and_network_remains_unverified(
    monkeypatch,
    capsys,
) -> None:
    _patch_hardware(monkeypatch)

    setup_cli.main(
        [
            "--expected-lab-ssid",
            "NULLSQUARE-HIL-AP",
            "--expected-lab-channel",
            "6",
            "--confirm-known-lab-ap",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["wifi_assessment_ready"] is True
    assert payload["network_verification_requested"] is False
    assert payload["network_assessment_ready"] is False
    assert payload["requested_setup_ready"] is True
    assert set(payload["wifi_capabilities"]["implemented"]) == IMPLEMENTED
    assert set(payload["wifi_capabilities"]["hardware_verified"]) == PASSIVE_VERIFIED
    assert len(payload["verification_records"]) == 2


def test_network_setup_requires_explicit_transmit_confirmation() -> None:
    with pytest.raises(SystemExit, match="confirm-network-transmit"):
        setup_cli.main(
            [
                "--expected-lab-ssid",
                "NULLSQUARE-HIL-AP",
                "--confirm-known-lab-ap",
                "--verify-network",
                "--wifi-password-env",
                "HPA_LAB_WIFI_PASSWORD",
                "--expected-lab-host",
                "192.168.50.10",
            ]
        )


def test_network_fields_are_rejected_without_verify_network() -> None:
    with pytest.raises(SystemExit, match="require explicit --verify-network"):
        setup_cli.main(
            [
                "--expected-lab-ssid",
                "NULLSQUARE-HIL-AP",
                "--confirm-known-lab-ap",
                "--wifi-password-env",
                "HPA_LAB_WIFI_PASSWORD",
            ]
        )


def test_network_setup_requires_credential_reference_and_controlled_host() -> None:
    with pytest.raises(SystemExit, match="wifi-password-env"):
        setup_cli.main(
            [
                "--expected-lab-ssid",
                "NULLSQUARE-HIL-AP",
                "--confirm-known-lab-ap",
                "--verify-network",
                "--confirm-network-transmit",
                "--expected-lab-host",
                "192.168.50.10",
            ]
        )

    with pytest.raises(SystemExit, match="expected-lab-host"):
        setup_cli.main(
            [
                "--expected-lab-ssid",
                "NULLSQUARE-HIL-AP",
                "--confirm-known-lab-ap",
                "--verify-network",
                "--confirm-network-transmit",
                "--wifi-password-env",
                "HPA_LAB_WIFI_PASSWORD",
            ]
        )


def test_successful_network_hil_marks_only_requested_network_capabilities_verified(
    monkeypatch,
    capsys,
) -> None:
    _patch_hardware(monkeypatch)

    setup_cli.main(
        [
            "--expected-lab-ssid",
            "NULLSQUARE-HIL-AP",
            "--confirm-known-lab-ap",
            "--verify-network",
            "--confirm-network-transmit",
            "--wifi-password-env",
            "HPA_LAB_WIFI_PASSWORD",
            "--expected-lab-host",
            "192.168.50.10",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    expected = PASSIVE_VERIFIED | {
        "wireless.wifi.network.join",
        "wireless.wifi.network.ping_discover",
        "wireless.wifi.network.arp_discover",
    }
    assert payload["network_verification_requested"] is True
    assert payload["network_assessment_ready"] is True
    assert payload["requested_setup_ready"] is True
    assert set(payload["wifi_capabilities"]["hardware_verified"]) == expected
    assert "wireless.wifi.network.ports.scan" in payload["wifi_capabilities"][
        "blocked_pending_verification"
    ]
    assert payload["network_profile"] == {
        "password_env": "HPA_LAB_WIFI_PASSWORD",
        "expected_host_ip": "192.168.50.10",
        "expected_service": None,
        "credential_value_persisted": False,
    }


def test_network_service_hil_also_verifies_port_scan(monkeypatch, capsys) -> None:
    _patch_hardware(monkeypatch)

    setup_cli.main(
        [
            "--expected-lab-ssid",
            "NULLSQUARE-HIL-AP",
            "--confirm-known-lab-ap",
            "--verify-network",
            "--confirm-network-transmit",
            "--wifi-password-env",
            "HPA_LAB_WIFI_PASSWORD",
            "--expected-lab-host",
            "192.168.50.10",
            "--expected-lab-service",
            "https",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["network_assessment_ready"] is True
    assert "wireless.wifi.network.ports.scan" in payload["wifi_capabilities"][
        "hardware_verified"
    ]


def test_fap_provisioning_requires_hash_and_explicit_apply() -> None:
    with pytest.raises(SystemExit, match="supplied together"):
        setup_cli.main(
            [
                "--expected-lab-ssid",
                "NULLSQUARE-HIL-AP",
                "--confirm-known-lab-ap",
                "--marauder-fap",
                "marauder.fap",
            ]
        )

    with pytest.raises(SystemExit, match="apply-fap"):
        setup_cli.main(
            [
                "--expected-lab-ssid",
                "NULLSQUARE-HIL-AP",
                "--confirm-known-lab-ap",
                "--marauder-fap",
                "marauder.fap",
                "--marauder-fap-sha256",
                "0" * 64,
            ]
        )
