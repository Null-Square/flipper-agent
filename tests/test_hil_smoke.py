from __future__ import annotations

import os

import pytest

from hardware_pentest.adapters.flipper.adapter import FlipperAdapter
from hardware_pentest.adapters.marauder.adapter import MarauderAdapter

pytestmark = pytest.mark.hil


def _hil_enabled() -> bool:
    return os.environ.get("HPA_HIL") == "1"


def test_attached_flipper_reports_stable_identity() -> None:
    if not _hil_enabled():
        pytest.skip("Set HPA_HIL=1 to allow physical hardware tests")
    port = os.environ.get("HPA_FLIPPER_PORT")
    if not port:
        pytest.fail("HPA_FLIPPER_PORT is required for the HIL profile")

    identity = FlipperAdapter(port).probe()

    assert identity.kind == "flipper-zero"
    assert identity.model == "Flipper Zero"
    assert identity.firmware_version
    assert identity.instrument_id.startswith("flipper:")


def test_attached_marauder_reports_expected_cli_identity_when_configured() -> None:
    if not _hil_enabled():
        pytest.skip("Set HPA_HIL=1 to allow physical hardware tests")
    port = os.environ.get("HPA_MARAUDER_PORT")
    if not port:
        pytest.skip("HPA_MARAUDER_PORT is not configured for this HIL run")

    identity = MarauderAdapter(port).probe()

    assert identity.kind == "esp32-marauder"
    assert identity.model == "ESP32 Marauder"
    assert identity.firmware_version
    assert identity.instrument_id.startswith("marauder:")
