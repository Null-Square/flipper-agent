from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pytest

from hardware_pentest.adapters.simulated import SimulatedAdapter
from hardware_pentest.assessment.adaptive_catalog import adaptive_hardware_test_catalog
from hardware_pentest.assessment.models import (
    AssessmentState,
    AssessmentStatus,
    PlannedStep,
    StepStatus,
)
from hardware_pentest.core.hardware import (
    DeploymentMethod,
    EvidenceChannel,
    HardwareDescriptor,
    HardwareDirection,
    HardwareIdentity,
    HardwareInterface,
    ToolchainDescriptor,
)
from hardware_pentest.core.models import ActionClass, Target
from hardware_pentest.core.registry import CapabilityRegistry
from hardware_pentest.providers.registry import HardwareProviderRegistry
from hardware_pentest.providers.simulated import SimulatedHardwareProvider
from hardware_pentest.service import HardwarePentestService
from hardware_pentest.synthesis import (
    AdaptiveSynthesisProfile,
    CapabilityGapWorkOrderBuilder,
    CapabilitySynthesisWorkOrderPlanner,
    FlipperSynthesisCompatibilityBackend,
    SynthesisWorkOrderState,
)


@dataclass
class _StaticProvider:
    descriptor: HardwareDescriptor

    def probe_hardware(self) -> HardwareIdentity:
        return self.descriptor.identity

    def describe_hardware(self) -> HardwareDescriptor:
        return self.descriptor


def _flipper_descriptor() -> HardwareDescriptor:
    return HardwareDescriptor(
        identity=HardwareIdentity(
            provider_id="flipper:test-001",
            kind="flipper-zero",
            model="Flipper Zero",
            transport="usb-cdc",
            firmware_version="lab-fw",
            provider_version="test-adapter",
        ),
        architecture="stm32wb55rg",
        interfaces=(
            HardwareInterface(
                interface_id="external.uart",
                kind="uart",
                direction=HardwareDirection.BIDIRECTIONAL,
                attributes={"external_header": True},
            ),
        ),
        artifact_types=("fap",),
        toolchains=(
            ToolchainDescriptor(
                toolchain_id="ufbt",
                artifact_types=("fap",),
                languages=("c",),
                available=None,
            ),
        ),
        deployment_methods=(
            DeploymentMethod(
                method_id="fap-storage-loader",
                artifact_types=("fap",),
                transport="usb-cdc",
                recoverable=True,
            ),
        ),
        evidence_channels=(
            EvidenceChannel(
                channel_id="generated-app-json",
                transport="app-private-storage",
                media_type="application/json",
                max_bytes=4096,
            ),
        ),
    )


def _state() -> AssessmentState:
    test_case = adaptive_hardware_test_catalog()[0]
    action = test_case.build_action(target_id="lab-target")
    timestamp = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
    return AssessmentState(
        schema_version="1",
        assessment_id="adaptive-assessment",
        engagement_id="engagement-lab",
        target=Target(target_id="lab-target", description="Authorized lab PCB"),
        status=AssessmentStatus.CAPABILITY_GAP,
        created_at=timestamp,
        updated_at=timestamp,
        steps=(
            PlannedStep(
                step_id="adaptive-assessment:adaptive.uart.autodetect.v1",
                test_case_id=test_case.test_case_id,
                action=action,
                status=StepStatus.CAPABILITY_GAP,
                reason="No connected instrument provides internal.uart.autodetect",
                required_capability=test_case.required_capability,
            ),
        ),
    )


def _planner(
    *,
    capabilities: CapabilityRegistry | None = None,
) -> CapabilitySynthesisWorkOrderPlanner:
    providers = HardwareProviderRegistry()
    providers.register(_StaticProvider(_flipper_descriptor()))
    return CapabilitySynthesisWorkOrderPlanner(
        capabilities=capabilities or CapabilityRegistry(),
        providers=providers,
        backends=(FlipperSynthesisCompatibilityBackend(),),
        builder=CapabilityGapWorkOrderBuilder(test_cases=adaptive_hardware_test_catalog()),
    )


def test_uart_gap_produces_deterministic_flipper_candidate_work_order() -> None:
    state = _state()
    planner = _planner()

    first = planner.create(state, state.steps[0].step_id).to_dict()
    second = planner.create(state, state.steps[0].step_id).to_dict()

    assert first == second
    assert first["state"] == SynthesisWorkOrderState.GENERATE_CANDIDATE.value
    request = first["request"]
    assert request["capability_id"] == "internal.uart.autodetect"
    assert request["target_id"] == "lab-target"
    assert request["max_action_class"] == "OBSERVE"
    assert request["requested_interfaces"] == ["uart"]
    assert request["accepted_artifact_types"] == ["fap"]
    assert request["accepted_architectures"] == ["stm32wb55rg"]
    assert request["constraints"]["action_inputs"] == {
        "duration_seconds": 5.0,
        "max_sample_bytes": 2048,
        "max_candidates": 8,
    }
    route = first["selected_route"]
    assert route["backend_id"] == "flipper-fap-v1"
    assert route["provider_id"] == "flipper:test-001"
    assert route["hardware_descriptor_sha256"] == _flipper_descriptor().fingerprint
    assert route["compatible"] is True
    contract = first["source_generation_contract"]
    assert contract["max_action_class"] == "OBSERVE"
    assert contract["declared_interfaces"] == ["uart"]
    assert contract["human_action_required_before_execution"] is True
    assert contract["approval_required_before_execution"] is False
    assert "transmit to the target" in contract["forbidden_behavior"]


def test_work_order_rejects_non_gap_steps() -> None:
    state = _state()
    ready = replace(
        state,
        steps=(replace(state.steps[0], status=StepStatus.READY),),
    )

    with pytest.raises(ValueError, match="CAPABILITY_GAP"):
        _planner().create(ready, ready.steps[0].step_id)


def test_work_order_rejects_persisted_authority_drift() -> None:
    state = _state()
    action = state.steps[0].action
    assert action is not None
    drifted_action = replace(action, action_class=ActionClass.TRANSMIT)
    drifted = replace(
        state,
        steps=(replace(state.steps[0], action=drifted_action),),
    )

    with pytest.raises(ValueError, match="Action class"):
        _planner().create(drifted, drifted.steps[0].step_id)


def test_missing_synthesis_profile_fails_closed() -> None:
    unrelated = AdaptiveSynthesisProfile(
        capability_id="internal.spi.capture",
        requested_interfaces=("spi",),
        accepted_artifact_types=("fap",),
        accepted_architectures=("stm32wb55rg",),
        source_language="c",
        manifest_api_groups=("spi", "logging"),
    )
    builder = CapabilityGapWorkOrderBuilder(
        test_cases=adaptive_hardware_test_catalog(),
        profiles=(unrelated,),
    )
    providers = HardwareProviderRegistry()
    providers.register(_StaticProvider(_flipper_descriptor()))
    planner = CapabilitySynthesisWorkOrderPlanner(
        capabilities=CapabilityRegistry(),
        providers=providers,
        backends=(FlipperSynthesisCompatibilityBackend(),),
        builder=builder,
    )

    with pytest.raises(LookupError, match="No adaptive synthesis profile"):
        planner.create(_state(), _state().steps[0].step_id)


def test_incompatible_provider_is_explained_without_fallback() -> None:
    providers = HardwareProviderRegistry()
    providers.register(SimulatedHardwareProvider())
    planner = CapabilitySynthesisWorkOrderPlanner(
        capabilities=CapabilityRegistry(),
        providers=providers,
        backends=(FlipperSynthesisCompatibilityBackend(),),
        builder=CapabilityGapWorkOrderBuilder(test_cases=adaptive_hardware_test_catalog()),
    )

    order = planner.create(_state(), _state().steps[0].step_id).to_dict()

    assert order["state"] == SynthesisWorkOrderState.NO_COMPATIBLE_PROVIDER.value
    assert order["selected_route"] is None
    assert order["evaluated_routes"]
    assert order["evaluated_routes"][0]["compatible"] is False
    assert order["evaluated_routes"][0]["hardware_descriptor_sha256"]
    assert order["next_action"] == "inspect_route_incompatibility"


def test_current_route_turns_gap_into_already_implemented_work_order() -> None:
    capabilities = CapabilityRegistry()
    capabilities.register(
        SimulatedAdapter(
            scripted_results={"internal.uart.autodetect": {}},
            capability_classes={"internal.uart.autodetect": ActionClass.OBSERVE},
        )
    )

    order = _planner(capabilities=capabilities).create(
        _state(),
        _state().steps[0].step_id,
    ).to_dict()

    assert order["state"] == SynthesisWorkOrderState.ALREADY_IMPLEMENTED.value
    assert order["request"] is None
    assert order["source_generation_contract"] is None
    assert order["next_action"] == "refresh_assessment"


def test_facade_work_order_does_not_mutate_assessment_or_create_implementation(tmp_path) -> None:
    service = HardwarePentestService(
        assessment_root=tmp_path / "assessments",
        engagement_root=tmp_path / "engagements",
        evidence_root=tmp_path / "evidence",
        verification_root=tmp_path / "verification",
        preflight_root=tmp_path / "preflight",
        gate_root=tmp_path / "gates",
        implementation_root=tmp_path / "implementations",
    )
    state = _state()
    service.assessments.save(state)

    order = service.assessment_synthesis_work_order(
        state.assessment_id,
        state.steps[0].step_id,
        instrument_backend="simulator",
    )

    assert order["state"] == SynthesisWorkOrderState.NO_COMPATIBLE_PROVIDER.value
    assert service.assessments.load(state.assessment_id) == state
    assert service.implementations.records() == ()
    assert service.verification.records() == ()
