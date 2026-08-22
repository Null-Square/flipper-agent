from __future__ import annotations

import json

from hardware_pentest.preflight.transcript import TranscriptRecorder


class SecretStream:
    def __init__(self, *, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)
        self.is_open = True
        self.writes: list[bytes] = []

    @property
    def in_waiting(self) -> int:
        return len(self.chunks[0]) if self.chunks else 0

    def read(self, size: int = 1) -> bytes:
        if not self.chunks:
            return b""
        return self.chunks.pop(0)

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self.chunks.clear()


def test_marauder_join_password_is_redacted_from_tx_and_rx_transcript(tmp_path) -> None:
    secret = "LabOnlySecret42!"
    stream = SecretStream(
        chunks=[
            f"#join -a 2 -p {secret}\r\n".encode(),
            f"Using SSID: NULLSQUARE-LAB Password: {secret}\r\n> ".encode(),
        ]
    )
    recorder = TranscriptRecorder()
    factory = recorder.recording_factory("marauder", base_factory=lambda **kwargs: stream)
    recorded = factory(port="/dev/ttyACM1")

    recorded.write(f"join -a 2 -p {secret}\n".encode())
    while recorded.in_waiting:
        recorded.read(4096)

    output = recorder.write(tmp_path / "transcript.json")
    text = output.read_text(encoding="utf-8")

    assert secret not in text
    assert "join -a 2 -p <redacted-secret>" in text
    assert "Password: <redacted-secret>" in text


def test_saved_client_password_is_redacted_from_settings_json(tmp_path) -> None:
    secret = "AnotherLabSecret"
    stream = SecretStream(chunks=[f'{{"ClientSSID":"LAB","ClientPW":"{secret}"}}'.encode()])
    recorder = TranscriptRecorder()
    factory = recorder.recording_factory("marauder", base_factory=lambda **kwargs: stream)
    recorded = factory(port="/dev/ttyACM1")

    while recorded.in_waiting:
        recorded.read(4096)

    output = recorder.write(tmp_path / "transcript.json")
    payload = json.loads(output.read_text(encoding="utf-8"))
    text = json.dumps(payload)

    assert secret not in text
    assert "<redacted-secret>" in text
