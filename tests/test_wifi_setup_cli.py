from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import hardware_pentest.interfaces.wifi_setup_cli as setup_cli
from hardware_pentest.adapters.flipper.usb import FlipperPortCandidate
from hardware_pentest.core.models import InstrumentIdentity
from hardware_pentest.preflight import PreflightReport
from hardware_pentest.preflight.ports import SerialPortMetadata


IMPLEMENTED = {
    "wireless.wifi.environment.scan",
    "wireless.wifi.beacons.observe",
    "wireless.wifi.raw_frames.observe",
    "wireless.wifi.probes.observe",
    "wireless.wifi.deauth_frames.observe",
    "wireless.wifi.pmkid.observe",
    "wireless.wifi.sae.observe",
    "wireless.wifi.packet_activity.observe",
}
VERIFIED = {
    "wireless.wifi.environment.scan",
    "wireless.wifi.beacons.observe",
}


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
        return FakeRecord("wireless.wifi.environment.scan")

    def verify_beacon_observation(self, **kwargs):
        return FakeRecord("wireless.wifi.beacons.observe")


class FakeMarauderAdapter:
    def __init__(self, *args, **kwargs) -> None:
        self.implemented_capabilities = frozenset(IMPLEMENTED)

    def probe(self):
        return _marauder_identity()

    def capabilities(self):
        return [SimpleNamespace(capability_id=item) for item in sorted(VERIFIED)]


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
        adapter_version="0.2.0-dev",
    )


def _patch_hardware(monkeypatch) -> None:
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


def test_successful_setup_reports_ready_and_remaining_verification_work(
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
    assert set(payload["wifi_capabilities"]["implemented"]) == IMPLEMENTED
    assert set(payload["wifi_capabilities"]["hardware_verified"]) == VERIFIED
    assert set(payload["wifi_capabilities"]["blocked_pending_verification"]) == IMPLEMENTED - VERIFIED
    assert len(payload["verification_records"]) == 2


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
