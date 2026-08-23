<div align="center">

# Hardware Pentest Agent

**Agent-native hardware and embedded security testing.**

Turn connected boards, probes, radios, debuggers and other physical computing resources into programmable pentesting instruments that any outer agent harness can use.

![Status](https://img.shields.io/badge/status-Flipper--first%20MVP-FED900)
![Use](https://img.shields.io/badge/use-authorized%20only-000000)
![By NullSquare](https://img.shields.io/badge/by-NullSquare-FED900)

</div>

> **Current repository name:** `flipper-agent`. The product is `hardware-pentest-agent`. Flipper Zero is the first reference hardware provider, not the architecture.

## Product thesis

Hardware Pentest Agent is not a Flipper command wrapper and it is not a fixed catalog of hardware tools.

The long-term goal is a **hardware-native pentesting runtime** that lets an AI pentester:

1. understand the target and its physical/embedded attack surface;
2. understand what connected hardware can physically do;
3. reuse an existing capability when one fits;
4. compose lower-level primitives when possible;
5. synthesize a new app, firmware helper, decoder or host tool when the required capability does not exist;
6. deploy and operate that implementation on an appropriate board/tool;
7. capture reproducible evidence and continue the assessment.

```text
Codex / Null-AI / another agent harness
                  |
             MCP / CLI / Python
                  |
                  v
        Hardware Pentest Agent
                  |
       assessment / methodology
                  |
             capability need
                  |
       +----------+----------+
       |          |          |
     reuse      compose    synthesize
       |          |          |
       +----------+----------+
                  |
          hardware resolver
                  |
   +--------------+--------------+----------------+
   |              |              |                |
 Flipper        ESP32          RP2040       specialist tools
   FAP          ESP-IDF        Pico SDK     / probes / SDR
   |              |              |                |
   +--------------+--------------+----------------+
                  |
             physical world
```

A camera, drone, router, lock, controller or unknown PCB can be the **target**. Flipper Zero, ESP32/RP2040/STM32 boards, Proxmark3, logic analyzers, debug probes, SDRs or Linux SBCs can be **hardware providers** used to investigate it. A development board may sometimes be both, but those roles remain explicit.

See [`docs/PROGRAMMABLE_HARDWARE.md`](docs/PROGRAMMABLE_HARDWARE.md).

## Harness-neutral by design

Hardware Pentest Agent owns the **hardware-pentesting domain**, not the generic LLM loop.

Codex, Null-AI, another MCP-capable harness, or a future hosted agent can sit outside the runtime:

```text
outer agent harness
      |
      | reasoning / conversation / generic tool loop
      v
Hardware Pentest Agent
      |
      +-- durable target + assessment state
      +-- methodology / TestCases
      +-- capability graph / implementations
      +-- hardware descriptors
      +-- build + deployment provenance
      +-- physical preflight / HIL verification
      +-- evidence / observations / findings
      |
      v
physical hardware
```

Changing the outer harness must not change the pentest state, hardware semantics or evidence model.

See [`docs/HARNESS_INTEGRATION.md`](docs/HARNESS_INTEGRATION.md).

## Core abstraction: capability need, not device command

The agent reasons about capabilities such as:

```text
wireless.nfc.identify
wireless.subghz.observe
internal.uart.observe
internal.uart.autodetect
internal.spi.capture
internal.i2c.capture
debug.jtag.detect
debug.swd.detect
memory.acquire
firmware.extract
protocol.decode
```

A capability may be satisfied by:

- a verified built-in adapter operation;
- a composition of lower-level verified primitives;
- a mature external tool;
- generated host-side software;
- a synthesized board-specific app/firmware artifact.

The runtime should choose the most appropriate implementation for the available hardware rather than making the assessment logic know Flipper, ESP-IDF, OpenOCD or vendor command syntax.

## Programmable hardware providers

The roadmap introduces a normalized `HardwareDescriptor` describing what a board/tool can provide:

- MCU/SoC architecture;
- GPIO and voltage domain;
- UART/SPI/I2C/CAN and other buses;
- Wi-Fi/BLE/NFC/Sub-GHz/radio resources;
- USB roles;
- ADC/DAC/timers/PIO/DMA where relevant;
- debug/programming interfaces;
- toolchains and artifact types;
- deployment/recovery methods;
- evidence channels and verified limitations.

This lets capability synthesis become hardware-neutral:

```text
CapabilitySynthesisRequest
        |
        +-- Flipper backend -> FAP / uFBT
        +-- ESP32 backend   -> ESP-IDF / PlatformIO
        +-- RP2040 backend  -> Pico SDK / PIO
        +-- STM32 backend   -> STM32/Zephyr/OpenOCD path
        +-- Linux backend   -> bounded native/container tool
```

The current generated-FAP system is the first implementation of this larger synthesis architecture.

## Flipper-first reference MVP

Flipper Zero remains the first proof because it combines multiple physical interfaces with a practical external-app model.

The current implementation includes:

- USB discovery and typed Flipper operations;
- passive IR, Sub-GHz, NFC and prepared GPIO capabilities;
- ESP32 Marauder passive Wi-Fi and approved network-assessment capabilities;
- composite Flipper + Marauder preflight;
- hardware-verification records;
- persistent assessment runtime and evidence;
- generated FAP review/build/deploy/execute/evidence pipeline;
- fault injection, transcript replay and opt-in HIL test profiles;
- harness-neutral Python service and MCP interface;
- deterministic candidate-test planning independent of model conversation state.

The critical next physical proof is not merely “more Flipper commands.” It is:

> Encounter a hardware capability gap during an assessment, synthesize the missing capability for an available provider, validate it on real hardware, store the implementation, and resume the assessment.

## Example: unknown camera board

```text
Camera target
   |
   +-- Wi-Fi visible
   +-- unknown 4-pin header
   +-- external SPI flash
   |
agent hypothesis: header may be UART
   |
need: internal.uart.autodetect
   |
no existing exact implementation
   |
HardwareDescriptor says Flipper can provide UART/GPIO + FAP toolchain
   |
generate bounded FAP
   |
build -> deploy -> capture -> evidence
   |
identified UART configuration
   |
continue assessment
```

The same methodology should later work if the better provider is RP2040, ESP32, a logic analyzer or a debug probe.

## Example: drone

A drone can contain multiple target components: flight controller, radio link, GNSS, ESC buses, storage, camera, companion computer and debug interfaces. Hardware Pentest Agent should model those components under one assessment and route each physical question to the best available provider without becoming a drone-specific agent.

## Safety and reproducibility

The language model is not the enforcement boundary. Physical operations remain typed, scoped and evidence-producing. Human setup/approval is represented explicitly, and real capabilities do not become `hardware_verified` from mocks or transcript replay.

Initial action classes are:

- `OBSERVE`;
- `INTERACT`;
- `TRANSMIT`;
- `MODIFY`;
- `EMULATE`;
- `DESTRUCTIVE`.

The programmable-hardware direction does not mean exposing unrestricted shell/serial/firmware execution. Synthesis is an implementation mechanism behind the same assessment/runtime contracts.

## Evidence and executable capability memory

Every executed step links engagement, target, TestCase, capability, hardware provider, implementation/artifact version, normalized inputs, raw evidence, hashes, observation and limitations.

A synthesized implementation that succeeds in HIL can later become a reusable route with:

- capability ID;
- source/artifact hashes;
- compatible hardware descriptors;
- toolchain constraints;
- evidence schema;
- known limitations;
- verification records.

The system grows its hardware competence through **verified executable capability memory**, not by relying on an LLM to remember old conversations.

## Interfaces

MCP is an interface, not the architecture.

Supported integration direction:

```text
Codex local                -> MCP stdio
Human / CI                 -> CLI
Null-AI                    -> Python service or MCP
Other local harness        -> MCP stdio / local HTTP
Hosted/online harness      -> authenticated gateway/tunnel -> local runtime
```

Install MCP support:

```bash
pip install -e ".[mcp]"
```

Run local MCP:

```bash
hardware-pentest-mcp
```

Enable high-level assessment creation/execution explicitly:

```bash
hardware-pentest-mcp --allow-execution
```

The MCP surface exposes assessment/domain operations rather than generic serial or device-command passthrough.

## Testing

Use the named profiles:

```bash
python scripts/test_harness.py quick
python scripts/test_harness.py contract
python scripts/test_harness.py ci
```

Real hardware HIL is explicit and opt-in. Sanitized real-device transcripts can be replayed through production transports in normal CI, but replay never creates real hardware-verification state.

See [`docs/HARDWARE_TESTING.md`](docs/HARDWARE_TESTING.md).

## Repository direction

```text
src/hardware_pentest/
  core/          target, capability, engagement and hardware-domain contracts
  assessment/    methodology, planning and persistent state
  runtime/       routing and execution
  service/       harness-neutral Python boundary
  policy/        scope and physical/action constraints
  evidence/      artifacts, provenance, observations and findings
  adapters/      existing hardware/tool implementations
  synthesis/     capability-generation pipeline; Flipper backend is first
  interfaces/    CLI and MCP
  reporting/     evidence-linked output

docs/
  PROGRAMMABLE_HARDWARE.md
  ARCHITECTURE.md
  CAPABILITY_SYNTHESIS.md
  HARNESS_INTEGRATION.md
  HARDWARE_TESTING.md
  ROADMAP.md
  MVP.md
```

## Roadmap summary

1. Flipper-first capability/runtime foundation. **Implemented in software; HIL coverage expanding.**
2. Harness-neutral Python/MCP planning and execution. **Implemented.**
3. Real Flipper + Marauder certification and replay corpus. **Next physical milestone.**
4. Introduce `HardwareDescriptor`, hardware-provider and synthesis-backend contracts.
5. Refactor generated FAPs as the first generic synthesis backend.
6. Persist/promote synthesized capability implementations after HIL.
7. Add a materially different programmable provider (RP2040/ESP32 or debug/capture provider).
8. Prove capability-gap -> synthesis -> deployment -> evidence -> resume on real hardware.
9. Expand to multi-component targets such as cameras, drones, routers and controllers.
10. Build multi-provider assessments and integrate broadly with external agent harnesses.

See [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Reference methodology

Initial design references include:

- [OWASP IoT Security Testing Guide](https://owasp.org/owasp-istg/)
- [Flipper Zero CLI documentation](https://docs.flipper.net/zero/development/cli)
- [Flipper Zero protobuf definitions](https://github.com/flipperdevices/flipperzero-protobuf)
- [NIST IR 8259 Rev. 1](https://csrc.nist.gov/pubs/ir/8259/r1/final)

The project remains responsible for its own implementation and hardware validation.

## Responsible use

This project is for authorized security testing and research only. Use it only on hardware and systems you own or are explicitly authorized to assess.

## Current status

**Phase:** Flipper-first reference provider + harness-neutral runtime, moving into generic programmable-hardware abstraction and real-HIL proof.

The repository is not yet a production pentesting system.

---

<div align="center">
<sub>A <b><a href="https://nullsquare.net">NullSquare</a></b> project.</sub>
</div>
