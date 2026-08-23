# Architecture

## Decision

Hardware Pentest Agent is a harness-neutral, vendor-neutral runtime for authorized hardware and embedded security assessments.

Its core job is not to expose device commands. Its job is to translate a security question into a reproducible physical experiment using the best available hardware implementation.

Flipper Zero is the first reference hardware provider. It must not define the core API.

## Architectural principle

```text
security question
      |
      v
capability need
      |
      +--> verified implementation exists -> reuse
      |
      +--> primitives can compose it ------> compose
      |
      +--> mature specialist tool exists --> route
      |
      +--> implementation missing ---------> synthesize
                                                |
                                                v
                                      choose hardware provider
                                                |
                                      build / deploy / execute
                                                |
                                                v
                                             evidence
```

The product should therefore own **domain intelligence and physical execution state**, while borrowing generic LLM orchestration from Codex, Null-AI or another outer harness when convenient.

## Goals

The architecture must support these behaviors:

- represent engagement, target and target components explicitly;
- discover connected hardware providers and physical resources;
- select applicable hardware/embedded tests;
- resolve a capability need to a verified implementation;
- compose lower-level primitives where useful;
- synthesize a new implementation when no route exists;
- choose a board/tool based on physical, timing and toolchain requirements;
- build and deploy board-specific artifacts without leaking toolchain details into assessment logic;
- validate scope, action risk and physical constraints before execution;
- persist target, assessment, implementation and evidence state independently of model context;
- expose the same domain through Python, CLI and MCP;
- add new boards/tools without changing TestCase semantics.

## Non-goals

The core runtime must not:

- become a generic LLM agent harness;
- make MCP the internal architecture;
- encode vendor command syntax in assessment logic;
- require every capability to be hard-coded in advance;
- generate firmware when a verified/composed/external implementation already fits;
- treat compilation success as proof that a physical capability works;
- infer authorization from a prompt;
- treat every anomaly as a finding.

## System layers

```text
+--------------------------------------------------------------+
|                     Outer Agent Harness                      |
| Codex / Null-AI / other MCP client                           |
| model inference | conversation | generic tool loop           |
+-----------------------------+--------------------------------+
                              |
                              v
+--------------------------------------------------------------+
|                Harness-Neutral Service Boundary              |
| Python service | CLI | MCP                                   |
+-----------------------------+--------------------------------+
                              |
                              v
+--------------------------------------------------------------+
|                    Assessment Runtime                        |
| engagement | target/component graph | TestCases | state      |
+-----------------------------+--------------------------------+
                              |
                              v
+--------------------------------------------------------------+
|                  Capability Resolution                       |
| registry | graph | reuse | compose | synthesize | routing     |
+-----------------------------+--------------------------------+
                              |
            +-----------------+------------------+
            |                                    |
            v                                    v
+--------------------------+        +---------------------------+
| Policy / Physical Gates  |        | Evidence / Verification   |
| scope | action class     |        | artifacts | hashes        |
| operator state           |        | observations | findings   |
+------------+-------------+        +-------------+-------------+
             |                                      ^
             +-------------------+------------------+
                                 |
                                 v
+--------------------------------------------------------------+
|              Hardware / Implementation Runtime               |
| descriptors | adapters | synthesis | build | deploy          |
+-----------------------------+--------------------------------+
                              |
      +-----------------------+-----------------------------+
      |                       |                             |
      v                       v                             v
 Flipper provider       programmable boards         specialist tools
 FAP / RPC / CLI        ESP32/RP2040/STM32          Proxmark/sigrok/
                                                     OpenOCD/SDR/...
```

## Core domain objects

### Engagement

Defines the authorized technical assessment context: targets, time window, capability policy, action-class ceiling and operator requirements.

### Target

The system being assessed. A target may be a camera, drone, router, lock, vehicle controller, board or larger embedded product.

### TargetComponent

A logical/physical part discovered within a target, such as:

- flight controller;
- radio module;
- SPI flash;
- debug header;
- Wi-Fi subsystem;
- companion computer;
- removable storage.

The component graph should evolve as evidence is collected.

### HardwareProvider

A controllable physical resource available to the runtime.

Examples:

- Flipper Zero;
- ESP32/RP2040/STM32 development boards;
- Proxmark3;
- logic analyzers;
- debug probes;
- SDRs;
- Linux SBCs.

A provider may expose prebuilt capabilities, programmable resources, or both.

### HardwareDescriptor

A normalized description of what a provider can physically and computationally do.

It should eventually cover:

- identity/revision/architecture;
- GPIO/electrical domain;
- buses and radios;
- timers/ADC/DAC/DMA/PIO where relevant;
- debug/programming interfaces;
- installed runtime/firmware state;
- build toolchains;
- artifact types;
- deployment/recovery methods;
- evidence channels;
- verified limitations.

See `PROGRAMMABLE_HARDWARE.md`.

### Capability

A stable, vendor-neutral physical/security operation.

Examples:

- `wireless.nfc.identify`;
- `internal.uart.observe`;
- `internal.uart.autodetect`;
- `internal.spi.capture`;
- `debug.swd.detect`;
- `firmware.extract`;
- `protocol.decode`.

A capability is not synonymous with a device API call.

### CapabilityImplementation

A concrete way to satisfy a capability on one or more compatible providers.

An implementation can be:

- built into an adapter;
- composed from primitives;
- delegated to an external specialist tool;
- generated host software;
- synthesized firmware/app.

It should carry compatibility, provenance, maturity, evidence schema and limitations.

### CapabilitySynthesisRequest

A hardware-neutral request to create a missing implementation. It should specify physical requirements and expected evidence before a toolchain/backend is chosen.

### TestCase

A security question with purpose, prerequisites, required capability, evidence expectations, stop conditions and result interpretation rules.

### Action

A concrete execution request derived from a TestCase and capability implementation.

### Evidence / Observation / Finding

Evidence is the raw or normalized physical result. An Observation is directly supported by evidence. A Finding is a security conclusion supported by observations/evidence.

## Target and provider roles

A device can be a target, provider, or both, but those roles must remain explicit.

Example: an RP2040 board connected as a logic/timing helper is a provider. An RP2040 board being assessed is a target. If an authorized debug/bootloader path allows a temporary diagnostic payload on the target, the runtime may model it as a target-provider hybrid for that bounded operation.

Control of a target does not automatically grant provider status.

## Capability resolution

Resolution should occur in this order:

1. Find verified implementations for the required capability.
2. Check whether verified lower-level primitives can compose it.
3. Check whether an external specialist provider is available.
4. Consider host-side generation.
5. Consider firmware/app synthesis on compatible providers.
6. If no provider can satisfy the physical requirements, return a hardware requirement instead of inventing an implementation.

Ranking can later include:

- evidence fidelity;
- timing/bandwidth fit;
- hardware verification confidence;
- setup cost;
- destructive risk;
- runtime duration;
- operator effort.

## Provider contract

Existing adapters implement a stable execution contract. The architecture should extend that with provider/descriptor discovery rather than replace it.

Conceptually:

```python
class HardwareProvider(Protocol):
    def probe(self) -> HardwareIdentity: ...
    def describe(self) -> HardwareDescriptor: ...
    def implementations(self) -> list[CapabilityImplementation]: ...
```

Existing `InstrumentAdapter` execution contracts remain useful for already-implemented capabilities.

## Synthesis backend contracts

Synthesis should be split into reusable contracts:

```text
CapabilitySynthesisRequest
        |
        v
SynthesisResolver
        |
        v
CapabilitySynthesisBackend
        |
        +--> BuildProvider
        +--> DeploymentProvider
        +--> EvidenceChannel
```

Examples:

- Flipper -> FAP / uFBT -> storage/loader or RPC;
- ESP32 -> ESP-IDF/PlatformIO -> esptool;
- RP2040 -> Pico SDK/PIO -> UF2;
- STM32 -> STM32/Zephyr -> DFU/OpenOCD;
- logic analysis -> generated sigrok decoder;
- Linux SBC -> bounded process/container.

Assessment code must never construct those vendor-specific commands directly.

## Flipper reference provider

Flipper remains provider #1 and currently demonstrates:

- physical discovery/identity;
- typed CLI operations;
- native IR/Sub-GHz/NFC/GPIO capabilities;
- external app transfer/loader lifecycle;
- ESP32 Marauder composite operation;
- generated FAP review/build/deploy/execute/evidence;
- hardware verification and transcript replay.

Structured Flipper protobuf RPC should be added where it improves reliability or transport flexibility, but RPC remains an implementation detail below the capability layer.

## Executable capability memory

A synthesized implementation that is validated on hardware should be persistable and rediscoverable.

Store at least:

```text
capability ID
synthesis request
source/artifact hashes
compatible hardware descriptor constraints
toolchain/version constraints
evidence schema
known limitations
HIL verification records
assessment usage history
```

This makes the runtime's competence cumulative across model sessions and outer harnesses.

## Assessment state machine

Persistent assessment state remains independent of LLM memory.

```text
PLANNED
  |
  +--> capability available ----------------------> READY
  |
  +--> capability missing but synthesizable ------> SYNTHESIS_REQUIRED
  |                                                    |
  |                                              implementation
  |                                                    |
  +----------------------------------------------------+
  |
  +--> HUMAN_ACTION_REQUIRED
  +--> APPROVAL_REQUIRED
  |
  v
RUNNING
  |
  +--> BLOCKED
  +--> INCONCLUSIVE
  +--> FAILED
  +--> SUCCESS
```

`SYNTHESIS_REQUIRED` is a planned architectural state; current planning still needs this integration.

## Human/physical actions

Hardware work often requires enclosure opening, ground identification, voltage measurement, probe placement, boot-mode changes or cable movement. These are durable domain states, not conversational reminders.

## Evidence architecture

Each physical experiment should link:

```text
Engagement
 -> Target / TargetComponent
 -> TestCase
 -> Capability
 -> CapabilityImplementation
 -> HardwareProvider + descriptor snapshot
 -> Build/deployment provenance where applicable
 -> Action
 -> Raw artifact/output
 -> Observation
 -> Finding only if supported
```

## Harness boundary

Outer harnesses may:

- reason over assessment context;
- choose among candidate tests;
- propose hypotheses;
- ask for capability synthesis;
- generate implementation source when invited by the synthesis backend;
- interpret observations and propose follow-up work.

The runtime owns:

- target/component state;
- hardware descriptors and implementation registry;
- methodology/TestCases;
- synthesis/build/deployment provenance;
- physical execution state;
- evidence and verification;
- resumable assessment state.

This lets Codex remain useful indefinitely without making Codex itself part of the product architecture.

## MCP boundary

MCP exposes high-level domain operations. It should evolve around concepts such as:

```text
hardware.discover
hardware.describe
capability.search
capability.implementations
assessment.create
assessment.context
assessment.candidates
assessment.execute_next
synthesis.propose
synthesis.status
evidence.get
```

The MCP tool list should not grow into a mirror of every vendor command.

## Definition of architectural success

The architecture is successful when all of the following are true:

1. The same security TestCase can route to different hardware providers without changing assessment logic.
2. A missing physical capability can be synthesized for a compatible provider and returned as normal evidence.
3. A later assessment can reuse the verified synthesized implementation.
4. A complex target such as a camera or drone can be represented as components and assessed across multiple providers.
5. Codex, Null-AI or another outer harness can drive the same durable domain without changing hardware semantics.

The most important proof is therefore not the number of predefined Flipper tools. It is a successful real assessment where the agent encounters a capability gap, creates the missing physical implementation, validates it, and continues.
