from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hardware_pentest.core.engagement_store import LocalEngagementStore
from hardware_pentest.core.models import ActionClass, Engagement, Target
from hardware_pentest.service.execution import InstrumentSelection
from hardware_pentest.service.planning import HarnessAssessmentPlanner


def _planner(tmp_path: Path) -> HarnessAssessmentPlanner:
    return HarnessAssessmentPlanner(
        assessment_root=tmp_path / "assessments",
        engagement_root=tmp_path / "engagements",
        verification_root=tmp_path / "verification",
        preflight_root=tmp_path / "preflight",
    )


def _persist_scope(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    target = Target(target_id="camera-1", description="Authorized lab camera")
    engagement = Engagement(
        engagement_id="engagement-1",
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=1),
        target_ids=frozenset({target.target_id}),
        allowed_capabilities=(
            "infrared.observe",
            "wireless.subghz.observe",
            "wireless.nfc.identify",
            "internal.gpio.inspect",
        ),
        denied_capabilities=(),
        max_action_class=ActionClass.INTERACT,
    )
    LocalEngagementStore(tmp_path / "engagements").save(engagement, (target,))


def test_planning_from_persisted_scope_is_deterministic_and_passive_first(tmp_path: Path) -> None:
    _persist_scope(tmp_path)
    planner = _planner(tmp_path)

    first = planner.create(
        engagement_id="engagement-1",
        target_id="camera-1",
        instrument=InstrumentSelection(),
        assessment_id="assessment-1",
        gpio_pin="PA7",
    )
    candidates = planner.candidates(first.assessment_id)

    assert first.assessment_id == "assessment-1"
    assert [item["test_case_id"] for item in candidates["candidates"]] == [
        "flipper.ir.observe.v1",
        "flipper.subghz.observe.v1",
        "flipper.gpio.inspect.v1",
        "flipper.nfc.identify.v1",
    ]
    assert candidates["candidates"][0]["rank"] == 1
    assert candidates["candidates"][0]["action_class"] == "OBSERVE"
    assert candidates["candidates"][0]["expected_evidence"]
    assert candidates["candidates"][0]["result_rules"]
    assert candidates["candidates"][2]["requires_human_action"] is True
    assert candidates["selection_rule"].startswith("deterministic passive-first")


def test_candidate_surface_exposes_input_keys_not_action_values(tmp_path: Path) -> None:
    _persist_scope(tmp_path)
    planner = _planner(tmp_path)
    state = planner.create(
        engagement_id="engagement-1",
        target_id="camera-1",
        instrument=InstrumentSelection(),
        assessment_id="assessment-1",
        gpio_pin="PA7",
    )

    candidates = planner.candidates(state.assessment_id)
    gpio = next(item for item in candidates["candidates"] if item["test_case_id"].endswith("gpio.inspect.v1"))

    assert gpio["input_keys"] == ["pin"]
    assert "PA7" not in repr(gpio)


def test_network_catalog_cannot_be_requested_without_composite_backend(tmp_path: Path) -> None:
    _persist_scope(tmp_path)
    planner = _planner(tmp_path)

    with pytest.raises(ValueError, match="network tests require"):
        planner.create(
            engagement_id="engagement-1",
            target_id="camera-1",
            instrument=InstrumentSelection(backend="simulator"),
            include_network_tests=True,
        )


def test_planner_cannot_create_assessment_for_target_outside_stored_scope(tmp_path: Path) -> None:
    _persist_scope(tmp_path)
    planner = _planner(tmp_path)

    with pytest.raises(ValueError, match="not present in stored engagement scope"):
        planner.create(
            engagement_id="engagement-1",
            target_id="other-target",
            instrument=InstrumentSelection(),
        )


@pytest.mark.parametrize("value", [0, 51, True, "20"])
def test_candidate_limit_fails_closed(tmp_path: Path, value) -> None:
    _persist_scope(tmp_path)
    planner = _planner(tmp_path)
    state = planner.create(
        engagement_id="engagement-1",
        target_id="camera-1",
        instrument=InstrumentSelection(),
        gpio_pin="PA7",
    )

    with pytest.raises(ValueError, match="candidate limit"):
        planner.candidates(state.assessment_id, limit=value)
