from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from hardware_pentest.adapters.simulated import SimulatedAdapter
from hardware_pentest.assessment import (
    AssessmentPlanner,
    AssessmentRunner,
    LocalAssessmentStore,
    flipper_mvp_test_catalog,
)
from hardware_pentest.core.models import ActionClass, Engagement, Target
from hardware_pentest.core.registry import CapabilityRegistry
from hardware_pentest.evidence.store import LocalEvidenceStore
from hardware_pentest.policy.engine import PolicyEngine
from hardware_pentest.reporting import (
    ReportIntegrityError,
    build_assessment_report_data,
    render_assessment_markdown,
)
from hardware_pentest.runtime.executor import AssessmentExecutor


def engagement() -> Engagement:
    now = datetime.now(UTC)
    return Engagement(
        engagement_id="report-lab",
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(minutes=10),
        target_ids=frozenset({"target-a"}),
        allowed_capabilities=("infrared.observe",),
        denied_capabilities=(),
        max_action_class=ActionClass.OBSERVE,
    )


def completed_state(tmp_path):
    registry = CapabilityRegistry()
    registry.register(SimulatedAdapter(scripted_results={"infrared.observe": {}}))
    test_cases = tuple(
        item
        for item in flipper_mvp_test_catalog()
        if item.required_capability == "infrared.observe"
    )
    state = AssessmentPlanner().plan(
        engagement=engagement(),
        target=Target(target_id="target-a", description="Lab target"),
        registry=registry,
        test_cases=test_cases,
        assessment_id="assessment-report",
    )
    assessment_store = LocalAssessmentStore(tmp_path / "assessments")
    evidence_store = LocalEvidenceStore(tmp_path / "evidence")
    runner = AssessmentRunner(
        executor=AssessmentExecutor(
            registry=registry,
            policy=PolicyEngine(),
            evidence=evidence_store,
        ),
        store=assessment_store,
    )
    return runner.run_next(engagement(), state).state, evidence_store


def test_report_contains_only_persisted_findings_and_validated_evidence(tmp_path) -> None:
    state, evidence_store = completed_state(tmp_path)

    report = build_assessment_report_data(state, evidence_store)
    markdown = render_assessment_markdown(report)

    evidence_id = state.steps[0].evidence_ids[0]
    assert report["summary"]["confirmed_findings"] == 0
    assert report["evidence"][0]["raw_artifact_intact"] is True
    assert evidence_id in markdown
    assert "No confirmed findings were recorded." in markdown
    assert "Observed interfaces or signals are not vulnerabilities by themselves." in markdown


def test_report_refuses_tampered_raw_artifact(tmp_path) -> None:
    state, evidence_store = completed_state(tmp_path)
    evidence_id = state.steps[0].evidence_ids[0]
    record = evidence_store.get(state.engagement_id, evidence_id)
    assert record.raw_artifact_reference is not None
    path = evidence_store.root / record.raw_artifact_reference
    path.write_text('{"tampered":true}\n', encoding="utf-8")

    with pytest.raises(ReportIntegrityError, match="missing or modified"):
        build_assessment_report_data(state, evidence_store)


def test_report_refuses_success_step_without_evidence(tmp_path) -> None:
    state, evidence_store = completed_state(tmp_path)
    forged_step = replace(state.steps[0], evidence_ids=())
    forged = replace(state, steps=(forged_step,))

    with pytest.raises(ReportIntegrityError, match="no evidence references"):
        build_assessment_report_data(forged, evidence_store)


def test_report_refuses_evidence_from_different_planned_instrument(tmp_path) -> None:
    state, evidence_store = completed_state(tmp_path)
    forged_step = replace(state.steps[0], instrument_id="simulator-other")
    forged = replace(state, steps=(forged_step,))

    with pytest.raises(ReportIntegrityError, match="instrument does not match"):
        build_assessment_report_data(forged, evidence_store)
