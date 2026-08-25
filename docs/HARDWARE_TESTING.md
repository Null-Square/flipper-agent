# Hardware testing strategy

Hardware Pentest Agent must not assume that a physical instrument still behaves like a simulator or a previous firmware release. The test strategy therefore separates software correctness from real-hardware readiness.

## Required test layers

### 1. Unit and protocol tests

Run on every commit in normal CI.

Use deterministic serial doubles to cover:

- command framing and prompts;
- partial reads and writes;
- malformed or unexpected output;
- timeouts and disconnects;
- parser behavior;
- policy and capability gating;
- cleanup after bounded operations;
- identity or firmware changes between probe and execution;
- negative-result semantics such as `INCONCLUSIVE`.

These tests must not claim that physical hardware works. They prove that the runtime behaves correctly for known protocol shapes.

### 2. Recorded hardware contracts

A real preflight session can write a sanitized transcript with `--transcript`.

The transcript is local diagnostic evidence. It redacts Flipper hardware UID fields and MAC addresses. Never commit an unreviewed raw hardware transcript.

After a real hardware baseline is accepted:

1. inspect the sanitized transcript;
2. remove unrelated environmental data;
3. retain only protocol output needed for a regression;
4. add the reviewed output under `tests/fixtures/hardware_contracts/`;
5. add or update parser/transport tests that consume that fixture.

This lets ordinary CI retain protocol shapes produced by real hardware without requiring a device on every runner.

Recorded contracts complement hardware-in-the-loop tests. They do not replace them.

### 3. Plug-in preflight

Run before a real assessment whenever the physical stack is connected, changed, reflashed, upgraded, or moved to a new host.

Install hardware support:

```bash
pip install -e '.[flipper]'
```

Run the basic readiness gate:

```bash
hardware-pentest-preflight \
  --transcript .hardware-pentest/transcripts/preflight.json \
  --output .hardware-pentest/preflight/latest.json
```

For deterministic Wi-Fi hardware-in-the-loop validation, use a controlled lab AP:

```bash
hardware-pentest-preflight \
  --expected-lab-ssid NULLSQUARE-HIL-AP \
  --expected-lab-channel 6 \
  --transcript .hardware-pentest/transcripts/preflight.json \
  --output .hardware-pentest/preflight/latest.json
```

If serial discovery is ambiguous, specify ports explicitly:

```bash
hardware-pentest-preflight \
  --flipper-port /dev/ttyACM0 \
  --marauder-port /dev/ttyUSB0 \
  --expected-lab-ssid NULLSQUARE-HIL-AP \
  --expected-lab-channel 6
```

The command exits nonzero when any required check fails.

## Current preflight checks

The Flipper + Marauder MVP checks:

1. Flipper Zero identity handshake;
2. known Flipper firmware version;
3. Marauder companion FAP is installed;
4. FAP file fingerprint is available;
5. exact Marauder FAP loader identity launches;
6. the FAP closes and the loader returns to idle;
7. ESP32 Marauder CLI signature is present;
8. Marauder firmware version is known;
9. passive beacon capture can start and stop cleanly;
10. the resulting AP list is parseable;
11. optionally, a known lab AP is observed on the expected channel;
12. a stable composite hardware/software identity can be constructed.

A missing known lab AP is a failure when an expected SSID is supplied. If no deterministic AP is supplied, command health can pass but RF reception is reported with a warning.

## Composite identity

Do not bind hardware trust to `/dev/ttyACM0`, `/dev/ttyUSB0`, COM numbers, or other volatile host paths.

The Flipper + Marauder composite identity is derived from the exact component state, including:

- Flipper instrument identity and firmware;
- Flipper adapter version;
- Marauder board stable serial identity;
- Marauder firmware;
- Marauder adapter version;
- Marauder companion FAP fingerprint;
- expected FAP version metadata.

A change in any component produces a different composite identity. Existing verification evidence therefore cannot silently carry across a changed hardware/software stack.

If the Marauder board does not expose a stable serial identity, preflight refuses to create composite trust. A volatile serial device path is not accepted as a substitute.

## 4. Hardware-in-the-loop smoke suite

The local NullSquare HIL fixture should become deterministic rather than depending on whatever happens to be nearby.

Initial fixture:

- Flipper Zero;
- ESP32 Wi-Fi Dev Board running a supported Marauder firmware;
- installed Marauder companion FAP;
- one controlled Wi-Fi AP named `NULLSQUARE-HIL-AP` on a fixed channel;
- one known NFC tag;
- one known IR source;
- one safe GPIO digital-level fixture;
- later, a controlled legal Sub-GHz source for the configured region.

Each capability verification should assert an expected observation from the fixture. The absence of random environmental traffic must never be used as the success condition.

### Host-only serial target HIL

The first target-side HIL proof uses a low-cost owned development board that continuously emits a deterministic banner over USB serial. This validates that the host itself can assess a connected target before any external pentest appliance is required.

A ready-to-flash deterministic fixture is provided under `examples/hil/serial_banner/`, with both Arduino-compatible and MicroPython variants. Both emit `NULLSQUARE-HIL-READY` repeatedly; choose whichever matches the owned development board.

Install the test and serial extras:

```bash
pip install -e '.[dev,serial]'
```

Configure a board that repeatedly prints a short known banner such as `NULLSQUARE-HIL-READY`, then run:

```bash
HPA_HIL=1 \
HPA_SERIAL_TARGET_APPROVE=1 \
HPA_SERIAL_TARGET_PORT=/dev/ttyACM0 \
HPA_SERIAL_TARGET_BAUD=115200 \
HPA_SERIAL_TARGET_EXPECT=NULLSQUARE-HIL-READY \
pytest -q -m hil tests/test_hil_smoke.py -k serial_target
```

Optional bounded capture settings are:

```text
HPA_SERIAL_TARGET_DURATION       default 1.0, maximum 5.0 seconds
HPA_SERIAL_TARGET_MAX_BYTES      default 4096, maximum 65536 bytes
```

`HPA_SERIAL_TARGET_APPROVE=1` is a deliberate operator opt-in for the HIL fixture. The test creates one exact temporary approval grant for the serial-observation step only. The production runtime still requires normal operator-controlled gate grants; MCP cannot self-grant approval.

The serial HIL test exercises the full domain path:

```text
real host discovery
  -> target association
  -> interface.serial.inspect
  -> approval-required pause
  -> exact one-shot HIL approval
  -> interface.serial.observe
  -> host.local route
  -> bounded capture
  -> durable evidence assertions
```

It verifies that the selected device is present in real discovery, metadata inspection routes to `host.local`, live observation remains `INTERACT`, execution pauses before approval, captured data contains the known banner, byte/time bounds are respected, and the evidence record is linked to the target/capability/provider.

Opening a USB serial interface may pulse DTR/RTS or reset some targets depending on host driver, USB bridge, bootloader, and board wiring. Use a disposable/owned development fixture and do not run this profile against production hardware without understanding that behavior.

If `HPA_FLIPPER_PORT` is also configured, the same HIL file performs a second complete serial-target assessment while Flipper is present. The serial TestCases must still route to `host.local`; Flipper augments the available provider set rather than replacing the host route.

Normal CI runs `pytest -m 'not hil'`, so none of these tests opens physical hardware on hosted runners.

## 5. Dedicated HIL runner

After the local fixture proves stable, connect it to a dedicated private self-hosted CI runner.

Recommended labels:

```text
self-hosted
nullsquare-hil
flipper-zero
marauder
```

Do not make normal pull requests wait indefinitely for hardware that is not online. Keep software CI mandatory and make HIL a separate release/hardware-sensitive-change gate until the lab runner is reliably available.

The HIL machine should run only trusted repository revisions and should not be exposed to untrusted fork pull requests.

## Readiness versus capability verification

Preflight and capability verification answer different questions.

**Preflight:** Is this connected stack healthy and compatible enough to begin work?

**Capability verification:** Has a specific assessment capability been proven against a known physical reference and recorded as evidence for this exact instrument state?

A preflight success does not automatically grant every implemented capability. Production capability discovery still uses the verification store.

## Release rule

A hardware-facing release must not be tagged as verified only because normal CI is green.

For an MVP hardware release require:

1. normal CI green;
2. preflight PASS on the supported real stack;
3. deterministic HIL reference observations PASS;
4. current capability-verification records PASS;
5. sanitized protocol contracts reviewed and updated when protocol output changed;
6. one end-to-end assessment produces intact evidence and a report from the real hardware stack.
