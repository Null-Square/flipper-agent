# Deterministic serial HIL target

This fixture turns a cheap owned development board into a known target for the Hardware Pentest Agent host-provider HIL profile.

The target is intentionally simple. It continuously emits one deterministic banner:

```text
NULLSQUARE-HIL-READY
```

The purpose is not to test a vulnerability. It is to prove the physical assessment path:

```text
host discovery
  -> explicit target association
  -> metadata evidence
  -> approval boundary
  -> bounded serial observation
  -> durable evidence
```

## Choose one firmware variant

### Arduino-compatible board

Flash `serial_banner.ino` using the normal toolchain for the owned board. It uses 115200 baud and emits the banner every 100 ms.

This is suitable for many ESP32, RP2040, AVR, STM32, and other boards supported by an Arduino-compatible core. USB/serial presentation varies by board and core, so use the actual device shown by `hardware_discover()`.

### MicroPython board

Install MicroPython using the board vendor's normal process, then copy `main.py` to the board as `main.py`.

This is convenient for boards such as RP2040/Pico-class devices that expose the MicroPython console over USB serial. Console routing is board/port-specific; confirm the banner appears on the selected host serial interface before running HIL.

## Verify the fixture manually

Before invoking Hardware Pentest Agent, confirm the target continuously emits the expected banner with a normal serial terminal at the configured baudrate. Close that terminal before HIL so the runtime can obtain exclusive access to the port.

Do not use a production or safety-critical device as this fixture. Opening some serial interfaces can pulse DTR/RTS or reset a target.

## Run the HIL profile

Install the required extras:

```bash
pip install -e '.[dev,serial]'
```

Then run the host-only proof:

```bash
HPA_HIL=1 \
HPA_SERIAL_TARGET_APPROVE=1 \
HPA_SERIAL_TARGET_PORT=/dev/ttyACM0 \
HPA_SERIAL_TARGET_BAUD=115200 \
HPA_SERIAL_TARGET_EXPECT=NULLSQUARE-HIL-READY \
pytest -q -m hil tests/test_hil_smoke.py -k serial_target
```

Replace `/dev/ttyACM0` with the actual discovered device. Windows COM ports are also valid when they are returned by typed discovery.

If a Flipper Zero is attached and `HPA_FLIPPER_PORT` is set, the same HIL selection also runs the additive-provider proof. The serial assessment must continue to route through `host.local` while Flipper remains an independent optional provider.

## Passing result

The profile passes only when real hardware produces the expected banner and the runtime records the bounded capture as evidence for `interface.serial.observe` on `host.local`.

A normal CI pass does not satisfy the physical HIL requirement tracked by issue #67.
