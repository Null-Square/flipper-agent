from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from hardware_pentest.core.models import ActionClass
from hardware_pentest.synthesis import (
    CapabilitySynthesisRequest,
    CapabilitySynthesisService,
    GeneratedAppBuildError,
    GeneratedAppManifest,
    GeneratedProjectWriter,
    GeneratedSourcePolicy,
    SynthesisPolicyProfile,
    SynthesisRejected,
    UfbTBuilder,
)

SAFE_GPIO_SOURCE = r'''
#include <furi.h>
#include <furi_hal_gpio.h>
#include "hpa_runtime.h"

int32_t hpa_generated_main(void* context) {
    UNUSED(context);
    bool value = furi_hal_gpio_read(&gpio_ext_pa7);
    const char* result = value
        ? "{\"schema_version\":\"1\",\"status\":\"success\",\"observations\":{\"PA7\":1}}"
        : "{\"schema_version\":\"1\",\"status\":\"success\",\"observations\":{\"PA7\":0}}";
    return hpa_write_evidence_json(result) ? 0 : 1;
}
'''.strip()


def _request(*, action_class: ActionClass = ActionClass.OBSERVE):
    return CapabilitySynthesisRequest(
        request_id="req-1",
        capability_id="generated.gpio.sample",
        target_id="lab-target",
        objective="Read one operator-prepared GPIO input and report its level.",
        requested_interfaces=("gpio",),
        max_action_class=action_class,
        expected_evidence=("Observed GPIO input level",),
    )


def _manifest(*, action_class: ActionClass = ActionClass.OBSERVE):
    return GeneratedAppManifest(
        app_id="hpa_gen_gpio_sample",
        display_name="HPA GPIO Sample",
        capability_id="generated.gpio.sample",
        declared_interfaces=("gpio",),
        declared_action_class=action_class,
        requested_api_groups=("gpio", "logging"),
        max_runtime_seconds=5.0,
        expected_evidence=("Observed GPIO input level",),
    )


def test_safe_read_only_generated_source_is_allowed() -> None:
    decision = GeneratedSourcePolicy().evaluate(_request(), _manifest(), SAFE_GPIO_SOURCE)

    assert decision.allowed is True
    assert decision.errors == ()
    assert decision.inferred_interfaces == ("gpio",)


def test_generated_source_requires_bounded_evidence_writer() -> None:
    source = SAFE_GPIO_SOURCE.replace(
        "return hpa_write_evidence_json(result) ? 0 : 1;",
        "return 0;",
    )

    decision = GeneratedSourcePolicy().evaluate(_request(), _manifest(), source)

    assert decision.allowed is False
    assert any(item.rule_id == "source.no_evidence_writer" for item in decision.errors)


def test_generated_source_rejects_direct_storage_write() -> None:
    source = SAFE_GPIO_SOURCE + "\nvoid write_any(File* f) { storage_file_write(f, 0, 0); }"

    decision = GeneratedSourcePolicy().evaluate(_request(), _manifest(), source)

    assert decision.allowed is False
    assert any(
        item.rule_id == "source.prohibited_api" and item.token == "storage_file_write"
        for item in decision.errors
    )


def test_generated_source_rejects_undeclared_hardware_interface() -> None:
    source = SAFE_GPIO_SOURCE + "\nvoid extra(void) { furi_hal_i2c_acquire(0); }"
    decision = GeneratedSourcePolicy().evaluate(_request(), _manifest(), source)

    assert decision.allowed is False
    assert any(item.rule_id == "source.undeclared_interface" for item in decision.errors)


def test_generated_source_rejects_prohibited_transmit_api() -> None:
    source = SAFE_GPIO_SOURCE + "\nvoid tx(void) { furi_hal_subghz_start_async_tx(0, 0); }"
    decision = GeneratedSourcePolicy().evaluate(_request(), _manifest(), source)

    assert decision.allowed is False
    assert any(
        item.rule_id == "source.prohibited_api" and item.token == "furi_hal_subghz_start_async_tx"
        for item in decision.errors
    )


def test_default_synthesis_profile_rejects_transmit_class_generated_app() -> None:
    request = _request(action_class=ActionClass.TRANSMIT)
    manifest = _manifest(action_class=ActionClass.TRANSMIT)

    decision = GeneratedSourcePolicy().evaluate(request, manifest, SAFE_GPIO_SOURCE)

    assert decision.allowed is False
    assert any(item.rule_id == "manifest.profile_action_exceeded" for item in decision.errors)


def test_operator_profile_can_raise_action_ceiling_without_bypassing_source_rules() -> None:
    profile = SynthesisPolicyProfile(max_action_class=ActionClass.TRANSMIT)
    policy = GeneratedSourcePolicy(profile)
    request = _request(action_class=ActionClass.TRANSMIT)
    manifest = _manifest(action_class=ActionClass.TRANSMIT)

    allowed = policy.evaluate(request, manifest, SAFE_GPIO_SOURCE)
    prohibited = policy.evaluate(
        request,
        manifest,
        SAFE_GPIO_SOURCE + "\nvoid tx(void) { furi_hal_subghz_tx(); }",
    )

    assert allowed.allowed is True
    assert prohibited.allowed is False


def test_project_writer_creates_external_fap_project_with_hashes(tmp_path: Path) -> None:
    project = GeneratedProjectWriter(tmp_path / "generated").write(
        _manifest(),
        SAFE_GPIO_SOURCE,
    )

    assert project.source_path.read_text(encoding="utf-8").endswith("\n")
    fam = project.app_manifest_path.read_text(encoding="utf-8")
    assert 'appid="hpa_gen_gpio_sample"' in fam
    assert "FlipperAppType.EXTERNAL" in fam
    assert 'fap_category="NullSquare"' in fam
    assert 'targets=["f7"]' in fam
    assert {path.name for path in project.support_paths} == {"hpa_runtime.c", "hpa_runtime.h"}
    runtime_source = (project.root / "hpa_runtime.c").read_text(encoding="utf-8")
    assert 'APP_DATA_PATH("result.json")' in runtime_source
    assert "HPA_EVIDENCE_MAX_BYTES 4096" in runtime_source
    assert project.source_sha256 == hashlib.sha256(project.source_path.read_bytes()).hexdigest()
    assert project.app_manifest_sha256 == hashlib.sha256(
        project.app_manifest_path.read_bytes()
    ).hexdigest()
    assert project.synthesis_manifest_sha256 == hashlib.sha256(
        project.synthesis_manifest_path.read_bytes()
    ).hexdigest()


# Every file whose bytes are reviewed, hashed, and re-verified before build. These must be
# byte-identical on disk to the bytes that were hashed, on every platform.
_INTEGRITY_BOUND_FILES = (
    "main.c",
    "hpa_runtime.h",
    "hpa_runtime.c",
    "application.fam",
    "synthesis.json",
)


def _never_run(*args, **kwargs):
    raise AssertionError("uFBT must not be invoked when project integrity verification fails")


def test_generated_project_files_are_lf_only_and_byte_exact(tmp_path: Path) -> None:
    project = GeneratedProjectWriter(tmp_path / "generated").write(_manifest(), SAFE_GPIO_SOURCE)

    # LF-only on every platform: Path.write_text on Windows would rewrite LF as CRLF and
    # desynchronize the on-disk bytes from the reviewed/hashed bytes.
    for name in _INTEGRITY_BOUND_FILES:
        data = (project.root / name).read_bytes()
        assert b"\r\n" not in data, f"{name} was written with CRLF line endings"
        assert b"\r" not in data, f"{name} contains a bare carriage return"

    # Every recorded integrity hash must equal the digest of the exact bytes on disk.
    recorded = {
        "main.c": project.source_sha256,
        "application.fam": project.app_manifest_sha256,
        "synthesis.json": project.synthesis_manifest_sha256,
    }
    for name, digest in recorded.items():
        on_disk = hashlib.sha256((project.root / name).read_bytes()).hexdigest()
        assert digest == on_disk, f"recorded hash for {name} does not match bytes on disk"


def test_generated_project_hashes_are_deterministic_across_writes(tmp_path: Path) -> None:
    first = GeneratedProjectWriter(tmp_path / "a").write(_manifest(), SAFE_GPIO_SOURCE)
    second = GeneratedProjectWriter(tmp_path / "b").write(_manifest(), SAFE_GPIO_SOURCE)

    # Identical inputs produce identical hashes; combined with LF-only bytes this makes the
    # source-tree hash stable across platforms and repeated runs.
    assert first.source_sha256 == second.source_sha256
    assert first.app_manifest_sha256 == second.app_manifest_sha256
    assert first.source_tree_sha256 == second.source_tree_sha256
    assert first.synthesis_manifest_sha256 == second.synthesis_manifest_sha256


def test_generated_project_writer_does_not_rely_on_text_mode(tmp_path: Path, monkeypatch) -> None:
    # A regression that reintroduces Path.write_text() must fail here, not silently ship CRLF
    # artifacts on Windows.
    def _forbidden(*args, **kwargs):
        raise AssertionError("GeneratedProjectWriter must write bytes, not text")

    monkeypatch.setattr(Path, "write_text", _forbidden)
    project = GeneratedProjectWriter(tmp_path / "generated").write(_manifest(), SAFE_GPIO_SOURCE)
    assert project.source_path.read_bytes().endswith(b"\n")


def test_builder_rejects_post_write_mutation_of_every_integrity_bound_file(tmp_path: Path) -> None:
    for name in _INTEGRITY_BOUND_FILES:
        project = GeneratedProjectWriter(tmp_path / name.replace(".", "_")).write(
            _manifest(), SAFE_GPIO_SOURCE
        )
        target = project.root / name
        target.write_bytes(target.read_bytes() + b"\n/* tamper */\n")
        with pytest.raises(GeneratedAppBuildError):
            UfbTBuilder(runner=_never_run, timeout_seconds=10).build(project)


def test_project_writer_rejects_manifest_string_injection(tmp_path: Path) -> None:
    manifest = GeneratedAppManifest(
        **{
            **_manifest().__dict__,
            "display_name": 'Bad"\nApp(',
        }
    )

    with pytest.raises(ValueError, match="unsupported manifest characters"):
        GeneratedProjectWriter(tmp_path).write(manifest, SAFE_GPIO_SOURCE)


def test_ufbt_builder_uses_fixed_non_shell_command_and_records_provenance(tmp_path: Path) -> None:
    project = GeneratedProjectWriter(tmp_path / "generated").write(
        _manifest(),
        SAFE_GPIO_SOURCE,
    )
    calls: list[tuple[list[str], dict]] = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        if command == ["ufbt"]:
            dist = Path(kwargs["cwd"]) / "dist"
            dist.mkdir()
            (dist / "hpa_gen_gpio_sample.fap").write_bytes(b"compiled-fap")
            return subprocess.CompletedProcess(command, 0, stdout="build ok\n", stderr="")
        if command == ["ufbt", "--version"]:
            return subprocess.CompletedProcess(command, 0, stdout="ufbt 0.2-test\n", stderr="")
        raise AssertionError(command)

    artifact = UfbTBuilder(runner=runner, timeout_seconds=10).build(project)

    assert artifact.builder == "ufbt"
    assert artifact.builder_version == "ufbt 0.2-test"
    assert artifact.artifact_sha256 == hashlib.sha256(b"compiled-fap").hexdigest()
    assert artifact.source_sha256 == project.source_sha256
    assert artifact.source_tree_sha256 == project.source_tree_sha256
    assert artifact.app_manifest_sha256 == project.app_manifest_sha256
    assert artifact.build_command == ("ufbt",)
    assert artifact.build_log_path.is_file()
    assert calls[0][0] == ["ufbt"]
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["cwd"] == project.root.resolve()
    assert "GITHUB_TOKEN" not in calls[0][1]["env"]


def test_builder_rejects_source_changed_after_policy_review(tmp_path: Path) -> None:
    project = GeneratedProjectWriter(tmp_path).write(_manifest(), SAFE_GPIO_SOURCE)
    project.source_path.write_text(SAFE_GPIO_SOURCE + "\n// changed\n", encoding="utf-8")

    def forbidden_runner(*args, **kwargs):
        raise AssertionError("tampered project must never reach uFBT")

    with pytest.raises(GeneratedAppBuildError, match="source changed"):
        UfbTBuilder(runner=forbidden_runner).build(project)


def test_builder_rejects_trusted_support_runtime_tampering(tmp_path: Path) -> None:
    project = GeneratedProjectWriter(tmp_path).write(_manifest(), SAFE_GPIO_SOURCE)
    support = project.root / "hpa_runtime.c"
    support.write_text(support.read_text(encoding="utf-8") + "\n// tampered\n", encoding="utf-8")

    def forbidden_runner(*args, **kwargs):
        raise AssertionError("tampered support runtime must never reach uFBT")

    with pytest.raises(GeneratedAppBuildError, match="source tree changed"):
        UfbTBuilder(runner=forbidden_runner).build(project)


def test_ufbt_builder_fails_closed_on_timeout(tmp_path: Path) -> None:
    project = GeneratedProjectWriter(tmp_path).write(_manifest(), SAFE_GPIO_SOURCE)

    def runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    with pytest.raises(GeneratedAppBuildError, match="exceeded"):
        UfbTBuilder(runner=runner, timeout_seconds=2).build(project)


def test_synthesis_rejection_never_materializes_or_builds_project(tmp_path: Path) -> None:
    writer = GeneratedProjectWriter(tmp_path / "generated")

    def forbidden_runner(*args, **kwargs):
        raise AssertionError("builder must not execute for rejected source")

    service = CapabilitySynthesisService(
        policy=GeneratedSourcePolicy(),
        project_writer=writer,
        builder=UfbTBuilder(runner=forbidden_runner),
    )
    prohibited_source = SAFE_GPIO_SOURCE + "\nvoid tx(void) { furi_hal_subghz_tx(); }"

    with pytest.raises(SynthesisRejected):
        service.synthesize(_request(), _manifest(), prohibited_source)

    assert not (writer.root / _manifest().app_id).exists()
