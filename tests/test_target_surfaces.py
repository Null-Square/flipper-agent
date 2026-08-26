from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import hardware_pentest.service.candidate_facade as candidate_facade
from hardware_pentest.core.artifact_scope import LocalArtifactScopeStore
from hardware_pentest.core.engagement_store import LocalEngagementStore
from hardware_pentest.core.models import ActionClass, Engagement, Target
from hardware_pentest.core.target_surfaces import (
    LocalTargetSurfaceStore,
    SurfaceKind,
    SurfaceSource,
    SurfaceStrength,
    TargetSurfaceStoreError,
)
from hardware_pentest.preflight.network import NetworkNeighborCandidate
from hardware_pentest.service import HardwarePentestService


def _engagement(*target_ids: str, allowed: tuple[str, ...] = ()) -> Engagement:
    now = datetime.now(UTC)
    return Engagement(
        engagement_id="eng-surfaces",
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(hours=1),
        target_ids=frozenset(target_ids),
        allowed_capabilities=allowed,
        denied_capabilities=(),
        max_action_class=ActionClass.OBSERVE,
    )


def _save_engagement(root: Path, *target_ids: str, allowed: tuple[str, ...] = ()) -> None:
    engagement = _engagement(*target_ids, allowed=allowed)
    targets = tuple(
        Target(target_id=target_id, description=f"Authorized target {target_id}")
        for target_id in target_ids
    )
    LocalEngagementStore(root).save(engagement, targets)


def _service(tmp_path: Path) -> HardwarePentestService:
    return HardwarePentestService(
        assessment_root=tmp_path / "assessments",
        engagement_root=tmp_path / "engagements",
        evidence_root=tmp_path / "evidence",
        verification_root=tmp_path / "verification",
        preflight_root=tmp_path / "preflight",
        gate_root=tmp_path / "gates",
        implementation_root=tmp_path / "implementations",
        artifact_scope_root=tmp_path / "artifact-scopes",
        surface_root=tmp_path / "target-surfaces",
        generated_project_root=tmp_path / "generated",
    )


def test_surface_upsert_deduplicates_and_evidence_corroborates(tmp_path: Path) -> None:
    store = LocalTargetSurfaceStore(tmp_path / "surfaces")
    first = store.upsert(
        engagement_id="eng-surfaces",
        target_id="target-a",
        kind=SurfaceKind.USB,
        reference="usb:1:2:1:1234:5678",
        source=SurfaceSource.ASSESSMENT_INPUT,
        attributes={"vid": 0x1234},
        limitations=("descriptor is a claim",),
    )
    second = store.upsert(
        engagement_id="eng-surfaces",
        target_id="target-a",
        kind=SurfaceKind.USB,
        reference="usb:1:2:1:1234:5678",
        source=SurfaceSource.HOST_OBSERVED,
        attributes={"pid": 0x5678},
    )

    assert first.surface_id == second.surface_id
    assert len(store.for_target("eng-surfaces", "target-a")) == 1
    assert second.strength is SurfaceStrength.CANDIDATE
    assert set(second.sources) == {
        SurfaceSource.ASSESSMENT_INPUT,
        SurfaceSource.HOST_OBSERVED,
    }
    assert second.attributes == {"vid": 0x1234, "pid": 0x5678}

    corroborated = store.upsert(
        engagement_id="eng-surfaces",
        target_id="target-a",
        kind=SurfaceKind.USB,
        reference="usb:1:2:1:1234:5678",
        source=SurfaceSource.EVIDENCE_LINKED,
        evidence_ids=("ev-123",),
    )

    assert corroborated.strength is SurfaceStrength.CORROBORATED
    assert corroborated.evidence_ids == ("ev-123",)
    assert SurfaceSource.EVIDENCE_LINKED in corroborated.sources


def test_surface_inventory_fails_closed_after_tampering(tmp_path: Path) -> None:
    store = LocalTargetSurfaceStore(tmp_path / "surfaces")
    store.upsert(
        engagement_id="eng-surfaces",
        target_id="target-a",
        kind=SurfaceKind.SERIAL,
        reference="COM7",
        source=SurfaceSource.ASSESSMENT_INPUT,
    )
    path = store.root / "eng-surfaces.json"
    original = path.read_text(encoding="utf-8")
    path.write_text(original.replace("COM7", "COM8"), encoding="utf-8")

    with pytest.raises(TargetSurfaceStoreError, match="Invalid target surface inventory"):
        store.for_target("eng-surfaces", "target-a")


def test_same_observed_network_reference_can_remain_candidate_for_two_targets(
    tmp_path: Path,
) -> None:
    store = LocalTargetSurfaceStore(tmp_path / "surfaces")
    reference = "network:192.168.1.87:aa:bb:cc:dd:ee:ff:eth0"
    first = store.upsert(
        engagement_id="eng-surfaces",
        target_id="target-a",
        kind=SurfaceKind.NETWORK,
        reference=reference,
        source=SurfaceSource.HOST_OBSERVED,
    )
    second = store.upsert(
        engagement_id="eng-surfaces",
        target_id="target-b",
        kind=SurfaceKind.NETWORK,
        reference=reference,
        source=SurfaceSource.HOST_OBSERVED,
    )

    assert first.surface_id != second.surface_id
    assert first.strength is SurfaceStrength.CANDIDATE
    assert second.strength is SurfaceStrength.CANDIDATE
    assert len(store.for_engagement("eng-surfaces")) == 2


def test_assessment_inputs_create_candidate_surfaces_and_context(tmp_path: Path) -> None:
    _save_engagement(tmp_path / "engagements", "target-a")
    service = _service(tmp_path)

    result = service.assessment_create(
        engagement_id="eng-surfaces",
        target_id="target-a",
        assessment_id="assessment-surfaces",
        artifact_path="firmware.bin",
        serial_device="COM7",
        usb_candidate_id="usb:1:2:1:1234:5678",
    )

    surfaces = result["context"]["target_surfaces"]
    assert result["context"]["target_surface_count"] == 3
    assert {(item["kind"], item["reference"]) for item in surfaces} == {
        ("artifact", "firmware.bin"),
        ("serial", "COM7"),
        ("usb", "usb:1:2:1:1234:5678"),
    }
    assert all(item["strength"] == "candidate" for item in surfaces)
    assert all(item["sources"] == ["assessment_input"] for item in surfaces)
    assert all("target_class" not in item for item in surfaces)


def test_successful_artifact_execution_corroborates_exact_surface(tmp_path: Path) -> None:
    allowed = (
        "artifact.binary.identify",
        "artifact.firmware.inspect",
        "artifact.firmware.triage",
        "artifact.strings.extract",
    )
    _save_engagement(tmp_path / "engagements", "target-a", allowed=allowed)
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    (artifact_root / "firmware.bin").write_bytes(b"\x7fELFfirmware-version-1.0")
    LocalArtifactScopeStore(tmp_path / "artifact-scopes").save(
        engagement_id="eng-surfaces",
        artifact_root=artifact_root,
    )
    service = _service(tmp_path)
    service.assessment_create(
        engagement_id="eng-surfaces",
        target_id="target-a",
        assessment_id="assessment-evidence-surface",
        artifact_path="firmware.bin",
    )

    result = service.assessment_execute_next("assessment-evidence-surface")

    assert isinstance(result.get("evidence_id"), str)
    inventory = service.target_surface_inventory("eng-surfaces", "target-a")
    artifact = next(item for item in inventory["surfaces"] if item["kind"] == "artifact")
    assert artifact["strength"] == "corroborated"
    assert result["evidence_id"] in artifact["evidence_ids"]
    assert "evidence_linked" in artifact["sources"]


def test_network_association_requires_exact_current_passive_candidate(
    tmp_path: Path, monkeypatch
) -> None:
    _save_engagement(tmp_path / "engagements", "target-a")
    candidate = NetworkNeighborCandidate(
        candidate_id="network:192.168.1.87:aa:bb:cc:dd:ee:ff:eth0",
        ip_address="192.168.1.87",
        mac_address="aa:bb:cc:dd:ee:ff",
        interface="eth0",
        state="complete",
        source="linux-proc-arp-cache",
    )
    monkeypatch.setattr(candidate_facade, "network_neighbor_discovery_available", lambda: True)
    monkeypatch.setattr(candidate_facade, "network_neighbors", lambda: (candidate,))
    service = _service(tmp_path)

    associated = service.target_surface_associate_network(
        "eng-surfaces",
        "target-a",
        candidate.candidate_id,
    )

    assert associated["side_effects"] == "host-state-only; no discovery packets sent"
    assert associated["surface"]["kind"] == "network"
    assert associated["surface"]["strength"] == "candidate"
    assert associated["surface"]["sources"] == ["host_observed"]
    assert associated["surface"]["attributes"]["ip_address"] == "192.168.1.87"

    monkeypatch.setattr(candidate_facade, "network_neighbors", lambda: ())
    with pytest.raises(ValueError, match="not present in current passive discovery"):
        service.target_surface_associate_network(
            "eng-surfaces",
            "target-a",
            candidate.candidate_id,
        )
