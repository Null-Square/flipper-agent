from __future__ import annotations

import json
from pathlib import Path

_FIXTURE_ROOT = Path(__file__).parents[1] / "examples" / "hil" / "dual_uart_pico"


def _manifest() -> dict:
    return json.loads((_FIXTURE_ROOT / "fixture.json").read_text(encoding="utf-8"))


def test_dual_uart_fixture_contract_is_passive_and_deterministic() -> None:
    fixture = _manifest()

    assert fixture["schema_version"] == "1"
    assert fixture["fixture_id"] == "nullsquare-dual-uart-pico-v1"
    assert fixture["marker"] == "NULLSQUARE-HIL-READY"
    assert fixture["interval_ms"] == 100
    assert fixture["usb_cdc"]["marker"] == fixture["marker"]

    uart = fixture["uart"]
    assert uart == {
        "controller": 1,
        "tx_gpio": 4,
        "rx_gpio": 5,
        "baud": 115200,
        "data_bits": 8,
        "parity": "none",
        "stop_bits": 1,
        "minimum_sample_bytes": 32,
        "purpose": "Flipper internal.uart.autodetect HIL",
    }

    electrical = fixture["electrical"]
    assert electrical["logic_level_volts"] == 3.3
    assert electrical["target_tx_only"] is True
    assert electrical["cross_device_power_connection"] is False
    assert any("GND" in item for item in electrical["required_connections"])
    assert all("power" not in item.lower() for item in electrical["required_connections"])


def test_micropython_fixture_matches_machine_readable_contract() -> None:
    fixture = _manifest()
    source = (_FIXTURE_ROOT / "main.py").read_text(encoding="utf-8")
    uart = fixture["uart"]

    assert f'BANNER = "{fixture["marker"]}"' in source
    assert f'BAUDRATE = {uart["baud"]}' in source
    assert f'UART_ID = {uart["controller"]}' in source
    assert f'UART_TX_GPIO = {uart["tx_gpio"]}' in source
    assert f'UART_RX_GPIO = {uart["rx_gpio"]}' in source
    assert "bits=8" in source
    assert "parity=None" in source
    assert "stop=1" in source
    assert "uart.write(payload)" in source
    assert "print(BANNER)" in source
