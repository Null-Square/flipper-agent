# Dual-path RP2040 UART HIL fixture

This fixture turns one owned Raspberry Pi Pico/Pico W-class RP2040 board into the deterministic physical target needed for both the host-provider HIL proof in #67 and the adaptive Flipper synthesis proof in #40.

It deliberately has two observation paths that carry the same marker:

```text
                         owned RP2040 Pico

USB CDC console  ------------------------------> host.local serial provider
     emits NULLSQUARE-HIL-READY

GP4 / UART1 TX, 3.3 V ------------------------> prepared Flipper UART RX
     115200 8N1, same marker

GND -------------------------------------------> GND
```

The fixture is a target, not a new Hardware Pentest Agent provider. The Pico is not controlled by the runtime during these proofs.

## Why this fixture exists

Issue #67 needs a real serial target that the host can observe before and after a Flipper is attached. Issue #40 then needs a known UART signal that a newly synthesized Flipper implementation can characterize physically.

Using one deterministic board for both tests makes the comparison meaningful:

```text
same physical fixture
  -> host USB serial proof
  -> add Flipper without changing host route
  -> encounter internal.uart.autodetect gap
  -> synthesize exact FAP
  -> observe known external UART
  -> validate expected 115200 candidate
  -> promote only after execution-backed HIL passes
```

## Required hardware

- an owned Raspberry Pi Pico, Pico W, or compatible RP2040 board with MicroPython support;
- the Flipper Zero under test;
- two female-to-female jumper wires for signal and ground;
- USB cables for the Pico and Flipper;
- optionally, a 3.3 V-compatible logic analyzer or USB-UART receiver for independent fixture verification.

Do not use a production or safety-critical target for this fixture.

## Install the fixture

1. Install a current MicroPython build appropriate for the RP2040 board using the board vendor/MicroPython instructions.
2. Copy `main.py` from this directory to the board filesystem as `main.py`.
3. Reboot the Pico.
4. Record the exact MicroPython version used in the physical test notes/evidence. The fixture contract intentionally names the firmware family rather than pretending every firmware revision has already been verified.

The program emits `NULLSQUARE-HIL-READY` every 100 ms on both paths.

### USB CDC path

The MicroPython console repeatedly prints:

```text
NULLSQUARE-HIL-READY
```

This is the serial target used by `host.local` in issue #67. The USB CDC driver's configured baud value is not the physical UART baud; the HIL environment can continue to use `115200` for the serial API configuration expected by the current test profile.

### External UART path

`UART1` is configured as:

```text
TX       GP4
RX       GP5 (left unconnected for this passive fixture)
baud     115200
data     8 bits
parity   none
stop     1 bit
logic    3.3 V
```

The exact machine-readable fixture contract is in `fixture.json`.

## Electrical setup

For the Flipper-side observation proof, make only these cross-device connections:

```text
Pico GP4 / UART1 TX  -> operator-prepared Flipper UART RX
Pico GND             -> Flipper GND
```

Do **not** connect Pico `VBUS`, `VSYS`, or `3V3` to a Flipper power pin. Both devices should be powered normally over their own USB connections. Do **not** connect Flipper TX to Pico GP5 for this passive fixture.

Before connecting the Flipper, independently confirm that GP4 is a 3.3 V UART signal and that the marker is readable at 115200 8N1. Stop if the observed voltage or wiring differs from the fixture contract.

The generated implementation/work order remains responsible for naming the exact Flipper-side RX resource it will use. This fixture documentation does not bypass that physical setup boundary.

## Proof 1: host-only serial target (#67)

First close any serial terminal that has the Pico USB CDC port open. Then set the HIL variables for the Pico's actual serial device.

PowerShell example:

```powershell
$env:HPA_HIL = "1"
$env:HPA_SERIAL_TARGET_APPROVE = "1"
$env:HPA_SERIAL_TARGET_PORT = "COM4"  # replace with the Pico port
$env:HPA_SERIAL_TARGET_BAUD = "115200"
$env:HPA_SERIAL_TARGET_EXPECT = "NULLSQUARE-HIL-READY"
python -m pytest -q -m hil -s tests/test_hil_smoke.py -k serial_target
```

Run the host-only proof with the Pico connected. Then attach the Flipper, set `HPA_FLIPPER_PORT` to its discovered port, and run the same selection again. The serial assessment must still execute through `host.local`; attaching Flipper must be additive rather than changing the target route.

A passing software/CI test without this board does not satisfy #67.

## Proof 2: adaptive UART implementation (#40)

After the assessment has produced and persisted an `internal.uart.autodetect` implementation candidate, connect GP4/GND as described above and invoke the operator-only execution-backed HIL command:

```text
hardware-pentest-operator implementation-hil-run \
  --implementation-id <exact-implementation-id> \
  --flipper-port <flipper-port> \
  --expected-uart-baud 115200 \
  --min-sample-bytes 32
```

On Windows PowerShell, provide the same arguments on one line or use PowerShell's normal line-continuation syntax.

The HIL runner decides pass/fail. A pass requires all of the following, not just successful FAP exit:

- exact active Flipper/provider binding;
- exact capability and implementation artifact hash;
- current hardware descriptor/firmware/adapter binding;
- result schema version `1` and result status `success`;
- at least 32 captured bytes;
- a valid non-empty UART candidate array;
- a candidate containing the expected `115200` baud with valid framing fields;
- confirmed generated-app and result cleanup with no cleanup errors.

Only after that verification record exists should the implementation be eligible for promotion/reuse.

## The #40 proof is not complete at first promotion

The decisive adaptive-hardware acceptance test must continue after the first physical pass:

1. persist/promote the exact verified implementation;
2. terminate the current process/outer-harness session;
3. start a fresh process;
4. rediscover the promoted implementation from durable storage;
5. refresh/resume the original assessment;
6. run a second compatible assessment and reuse the implementation without generating source again;
7. preserve the original artifact/source/descriptor/verification provenance throughout reuse.

That restart-and-reuse step is what turns a successful generated FAP into verified executable capability memory rather than a one-off demo.
