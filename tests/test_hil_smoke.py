from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hardware_pentest.adapters.flipper.adapter import FlipperAdapter
from hardware_pentest.adapters.marauder.adapter import MarauderAdapter
from hardware_pentest.assessment import AssessmentPlanner
from hardware_pentest.assessment.interface_catalog import interface_test_catalog
from hardware_pentest.assessment.store import LocalAssessmentStore
from hardware_pentest.core.artifact_scope import LocalArtifactScopeStore
from hardware_pentest.core.engagement_store import LocalEngagementStore
from hardware_pentest.core.models import ActionClass, Engagement, ExecutionStatus, Target
from hardware_pentest.evidence.store import LocalEvidenceStore
from hardware_pentest.preflight.ports import metadata_for_port, serial_discovery_available
from hardware_pentest.preflight.store import LocalPreflightStore
from hardware_pentest.service.execution import (
    HarnessAssessmentExecutor,
    InstrumentSelection,
    build_registry,
)
from hardware_pentest.service.gates import GateKind, LocalGateStore
from hardware_pentest.synthesis.store import LocalCapabilityImplementationStore
from hardware_pentest.verification.store import LocalVerificationStore

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


def test_attached_serial_target_completes_host_only_assessment(tmp_path: Path) -> None:
    if not _hil_enabled():
        pytest.skip("Set HPA_HIL=1 to allow physical hardware tests")

    _run_serial_target_assessment(
        tmp_path,
        instrument=InstrumentSelection(backend="simulator"),
        assessment_suffix="host-only",
    )


def test_attached_serial_target_route_survives_flipper_when_configured(tmp_path: Path) -> None:
    if not _hil_enabled():
        pytest.skip("Set HPA_HIL=1 to allow physical hardware tests")
    flipper_port = os.environ.get("HPA_FLIPPER_PORT")
    if not flipper_port:
        pytest.skip("HPA_FLIPPER_PORT is not configured for the additive-provider HIL run")

    _run_serial_target_assessment(
        tmp_path,
        instrument=InstrumentSelection(backend="flipper", flipper_port=flipper_port),
        assessment_suffix="with-flipper",
    )


def _run_serial_target_assessment(
    tmp_path: Path,
    *,
    instrument: InstrumentSelection,
    assessment_suffix: str,
) -> None:
    port = _required_env("HPA_SERIAL_TARGET_PORT")
    baudrate = _bounded_int_env("HPA_SERIAL_TARGET_BAUD", minimum=300, maximum=1_000_000)
    expected = _required_env("HPA_SERIAL_TARGET_EXPECT")
    duration = _bounded_float_env(
        "HPA_SERIAL_TARGET_DURATION",
        default=1.0,
        minimum=0.01,
        maximum=5.0,
    )
    max_bytes = _bounded_int_env(
        "HPA_SERIAL_TARGET_MAX_BYTES",
        default=4096,
        minimum=1,
        maximum=64 * 1024,
    )
    if os.environ.get("HPA_SERIAL_TARGET_APPROVE") != "1":
        pytest.fail(
            "Set HPA_SERIAL_TARGET_APPROVE=1 to approve the bounded serial-open/read HIL step"
        )
    if not serial_discovery_available():
        pytest.fail("Serial HIL requires pyserial; install with pip install -e '.[dev,serial]'")

    metadata = metadata_for_port(port)
    if metadata is None:
        pytest.fail(f"Configured HPA serial target is not present in discovery: {port}")

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
    now = datetime.now(UTC)
    engagement = Engagement(
        engagement_id=f"hil-serial-{assessment_suffix}",
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(minutes=30),
        target_ids=frozenset({"hil-serial-target"}),
        allowed_capabilities=("interface.serial.inspect", "interface.serial.observe"),
        denied_capabilities=(),
        max_action_class=ActionClass.INTERACT,
        mode="controlled-hil",
    )
    target = Target(
        target_id="hil-serial-target",
        description="Operator-configured physical USB serial HIL target",
        metadata={
            "serial_device": port,
            "usb_serial_number": metadata.serial_number,
            "usb_vid": metadata.vid,
            "usb_pid": metadata.pid,
        },
    )
    LocalEngagementStore(roots["engagement"]).save(engagement, (target,))

    verification = LocalVerificationStore(roots["verification"])
    preflight = LocalPreflightStore(roots["preflight"])
    implementations = LocalCapabilityImplementationStore(roots["implementation"])
    artifact_scopes = LocalArtifactScopeStore(roots["artifact_scope"])
    registry = build_registry(
        instrument,
        verification=verification,
        preflight=preflight,
        implementations=implementations,
        engagement_id=engagement.engagement_id,
        artifact_scopes=artifact_scopes,
    )
    state = AssessmentPlanner().plan(
        engagement=engagement,
        target=target,
        registry=registry,
        test_cases=interface_test_catalog(),
        test_inputs={
            "interface.serial.inspect.v1": {"serial_device": port},
            "interface.serial.observe.v1": {
                "serial_device": port,
                "baudrate": baudrate,
                "duration_seconds": duration,
                "max_bytes": max_bytes,
            },
        },
        assessment_id=f"hil-serial-{assessment_suffix}",
    )
    LocalAssessmentStore(roots["assessment"]).save(state)

    inspect_step = state.step(f"{state.assessment_id}:interface.serial.inspect.v1")
    observe_step = state.step(f"{state.assessment_id}:interface.serial.observe.v1")
    assert inspect_step.instrument_id == "host.local"
    assert inspect_step.status.value == "ready"
    assert observe_step.instrument_id == "host.local"
    assert observe_step.status.value == "approval_required"

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
    inspected = executor.execute_next(state.assessment_id, instrument=instrument)
    assert inspected["execution_status"] == ExecutionStatus.SUCCESS.value

    before_approval = executor.execute_next(state.assessment_id, instrument=instrument)
    assert before_approval["paused"] is True

    LocalGateStore(roots["gate"]).grant(
        assessment_id=state.assessment_id,
        step_id=observe_step.step_id,
        kind=GateKind.APPROVAL,
    )
    captured = executor.execute_next(state.assessment_id, instrument=instrument)
    assert captured["execution_status"] == ExecutionStatus.SUCCESS.value

    records = LocalEvidenceStore(roots["evidence"]).records(engagement.engagement_id)
    observation = next(
        record for record in records if record.capability_id == "interface.serial.observe"
    )
    assert observation.target_id == target.target_id
    assert observation.instrument_id == "host.local"
    assert observation.normalized_inputs["serial_device"] == port
    assert observation.normalized_inputs["baudrate"] == baudrate

    normalized = observation.normalized_observation
    assert 0 < int(normalized["byte_count"]) <= max_bytes
    assert len(str(normalized["sha256"])) == 64
    assert expected in str(normalized["text_preview"])
    assert float(normalized["actual_duration_seconds"]) <= min(5.0, duration) + 0.15


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value or not value.strip():
        pytest.fail(f"{name} is required for the serial-target HIL profile")
    return value.strip()


def _bounded_int_env(
    name: str,
    *,
    minimum: int,
    maximum: int,
    default: int | None = None,
) -> int:
    raw = os.environ.get(name)
    if raw is None and default is not None:
        return default
    if raw is None:
        pytest.fail(f"{name} is required for the serial-target HIL profile")
    try:
        value = int(raw)
    except ValueError:
        pytest.fail(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        pytest.fail(f"{name} must be between {minimum} and {maximum}")
    return value


def _bounded_float_env(
    name: str,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    raw = os.environ.get(name)
    try:
        value = default if raw is None else float(raw)
    except ValueError:
        pytest.fail(f"{name} must be numeric")
    if not minimum <= value <= maximum:
        pytest.fail(f"{name} must be between {minimum} and {maximum}")
    return value
