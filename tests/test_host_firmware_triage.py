from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from hardware_pentest.adapters.host import HostArtifactAdapter
from hardware_pentest.core.artifact_scope import LocalArtifactScopeStore
from hardware_pentest.core.engagement_store import LocalEngagementStore
from hardware_pentest.core.models import Action, ActionClass, Engagement, ExecutionStatus, Target
from hardware_pentest.evidence.store import LocalEvidenceStore
from hardware_pentest.service.execution import HarnessAssessmentExecutor, InstrumentSelection
from hardware_pentest.service.planning import HarnessAssessmentPlanner

_CAPABILITIES = (
    "artifact.firmware.inspect",
    "artifact.binary.identify",
    "artifact.strings.extract",
    "artifact.firmware.triage",
)


def _firmware_bytes() -> bytes:
    return b"".join(
        (
            b"\x7fELF\x02\x01" + b"\x00" * 12 + b"\x3e\x00",
            b"\x00build version 1.2.3\x00",
            b"http://192.168.10.1/admin?token=super-secret\x00",
            b"/etc/passwd\x00/dev/ttyS0\x00",
            b"password=do-not-copy-this\x00",
            b"-----BEGIN CERTIFICATE-----\x00",
            bytes(range(256)),
        )
    )


def _action(capability_id: str, path: str = "firmware.elf") -> Action:
    return Action(
        action_id=f"{capability_id}:target-1",
        capability_id=capability_id,
        target_id="target-1",
        action_class=ActionClass.OBSERVE,
        inputs={"artifact_path": path},
    )


def _adapter(tmp_path: Path) -> tuple[HostArtifactAdapter, Path]:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    firmware = artifact_root / "firmware.elf"
    firmware.write_bytes(_firmware_bytes())
    scopes = LocalArtifactScopeStore(tmp_path / "scopes")
    scopes.save(engagement_id="eng-triage", artifact_root=artifact_root)
    return HostArtifactAdapter(engagement_id="eng-triage", scopes=scopes), firmware


def test_host_artifact_adapter_advertises_typed_triage_capabilities(tmp_path: Path) -> None:
    adapter, _firmware = _adapter(tmp_path)

    descriptors = {item.capability_id: item for item in adapter.capabilities()}

    assert set(descriptors) == set(_CAPABILITIES)
    for descriptor in descriptors.values():
        assert descriptor.instrument_id == "host.local"
        assert descriptor.action_class is ActionClass.OBSERVE
        assert descriptor.constraints["shell_passthrough"] is False
        assert descriptor.constraints["subprocess_execution"] is False
        assert descriptor.constraints["mutates_artifact"] is False


def test_binary_identify_reports_elf_hints_without_execution(tmp_path: Path) -> None:
    adapter, firmware = _adapter(tmp_path)

    result = adapter.execute(_action("artifact.binary.identify"))

    assert result.status is ExecutionStatus.SUCCESS
    identification = result.normalized["identification"]
    assert identification["magic_type"] == "elf"
    assert identification["extension"] == ".elf"
    assert identification["elf"]["class"] == "64-bit"
    assert identification["elf"]["byte_order"] == "little"
    assert firmware.read_bytes() == _firmware_bytes()


def test_strings_extract_is_bounded_and_contains_expected_strings(tmp_path: Path) -> None:
    adapter, _firmware = _adapter(tmp_path)

    result = adapter.execute(_action("artifact.strings.extract"))

    assert result.status is ExecutionStatus.SUCCESS
    strings = result.normalized["strings"]
    assert any("build version 1.2.3" in value for value in strings)
    assert any("/etc/passwd" in value for value in strings)
    assert result.normalized["string_count"] <= 200
    assert result.normalized["output_bytes"] <= 16 * 1024


def test_firmware_triage_sanitizes_urls_and_reports_indicator_labels(tmp_path: Path) -> None:
    adapter, _firmware = _adapter(tmp_path)

    result = adapter.execute(_action("artifact.firmware.triage"))

    assert result.status is ExecutionStatus.SUCCESS
    normalized = result.normalized
    assert normalized["identification"]["magic_type"] == "elf"
    assert 0.0 < normalized["entropy"]["global_bits_per_byte"] <= 8.0
    indicators = normalized["indicators"]
    assert "http://192.168.10.1/admin" in indicators["urls"]
    assert all("super-secret" not in value for value in indicators["urls"])
    assert "192.168.10.1" in indicators["ipv4_addresses"]
    assert "/etc/passwd" in indicators["paths"]
    assert "password" in indicators["credential_labels"]
    assert "token" in indicators["credential_labels"]
    assert "-----BEGIN CERTIFICATE-----" in indicators["certificate_markers"]
    assert "strings" not in normalized


def test_triage_rejects_parent_traversal_before_analysis(tmp_path: Path) -> None:
    adapter, _firmware = _adapter(tmp_path)

    result = adapter.execute(_action("artifact.firmware.triage", "../outside.bin"))

    assert result.status is ExecutionStatus.FAILED
    assert "parent traversal" in str(result.error)


def test_full_assessment_routes_all_firmware_triage_to_host_and_records_evidence(
    tmp_path: Path,
) -> None:
    roots = {
        "assessment": tmp_path / "assessments",
        "engagement": tmp_path / "engagements",
        "evidence": tmp_path / "evidence",
        "verification": tmp_path / "verification",
        "preflight": tmp_path / "preflight",
        "gate": tmp_path / "gates",
        "implementation": tmp_path / "implementations",
        "artifact_scope": tmp_path / "artifact-scopes",
    }
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    (artifact_root / "firmware.elf").write_bytes(_firmware_bytes())

    now = datetime.now(UTC)
    engagement = Engagement(
        engagement_id="eng-triage-runtime",
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
        target_ids=frozenset({"board-1"}),
        allowed_capabilities=_CAPABILITIES,
        denied_capabilities=(),
        max_action_class=ActionClass.OBSERVE,
    )
    target = Target(target_id="board-1", description="Authorized firmware fixture")
    LocalEngagementStore(roots["engagement"]).save(engagement, (target,))
    LocalArtifactScopeStore(roots["artifact_scope"]).save(
        engagement_id=engagement.engagement_id,
        artifact_root=artifact_root,
    )

    planner = HarnessAssessmentPlanner(
        assessment_root=roots["assessment"],
        engagement_root=roots["engagement"],
        verification_root=roots["verification"],
        preflight_root=roots["preflight"],
        implementation_root=roots["implementation"],
        artifact_scope_root=roots["artifact_scope"],
    )
    state = planner.create(
        engagement_id=engagement.engagement_id,
        target_id=target.target_id,
        instrument=InstrumentSelection(backend="simulator"),
        artifact_path="firmware.elf",
        assessment_id="assessment-triage",
    )

    artifact_steps = [step for step in state.steps if step.test_case_id.startswith("artifact.")]
    assert len(artifact_steps) == 4
    assert {step.instrument_id for step in artifact_steps} == {"host.local"}
    assert all(step.status.value == "ready" for step in artifact_steps)

    executor = HarnessAssessmentExecutor(
        assessment_root=roots["assessment"],
        engagement_root=roots["engagement"],
        evidence_root=roots["evidence"],
        verification_root=roots["verification"],
        preflight_root=roots["preflight"],
        gate_root=roots["gate"],
        implementation_root=roots["implementation"],
        artifact_scope_root=roots["artifact_scope"],
    )
    for _ in range(4):
        result = executor.execute_next(state.assessment_id)
        assert result["execution_status"] == ExecutionStatus.SUCCESS.value

    records = LocalEvidenceStore(roots["evidence"]).records(engagement.engagement_id)
    artifact_records = [record for record in records if record.capability_id in _CAPABILITIES]
    assert len(artifact_records) == 4
    assert {record.capability_id for record in artifact_records} == set(_CAPABILITIES)
    assert {record.instrument_id for record in artifact_records} == {"host.local"}
    assert {record.target_id for record in artifact_records} == {"board-1"}
