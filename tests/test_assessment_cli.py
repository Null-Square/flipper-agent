from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from hardware_pentest.assessment import AssessmentStatus, LocalAssessmentStore, StepStatus
from hardware_pentest.interfaces.assessment_cli import handle_assessment_command
from hardware_pentest.interfaces.cli import build_parser


def write_engagement(tmp_path):
    now = datetime.now(UTC)
    start = (now - timedelta(minutes=1)).isoformat()
    end = (now + timedelta(hours=1)).isoformat()
    path = tmp_path / "engagement.yaml"
    path.write_text(
        f"""engagement_id: cli-lab
valid_from: '{start}'
valid_until: '{end}'
mode: non-destructive
max_action_class: INTERACT
targets:
  - target_id: target-a
    description: CLI lab target
allowed_capabilities:
  - infrared.*
  - wireless.*
  - internal.gpio.*
denied_capabilities:
  - '*.transmit'
  - '*.emulate'
  - '*.write'
""",
        encoding="utf-8",
    )
    return path


def parse(*parts: str):
    return build_parser().parse_args(list(parts))


def test_cli_create_pause_resume_and_report_with_simulator(tmp_path, capsys) -> None:
    engagement = write_engagement(tmp_path)
    assessment_root = tmp_path / "assessments"
    evidence_root = tmp_path / "evidence"
    report_path = tmp_path / "report.json"

    create = parse(
        "assessment-create",
        "--engagement",
        str(engagement),
        "--target",
        "target-a",
        "--assessment-id",
        "cli-assessment",
        "--assessment-root",
        str(assessment_root),
        "--gpio-pin",
        "PA7",
    )
    assert handle_assessment_command(create) is True
    capsys.readouterr()

    store = LocalAssessmentStore(assessment_root)
    planned = store.load("cli-assessment")
    assert planned.status is AssessmentStatus.PLANNED
    assert len(planned.steps) == 4

    first_run = parse(
        "assessment-run",
        "cli-assessment",
        "--engagement",
        str(engagement),
        "--assessment-root",
        str(assessment_root),
        "--evidence-root",
        str(evidence_root),
    )
    assert handle_assessment_command(first_run) is True
    capsys.readouterr()

    paused = store.load("cli-assessment")
    assert paused.status is AssessmentStatus.HUMAN_ACTION_REQUIRED
    assert paused.steps[0].status is StepStatus.SUCCESS
    assert paused.steps[1].status is StepStatus.SUCCESS
    assert paused.steps[2].status is StepStatus.HUMAN_ACTION_REQUIRED
    assert paused.steps[3].status is StepStatus.READY

    resume = parse(
        "assessment-run",
        "cli-assessment",
        "--engagement",
        str(engagement),
        "--assessment-root",
        str(assessment_root),
        "--evidence-root",
        str(evidence_root),
        "--confirm-human-action",
    )
    assert handle_assessment_command(resume) is True
    capsys.readouterr()

    completed = store.load("cli-assessment")
    assert completed.status is AssessmentStatus.COMPLETED
    assert all(step.evidence_ids for step in completed.steps)
    assert len(completed.observations) == 4
    assert completed.findings == ()

    report = parse(
        "assessment-report",
        "cli-assessment",
        "--assessment-root",
        str(assessment_root),
        "--evidence-root",
        str(evidence_root),
        "--format",
        "json",
        "--output",
        str(report_path),
    )
    assert handle_assessment_command(report) is True
    capsys.readouterr()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["assessment_status"] == "completed"
    assert payload["summary"]["confirmed_findings"] == 0
    assert len(payload["evidence"]) == 4
    assert all(item["raw_artifact_intact"] for item in payload["evidence"])


def test_cli_parser_has_no_raw_action_or_manual_finding_confirmation_surface() -> None:
    parser = build_parser()
    assessment = parser.parse_args(
        [
            "assessment-run",
            "assessment-1",
            "--engagement",
            "scope.yaml",
            "--max-steps",
            "1",
        ]
    )

    assert not hasattr(assessment, "raw_command")
    assert not hasattr(assessment, "capability_id")
    assert not hasattr(assessment, "confirm_finding")
