from __future__ import annotations

from types import SimpleNamespace

from hardware_pentest.adapters.flipper.usb import discover_flipper_ports


def _port(**overrides):
    values = {
        "device": "/dev/ttyUSB0",
        "description": "USB serial",
        "manufacturer": None,
        "product": None,
        "serial_number": None,
        "vid": None,
        "pid": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_discovery_accepts_named_flipper_port() -> None:
    candidates = discover_flipper_ports(
        lambda: [
            _port(
                device="/dev/serial/by-id/usb-Flipper_Devices_Inc._Flipper_TEST-if00",
                description="Flipper Zero",
                manufacturer="Flipper Devices Inc.",
                product="Flipper Zero",
                serial_number="TEST",
                vid=0x0483,
                pid=0x5740,
            )
        ]
    )

    assert len(candidates) == 1
    assert candidates[0].serial_number == "TEST"
    assert candidates[0].vid == 0x0483
    assert candidates[0].pid == 0x5740


def test_discovery_rejects_unrelated_stm_cdc_device() -> None:
    candidates = discover_flipper_ports(
        lambda: [
            _port(
                description="STM Virtual COM Port",
                manufacturer="STMicroelectronics",
                vid=0x0483,
                pid=0x5740,
            )
        ]
    )

    assert candidates == []


def test_discovery_uses_official_vid_pid_with_flipper_manufacturer() -> None:
    candidates = discover_flipper_ports(
        lambda: [
            _port(
                device="COM7",
                manufacturer="Flipper Devices Inc.",
                vid=0x0483,
                pid=0x5740,
            )
        ]
    )

    assert [candidate.device for candidate in candidates] == ["COM7"]


def test_discovery_accepts_windows_inbox_driver_via_flip_serial() -> None:
    # Real Windows enumeration of a genuine Flipper: usbser.sys reports manufacturer "Microsoft",
    # but the firmware exposes the "FLIP_"-prefixed CDC serial number alongside the exact VID/PID.
    candidates = discover_flipper_ports(
        lambda: [
            _port(
                device="COM3",
                description="USB Serial Device (COM3)",
                manufacturer="Microsoft",
                serial_number="FLIP_OY",
                vid=0x0483,
                pid=0x5740,
            )
        ]
    )

    assert [candidate.device for candidate in candidates] == ["COM3"]
    assert candidates[0].serial_number == "FLIP_OY"


def test_discovery_rejects_official_cdc_without_flipper_serial() -> None:
    # Same VID/PID and inbox-driver manufacturer, but no Flipper signal in the serial number.
    candidates = discover_flipper_ports(
        lambda: [
            _port(
                device="COM4",
                description="USB Serial Device (COM4)",
                manufacturer="Microsoft",
                serial_number="0123456789AB",
                vid=0x0483,
                pid=0x5740,
            )
        ]
    )

    assert candidates == []


def test_discovery_rejects_flip_serial_on_unrelated_vid_pid() -> None:
    # A "FLIP_" serial number is not sufficient on its own; the exact VID/PID must also match.
    candidates = discover_flipper_ports(
        lambda: [
            _port(
                device="COM5",
                manufacturer="Microsoft",
                serial_number="FLIP_OY",
                vid=0x1234,
                pid=0x5678,
            )
        ]
    )

    assert candidates == []
