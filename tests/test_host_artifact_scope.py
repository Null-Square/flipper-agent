from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from hardware_pentest.adapters.host import HostArtifactAdapter
from hardware_pentest.assessment.artifact_catalog import artifact_test_catalog
from hardware_pentest.core.artifact_scope import ArtifactScopeError, LocalArtifactScopeStore
from hardware_pentest.core.models import Action, ActionClass, ExecutionStatus


def _action(path: str) -> Action:
    return Action(
        action_id="artifact.firmware.inspect.v1:target-1",
        capability_id="artifact.firmware.inspect",
        target_id="target-1",
        action_class=ActionClass.OBSERVE,
        inputs={"artifact_path": path},
    )


def test_artifact_scope_resolves_only_files_inside_root(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    firmware = artifact_root / "firmware.bin"
    firmware.write_bytes(b"firmware")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")

    store = LocalArtifactScopeStore(tmp_path / "scopes")
    scope = store.save(engagement_id="eng-1", artifact_root=artifact_root)

    assert scope.root == artifact_root.resolve()
    assert store.resolve_file("eng-1", "firmware.bin") == firmware.resolve()
    with pytest.raises(ArtifactScopeError):
        store.resolve_file("eng-1", "../outside.bin")
    with pytest.raises(ArtifactScopeError):
        store.resolve_file("eng-1", str(outside.resolve()))


def test_artifact_scope_rejects_symlink_escape(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    link = artifact_root / "link.bin"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable in this test environment")

    store = LocalArtifactScopeStore(tmp_path / "scopes")
    store.save(engagement_id="eng-1", artifact_root=artifact_root)

    with pytest.raises(ArtifactScopeError):
        store.resolve_file("eng-1", "link.bin")


def test_host_adapter_inspects_bounded_metadata_without_mutation(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    content = b"\x7fELF" + b"firmware-payload"
    firmware = artifact_root / "firmware.bin"
    firmware.write_bytes(content)

    scopes = LocalArtifactScopeStore(tmp_path / "scopes")
    scopes.save(engagement_id="eng-1", artifact_root=artifact_root)
    adapter = HostArtifactAdapter(engagement_id="eng-1", scopes=scopes, header_bytes=8)

    result = adapter.execute(_action("firmware.bin"))

    assert result.status is ExecutionStatus.SUCCESS
    assert result.instrument_id == "host.local"
    assert result.normalized == {
        "artifact_path": "firmware.bin",
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "header_hex": content[:8].hex(),
    }
    assert result.artifacts == ("firmware.bin",)
    assert firmware.read_bytes() == content


def test_host_adapter_rejects_oversize_artifact(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    (artifact_root / "large.bin").write_bytes(b"12345")
    scopes = LocalArtifactScopeStore(tmp_path / "scopes")
    scopes.save(engagement_id="eng-1", artifact_root=artifact_root)
    adapter = HostArtifactAdapter(
        engagement_id="eng-1",
        scopes=scopes,
        max_artifact_bytes=4,
    )

    validation = adapter.validate(_action("large.bin"))

    assert validation.valid is False
    assert "exceeds maximum size" in str(validation.reason)


def test_artifact_test_case_is_provider_neutral() -> None:
    test_case = artifact_test_catalog()[0]
    serialized = " ".join(
        (
            test_case.test_case_id,
            test_case.title,
            test_case.purpose,
            test_case.required_capability,
            *test_case.prerequisites,
            *test_case.expected_evidence,
        )
    ).lower()

    assert test_case.required_capability == "artifact.firmware.inspect"
    assert test_case.action_class is ActionClass.OBSERVE
    assert test_case.required_inputs == ("artifact_path",)
    assert "flipper" not in serialized
    assert "host.local" not in serialized
