import pytest

from hardware_pentest.adapters.flipper.adapter import (
    INFRARED_OBSERVE,
    NFC_IDENTIFY,
    SUBGHZ_OBSERVE,
    FlipperAdapter,
)
from hardware_pentest.adapters.flipper.capabilities.infrared import InfraredObserveCapability


def test_default_handler_registry_exposes_implemented_ids_without_probing() -> None:
    adapter = FlipperAdapter("/dev/not-opened")

    assert adapter.implemented_capabilities == frozenset(
        {INFRARED_OBSERVE, SUBGHZ_OBSERVE, NFC_IDENTIFY}
    )
    assert adapter.capabilities() == []


def test_duplicate_capability_handlers_are_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate Flipper capability handler"):
        FlipperAdapter(
            "/dev/not-opened",
            capability_handlers=(
                InfraredObserveCapability(),
                InfraredObserveCapability(),
            ),
        )


def test_unknown_capability_cannot_be_marked_verified() -> None:
    with pytest.raises(ValueError, match="Cannot verify unimplemented"):
        FlipperAdapter(
            "/dev/not-opened",
            verified_capabilities={"wireless.unknown.identify"},
        )
