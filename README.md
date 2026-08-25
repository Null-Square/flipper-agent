<div align="center">

# Hardware Pentest Agent

**Agent-native hardware and embedded security testing.**

A hardware-security runtime that assesses physical targets with whatever compatible capabilities are currently available, from the host computer itself to connected Flipper Zero, debug probes, logic analyzers, programmable boards, SDRs, and other lab instruments.

![Status](https://img.shields.io/badge/status-foundation-FED900)
![Use](https://img.shields.io/badge/use-authorized%20only-000000)
![By NullSquare](https://img.shields.io/badge/by-NullSquare-FED900)

</div>

> **Product name:** `hardware-pentest-agent`  
> **Current GitHub repository slug:** `flipper-agent` (legacy name; rename to `hardware-pentest-agent` when repository administration allows it).

## Mission

Hardware Pentest Agent is the **pentester**. Hardware devices are either targets being assessed or providers that extend what the pentester can physically observe or do.

The product is not a Flipper command wrapper, not a fixed catalog of hardware tools, and not a generic LLM harness.

Its job is to:

1. understand an authorized hardware/embedded target and its components;
2. build and refine a model of the target's physical and embedded attack surface;
3. understand which capabilities are available from the host environment and connected instruments;
4. select applicable tests based on the target, current evidence, scope, and available capabilities;
5. resolve each required capability to the best compatible implementation;
6. reuse an existing implementation, compose primitives, use a specialist tool, or synthesize a bounded implementation when appropriate;
7. execute through typed, policy-controlled provider boundaries;
8. collect reproducible evidence and update the assessment state;
9. explain when a test cannot be performed and what additional hardware or setup would unlock it.

```text
                         Hardware Pentest Agent
                                  |
                    assessment / target model
                                  |
                         security question
                                  |
                         capability need
                                  |
              +-------------------+-------------------+
              |                   |                   |
            reuse               compose            synthesize
              |                   |                   |
              +-------------------+-------------------+
                                  |
                         capability resolver
                                  |
              +-------------------+----------------------------+
              |                   |                            |
          Host provider      External providers          Specialist tools
          provider #0        Flipper / RP2040 /          probes / analyzers /
          local tools        ESP32 / SBC / ...           Proxmark / SDR / ...
              |                   |                            |
              +-------------------+----------------------------+
                                  |
                             physical world
```

## Three concepts must never be mixed

### 1. Target

The system being assessed.

Examples:

- drone;
- camera;
- router;
- smart lock;
- vehicle controller;
- unknown PCB;
- development board under test;
- industrial or IoT device.

A target can contain many `TargetComponent` objects such as a flight controller, SPI flash, debug header, Wi-Fi module, storage device, radio subsystem, or companion computer.

### 2. Provider

A controllable resource the runtime can use during the assessment.

Examples:

- the host computer running the local runtime;
- Flipper Zero;
- USB serial/debug resources;
- RP2040/ESP32/STM32 boards;
- CMSIS-DAP/ST-Link/J-Link class probes;
- logic analyzers;
- Proxmark3;
- SDR hardware;
- Linux SBCs;
- future side-channel/fault-injection equipment.

A provider does not define the mission. It only contributes capabilities.

### 3. Capability

A stable, vendor-neutral operation required by an assessment.

Examples:

```text
artifact.firmware.inspect
interface.usb.enumerate
internal.uart.observe
internal.uart.autodetect
internal.spi.capture
internal.i2c.capture
debug.jtag.detect
debug.swd.detect
memory.acquire
firmware.extract
protocol.decode
wireless.nfc.identify
wireless.subghz.observe
```

Assessment logic asks for a capability. It should not ask for a Flipper command, OpenOCD command, pyserial script, or vendor API call.

## Provider #0: the host computer

The agent should remain useful when no external security hardware is connected.

The local host is therefore the baseline provider. Depending on the environment and authorization, it may expose bounded implementations for capabilities through resources such as:

- USB discovery and enumeration;
- serial interfaces;
- network interfaces;
- firmware/artifact inspection tools;
- debuggers and reverse-engineering tools;
- OpenOCD/GDB-compatible workflows when supported hardware is present;
- flashing/bootloader utilities;
- filesystem and evidence processing;
- build toolchains;
- emulation or analysis packages.

This does **not** mean exposing an unrestricted shell to an outer model. Host capabilities remain typed, scoped, policy-controlled, evidence-producing operations behind the same runtime contracts as physical providers.

Baseline rule:

```text
no external provider connected
        -> use compatible host capabilities

Flipper connected
        -> host capabilities + Flipper capabilities

debug probe connected
        -> previous capabilities + debug capabilities

logic analyzer connected
        -> previous capabilities + high-fidelity capture capabilities
```

The available capability set changes. The pentesting mission does not.

## Capability applicability is target-dependent

Not every capability applies to every assessment.

For a drone, the target model may include:

```text
drone
  +-- flight controller
  +-- RF link
  +-- GNSS
  +-- ESC/CAN/UART buses
  +-- storage
  +-- camera
  +-- companion computer
  +-- debug/programming interfaces
```

The runtime may find that:

- the host can inspect firmware and USB/network surfaces;
- Flipper contributes useful Sub-GHz, NFC, IR, GPIO, or other physical capabilities where relevant;
- a debug probe contributes SWD/JTAG capabilities;
- a logic analyzer contributes higher-fidelity bus capture;
- an SDR contributes RF capabilities;
- some connected providers are irrelevant to this target and are not selected.

The system must prefer **applicable capability resolution**, not maximum tool usage.

## Hardware descriptors

Each provider should expose a normalized `HardwareDescriptor` describing what it can physically and computationally provide.

Descriptor areas include:

- stable identity and revision;
- architecture / MCU / SoC family where relevant;
- GPIO and electrical domain;
- UART/SPI/I2C/CAN and other buses;
- Wi-Fi/BLE/NFC/Sub-GHz/SDR resources;
- USB roles;
- timers/ADC/DAC/DMA/PIO where relevant;
- debug/programming interfaces;
- installed runtime/firmware state;
- supported toolchains;
- supported artifact types;
- deployment/recovery methods;
- evidence channels;
- verified limitations.

A descriptor describes **what a provider can supply**. It does not decide what the assessment should do.

See [`docs/PROGRAMMABLE_HARDWARE.md`](docs/PROGRAMMABLE_HARDWARE.md).

## Capability resolution

When a test requires a capability, resolve it in this order:

1. reuse an existing verified implementation;
2. compose verified lower-level primitives;
3. route to a mature specialist provider/tool;
4. generate bounded host-side software if appropriate;
5. synthesize a provider-specific app/firmware implementation;
6. return a capability/setup gap when the available providers cannot satisfy the physical requirements.

The last outcome is important. A hardware pentester must be able to say **"this test is not currently possible"** rather than inventing capability.

Example:

```text
need: internal.uart.observe
required electrical domain: 1.8 V
available providers:
  host serial path: no compatible interface
  Flipper: incompatible electrical setup

result:
  blocked capability
  -> request appropriate level shifting / compatible provider
```

## Physical safety is part of the domain

Low-level hardware operations can damage targets or instruments if electrical constraints are treated like software parameters.

Before active interaction, the runtime should be able to represent and verify relevant facts such as:

- voltage domain;
- ground/reference state;
- signal direction;
- powered/unpowered target state;
- contention risk;
- pull-up/pull-down expectations;
- bus ownership;
- reset/recovery method;
- operator probe/cable placement.

Physical setup and approval are durable assessment state, not conversational reminders.

Initial action classes are:

- `OBSERVE`;
- `INTERACT`;
- `TRANSMIT`;
- `MODIFY`;
- `EMULATE`;
- `DESTRUCTIVE`.

The language model is not the enforcement boundary.

## Flipper Zero: first external reference provider

Flipper remains valuable because it combines multiple physical interfaces with a practical external-app model.

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

Flipper is provider #1, not the architecture.

## Programmable capability creation

A key long-term differentiator is handling capability gaps.

Example:

```text
unknown authorized PCB
   |
likely UART header
   |
need: internal.uart.autodetect
   |
no exact implementation exists
   |
inspect compatible providers
   |
choose provider based on electrical/timing/toolchain fit
   |
create bounded implementation
   |
build -> deploy -> execute -> evidence
   |
HIL verify
   |
persist implementation
   |
resume assessment
```

A synthesized implementation that succeeds on real hardware can later become executable capability memory with:

- capability ID;
- source/artifact hashes;
- compatible hardware descriptors;
- toolchain constraints;
- evidence schema;
- known limitations;
- HIL verification records;
- assessment usage history.

The system grows its hardware competence through verified implementations, not model conversation memory.

## Harness-neutral by design

Hardware Pentest Agent owns the hardware-pentesting domain, not the generic model loop.

Codex, Null-AI, another MCP-capable harness, or a future hosted agent can sit outside the runtime:

```text
outer agent harness
      |
      | reasoning / conversation / generic tool loop
      v
Hardware Pentest Agent
      |
      +-- durable engagement + target/component state
      +-- methodology / TestCases
      +-- provider descriptors
      +-- capability graph + implementations
      +-- physical/operator gates
      +-- build + deployment provenance
      +-- evidence / observations / findings
      |
      v
host + connected physical providers
```

Changing the outer harness must not change pentest state, hardware semantics, policy, or evidence.

See [`docs/HARNESS_INTEGRATION.md`](docs/HARNESS_INTEGRATION.md).

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

The MCP surface exposes assessment/domain operations rather than generic shell, serial, or vendor-command passthrough.

## Testing

Use the named profiles:

```bash
python scripts/test_harness.py quick
python scripts/test_harness.py contract
python scripts/test_harness.py ci
```

Real hardware HIL is explicit and opt-in. Sanitized real-device transcripts can be replayed through production transports in normal CI, but replay never creates real hardware-verification state.

See [`docs/HARDWARE_TESTING.md`](docs/HARDWARE_TESTING.md).

## Near-term direction

The next work is deliberately narrow:

1. lock the target/provider/capability boundaries;
2. model the host computer as provider #0;
3. complete real Flipper provider certification;
4. prove that adding/removing Flipper changes available capabilities without changing assessment semantics;
5. prove one capability can route through materially different providers;
6. prove one real capability gap can be represented and, where appropriate, satisfied by a bounded synthesized implementation;
7. only then expand to additional provider classes and complex targets.

The roadmap is organized around architecture proofs, not a shopping list of integrations.

See [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Responsible use

This project is for authorized security testing and research only. Use it only on hardware and systems you own or are explicitly authorized to assess.

## Current status

**Phase:** strong Flipper-first implementation and generic hardware-domain foundation; next focus is host-provider baseline, real HIL certification, and provider-independence proof.

The repository is not yet a production autonomous hardware pentesting system.

---

<div align="center">
<sub>A <b><a href="https://nullsquare.net">NullSquare</a></b> project.</sub>
</div>
