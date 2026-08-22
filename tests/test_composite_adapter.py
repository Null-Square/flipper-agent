from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import hardware_pentest.adapters.composite.flipper_marauder as composite_module
import pytest
from hardware_pentest.adapters.composite import FlipperMarauderAdapter
from hardware_pentest.adapters.flipper.apps import MARAUDER_APP
from hardware_pentest.adapters.flipper.apps.models import FlipperAppInstallation
from hardware_pentest.core.models import (
    Action,
    ActionClass,
    CapabilityDescriptor,
    CapabilityMaturity,
    ExecutionResult,
    ExecutionStatus,
    InstrumentIdentity,
    ValidationResult,
)
from hardware_pentest.preflight import PreflightReport
from hardware_pentest.preflight.store import LocalPreflightStore


FLIPPER_IR = "infrared.observe"
MARAUDER_WIFI = "wireless.wifi.beacons.observe"


class AllVerified:
    def verified_capabilities(self, identity, implemented_capabilities):
        return frozenset(implemented_capabilities)


class FakeFlipperAdapter:
    implemented_capabilities = frozenset({FLIPPER_IR})

    def __init__(self, *args, **kwargs) -> None:
        self.identity = InstrumentIdentity(
            instrument_id="flipper:FLIPPER123",
            kind="flipper-zero",
            model="Flipper Zero",
            transport="usb-cli",
            firmware_version="1.4.3",
            adapter_version="0.7.0-dev",
        )

    def probe(self) -> InstrumentIdentity:
        return self.identity

    def capabilities(self) -> list[CapabilityDescriptor]:
        return [
            CapabilityDescriptor(
                capability_id=FLIPPER_IR,
                description="fake IR",
                action_class=ActionClass.OBSERVE,
                maturity=CapabilityMaturity.HARDWARE_VERIFIED,
                instrument_id=self.identity.instrument_id,
            )
        ]

    def validate(self, action: Action) -> ValidationResult:
        return ValidationResult(action.capability_id == FLIPPER_IR)

    def execute(self, action: Action) -> ExecutionResult:
        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            instrument_id=self.identity.instrument_id,
            capability_id=action.capability_id,
            raw={"source": "flipper"},
            normalized={"observed": True},
        )


class FakeMarauderAdapter:
    implemented_capabilities = frozenset({MARAUDER_WIFI})
    default_firmware: str | None = "v1.12.1"

    def __init__(self, *args, firmware_version_hint=None, **kwargs) -> None:
        self.firmware_version_hint = firmware_version_hint
        self.identity = InstrumentIdentity(
            instrument_id="marauder:BOARD123",
            kind="esp32-marauder",
            model="ESP32 Marauder",
            transport="usb-serial",
            firmware_version=self.default_firmware or firmware_version_hint,
            adapter_version="0.1.0-dev",
        )

    def probe(self) -> InstrumentIdentity:
        return replace(
            self.identity,
            firmware_version=self.default_firmware or self.firmware_version_hint,
        )

    def capabilities(self) -> list[CapabilityDescriptor]:
        return [
            CapabilityDescriptor(
                capability_id=MARAUDER_WIFI,
                description="fake passive Wi-Fi",
                action_class=ActionClass.OBSERVE,
                maturity=CapabilityMaturity.HARDWARE_VERIFIED,
                instrument_id=self.probe().instrument_id,
                constraints={"receive_only": True},
            )
        ]

    def validate(self, action: Action) -> ValidationResult:
        return ValidationResult(action.capability_id == MARAUDER_WIFI)

    def execute(self, action: Action) -> ExecutionResult:
        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            instrument_id=self.probe().instrument_id,
            capability_id=action.capability_id,
            raw={"source": "marauder"},
            normalized={
                "observation_mode": "passive-beacon",
                "access_point_count": 1,
                "access_points": [{"ssid": "NULLSQUARE-HIL-AP", "channel": 6}],
            },
        )


class FakeAppManager:
    md5 = "0123456789abcdef0123456789abcdef"

    def __init__(self, *args, **kwargs) -> None:
        pass

    def installation(self, app_id: str) -> FlipperAppInstallation:
        assert app_id == MARAUDER_APP.app_id
        return FlipperAppInstallation(
            spec=MARAUDER_APP,
            installed=True,
            file_md5=self.md5,
        )


def patch_components(monkeypatch) -> None:
    monkeypatch.setattr(composite_module, "FlipperAdapter", FakeFlipperAdapter)
    monkeypatch.setattr(composite_module, "MarauderAdapter", FakeMarauderAdapter)
    monkeypatch.setattr(composite_module, "FlipperAppManager", FakeAppManager)


def make_adapter(tmp_path, monkeypatch) -> FlipperMarauderAdapter:
    patch_components(monkeypatch)
    return FlipperMarauderAdapter(
        flipper_port="/dev/flipper",
        flipper_serial_number="USB-FLIPPER",
        marauder_port="/dev/marauder",
        marauder_serial_number="BOARD123",
        verification_resolver=AllVerified(),
        preflight_store=LocalPreflightStore(tmp_path / "preflight"),
    )


def record_ready(adapter: FlipperMarauderAdapter) -> None:
    identity = adapter.probe()
    report = PreflightReport(
        checks=(),
        flipper_identity=adapter.flipper.probe(),
        marauder_identity=adapter.marauder.probe(),
        composite_identity=identity,
        composite_components=None,
        verified_capabilities={"flipper": (FLIPPER_IR,), "marauder": (MARAUDER_WIFI,)},
    )
    adapter.preflight_store.record(report, tested_at=datetime.now(UTC))


def test_composite_exposes_no_capabilities_without_matching_preflight(
    tmp_path,
    monkeypatch,
) -> None:
    adapter = make_adapter(tmp_path, monkeypatch)

    assert adapter.capabilities() == []


def test_matching_preflight_exposes_verified_component_capabilities(
    tmp_path,
    monkeypatch,
) -> None:
    adapter = make_adapter(tmp_path, monkeypatch)
    record_ready(adapter)

    capabilities = {item.capability_id: item for item in adapter.capabilities()}

    assert set(capabilities) == {FLIPPER_IR, MARAUDER_WIFI}
    assert all(
        item.instrument_id.startswith("flipper-marauder:")
        for item in capabilities.values()
    )
    assert (
        capabilities[MARAUDER_WIFI].quality["physical_instrument_id"]
        == "marauder:BOARD123"
    )
    assert capabilities[MARAUDER_WIFI].quality["preflight_record_id"]


def test_fap_fingerprint_change_invalidates_preflight(tmp_path, monkeypatch) -> None:
    adapter = make_adapter(tmp_path, monkeypatch)
    record_ready(adapter)
    assert adapter.capabilities()

    FakeAppManager.md5 = "fedcba9876543210fedcba9876543210"
    try:
        assert adapter.capabilities() == []
    finally:
        FakeAppManager.md5 = "0123456789abcdef0123456789abcdef"


def test_wifi_execution_keeps_composite_and_physical_provenance(
    tmp_path,
    monkeypatch,
) -> None:
    adapter = make_adapter(tmp_path, monkeypatch)
    record_ready(adapter)
    action = Action(
        action_id="wifi-observe",
        capability_id=MARAUDER_WIFI,
        target_id="target-a",
        action_class=ActionClass.OBSERVE,
        inputs={"duration_seconds": 1.0},
    )

    result = adapter.execute(action)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.instrument_id.startswith("flipper-marauder:")
    assert result.raw["_physical_instrument"]["instrument_id"] == "marauder:BOARD123"
    assert result.raw["_composite_instrument"]["instrument_id"] == result.instrument_id
    assert result.raw["_preflight_record_id"]


def test_recent_preflight_can_fill_missing_runtime_marauder_boot_banner(
    tmp_path,
    monkeypatch,
) -> None:
    adapter = make_adapter(tmp_path, monkeypatch)
    record_ready(adapter)
    expected = adapter.probe()

    FakeMarauderAdapter.default_firmware = None
    try:
        recovered = adapter.probe()
    finally:
        FakeMarauderAdapter.default_firmware = "v1.12.1"

    assert recovered == expected


def test_new_runtime_marauder_firmware_invalidates_old_preflight(
    tmp_path,
    monkeypatch,
) -> None:
    adapter = make_adapter(tmp_path, monkeypatch)
    record_ready(adapter)

    FakeMarauderAdapter.default_firmware = "v1.13.0"
    try:
        assert adapter.capabilities() == []
    finally:
        FakeMarauderAdapter.default_firmware = "v1.12.1"


def test_composite_requires_stable_marauder_serial_identity(tmp_path, monkeypatch) -> None:
    patch_components(monkeypatch)
    with pytest.raises(ValueError, match="stable Marauder serial identity"):
        FlipperMarauderAdapter(
            flipper_port="/dev/flipper",
            marauder_port="/dev/marauder",
            marauder_serial_number=None,
            verification_resolver=AllVerified(),
            preflight_store=LocalPreflightStore(tmp_path / "preflight"),
        )
