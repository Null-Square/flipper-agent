from hardware_pentest.adapters.simulated import SimulatedAdapter
from hardware_pentest.core.models import ActionClass
from hardware_pentest.core.registry import CapabilityRegistry


def test_registry_keeps_routes_bound_to_adapter_when_instrument_id_is_shared() -> None:
    first = SimulatedAdapter(
        instrument_id="shared-instrument",
        scripted_results={"internal.uart.autodetect": {}},
        capability_classes={"internal.uart.autodetect": ActionClass.OBSERVE},
    )
    second = SimulatedAdapter(
        instrument_id="shared-instrument",
        scripted_results={"internal.spi.identify": {}},
        capability_classes={"internal.spi.identify": ActionClass.OBSERVE},
    )
    registry = CapabilityRegistry()

    registry.register(first)
    registry.register(second)

    assert registry.instruments() == ["shared-instrument"]
    assert registry.choose("internal.uart.autodetect").adapter is first
    assert registry.choose("internal.spi.identify").adapter is second
    assert {item.capability_id for item in registry.capabilities()} == {
        "internal.uart.autodetect",
        "internal.spi.identify",
    }


def test_registry_ignores_duplicate_registration_of_same_adapter_object() -> None:
    adapter = SimulatedAdapter(
        instrument_id="shared-instrument",
        scripted_results={"internal.uart.autodetect": {}},
    )
    registry = CapabilityRegistry()

    registry.register(adapter)
    registry.register(adapter)

    assert len(registry.routes_for("internal.uart.autodetect")) == 1
