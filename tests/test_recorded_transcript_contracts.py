from __future__ import annotations

import json
from pathlib import Path

import pytest

from hardware_pentest.adapters.flipper.transport import FlipperSerialTransport
from hardware_pentest.adapters.marauder.transport import MarauderSerialTransport
from tests.support.transcript_replay import replay_factory

pytestmark = pytest.mark.contract

_FIXTURES = Path(__file__).parent / "fixtures" / "hardware" / "synthetic"


def test_flipper_transcript_replays_through_production_parser() -> None:
    factory = replay_factory(
        _FIXTURES / "flipper-device-info.json",
        label="flipper-identity",
    )

    with FlipperSerialTransport("/dev/replay", serial_factory=factory) as transport:
        info = transport.read_device_info()

    assert info.model == "Flipper Zero"
    assert info.uid == "<redacted-uid>"
    assert info.firmware_version == "1.4.3"


def test_marauder_transcript_replays_through_production_probe() -> None:
    factory = replay_factory(
        _FIXTURES / "marauder-probe.json",
        label="marauder-probe",
    )

    with MarauderSerialTransport(
        "/dev/replay",
        serial_factory=factory,
        boot_timeout=0.05,
        command_timeout=0.05,
    ) as transport:
        info = transport.probe()

    assert info.firmware_version == "v1.12.1"
    assert "sniffbeacon" in info.help_text


@pytest.mark.parametrize(
    "leaked_text",
    [
        "Password: real-secret",
        "join -a 1 -p real-secret",
        "hardware_uid: ABCDEF012345",
        "AA:BB:CC:DD:EE:FF",
    ],
)
def test_transcript_fixture_loader_rejects_unsanitized_sensitive_data(
    tmp_path: Path,
    leaked_text: str,
) -> None:
    fixture = {
        "schema_version": "1",
        "sessions": [
            {
                "label": "leaky",
                "events": [
                    {"direction": "rx", "data": leaked_text},
                ],
            }
        ],
    }
    path = tmp_path / "leaky.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    with pytest.raises(ValueError, match="unsanitized sensitive data"):
        replay_factory(path, label="leaky")
