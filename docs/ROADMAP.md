# Roadmap

## North star

Build a hardware-native pentesting runtime that can assess an authorized embedded/IoT target with **whatever compatible capabilities are currently available**.

The agent is the pentester. The host computer and connected instruments are providers. The target is the system being assessed.

The runtime should be able to:

```text
understand target/component graph
  -> choose security question / TestCase
  -> determine required capability
  -> inspect available providers
  -> resolve implementation
       reuse / compose / specialist / synthesize
  -> satisfy physical/operator gates
  -> execute
  -> collect evidence
  -> update target understanding
  -> continue assessment
```

The roadmap is organized around **proofs of architecture and assessment behavior**, not around accumulating device integrations.

A new provider is valuable only when it proves a missing architectural property or materially expands a real assessment.

---

## Product invariants

These rules apply to every phase.

### Target and provider are separate roles

A drone, camera, router, controller, lock, unknown PCB, or development board under test is a target.

The host computer, Flipper Zero, debug probe, logic analyzer, programmable board, SDR, Proxmark3, or other controllable instrument is a provider.

A physical device can be both only when the roles are explicitly authorized and modeled separately.

### Capability semantics are vendor-neutral

Assessment logic asks for capabilities such as:

```text
artifact.firmware.inspect
interface.usb.enumerate
internal.uart.observe
internal.spi.capture
debug.swd.detect
firmware.extract
protocol.decode
wireless.nfc.identify
```

It does not ask for vendor commands.

### Capability availability is dynamic

```text
host only
  -> baseline capabilities

+ Flipper
  -> baseline + Flipper capabilities

+ debug probe
  -> previous + debug capabilities

+ logic analyzer
  -> previous + capture capabilities
```

Adding or removing a provider changes what the agent can do, not what the agent is.

### Inapplicable providers are ignored

The system should not use a connected tool simply because it exists. Provider selection must be justified by the target, TestCase, physical requirements, evidence quality, risk, and operator state.

### Missing capability is a valid result

If no available provider can satisfy a physical requirement, return a capability/setup gap. Do not create a raw-command escape hatch or hallucinate capability.

### Physical constraints are first-class

Electrical domain, signal direction, target power state, bus ownership, contention risk, recovery path, probe placement, and operator action can block execution even when a software implementation exists.

### Evidence survives the model session

Assessment state, provider state, implementation provenance, evidence, observations, and findings remain durable and independent of outer-agent conversation memory.

---

# Phase 0 — Existing foundation

**Status:** substantially implemented in software; physical verification still incomplete in important areas.

This phase established:

- engagement, target, component, capability, action, evidence, observation, and finding models;
- deterministic policy/action gates;
- capability registry and adapter contracts;
- simulator and transcript replay;
- persistent assessment state;
- TestCase catalog and deterministic candidate planning;
- harness-neutral Python service;
- MCP/CLI surfaces;
- Flipper transport and typed operations;
- Flipper/Marauder capability families;
- generated FAP build/deploy/evidence pipeline;
- `HardwareDescriptor` domain foundation;
- provider registry and Flipper provider implementation;
- synthesis contracts, routing, HIL records, and promotion model.

Acceptance already achieved in software:

- assessment logic does not need Flipper command strings;
- policy is below the model layer;
- simulator and real adapters share domain contracts;
- outer harness replacement does not require a second assessment state model.

Outstanding proof:

- real hardware behavior must validate the software architecture.

---

# Phase 1 — Host provider baseline

## Goal

Make the local host environment **provider #0** so the agent remains useful without Flipper or any other external security appliance.

The host provider is not unrestricted shell access. It is a registry of bounded, typed, policy-controlled capabilities backed by local resources and tools.

## Milestone 1.1 — Host descriptor

Create a normalized host/provider description covering relevant resources such as:

- operating system and architecture;
- USB access;
- serial interfaces;
- network interfaces;
- available analysis/debug/build toolchains;
- supported artifact types;
- local deployment methods where relevant;
- evidence/output channels;
- explicit limitations and unavailable privileges.

Acceptance:

- the runtime can describe host capabilities through the same provider discovery surface used for physical tools;
- an outer agent does not need to know which local command implements a capability.

## Milestone 1.2 — First bounded host capabilities

Start with safe, high-value capabilities that make hardware assessment useful with minimal equipment.

Candidate families:

```text
interface.usb.enumerate
interface.serial.enumerate
artifact.firmware.inspect
artifact.binary.identify
artifact.strings.extract
artifact.filesystem.inspect
network.interface.inspect
```

Add low-level debugger/flashing capabilities only behind explicit compatibility and policy gates.

Acceptance:

- a connected target exposing USB, serial, network, or firmware artifacts can produce evidence without Flipper;
- execution is typed and evidence-producing rather than generic shell passthrough.

## Milestone 1.3 — Host-only assessment proof

Use an authorized development board or simple embedded target.

Reference flow:

```text
target connected
  -> discover USB/serial surface
  -> create target/component state
  -> run applicable host capabilities
  -> collect evidence
  -> produce observations
  -> identify what cannot yet be tested
```

Acceptance:

- a useful assessment progresses with no external provider connected;
- unsupported tests resolve to explicit capability/setup gaps.

---

# Phase 2 — Flipper as external capability augmentation

## Goal

Prove that Flipper is an optional provider that extends the same assessment rather than defining it.

## Milestone 2.1 — Real Flipper + Marauder certification

Required baseline session:

```text
Flipper identity / firmware
  -> SD/app state
  -> Marauder identity / firmware
  -> composite preflight
  -> passive Wi-Fi HIL
  -> approved network HIL
  -> generated-FAP smoke test
  -> sanitized transcript capture
  -> replay fixtures
```

Acceptance:

- deterministic physical smoke command reports stack health;
- release claims are backed by hardware-verification records;
- replay fixtures never masquerade as real HIL.

## Milestone 2.2 — Capability augmentation proof

Run one assessment first with the host provider only, then attach Flipper and resume the same durable assessment.

Acceptance:

- the target and TestCases do not change merely because Flipper appears;
- available capability routes expand after discovery;
- newly applicable tests become candidates;
- unrelated Flipper capabilities are not selected;
- evidence continuity is preserved across provider attachment.

This is the first strong proof that the product is **Hardware Pentest Agent**, not Flipper Agent.

---

# Phase 3 — Provider independence

## Goal

Prove that a capability is not synonymous with one device implementation.

## Milestone 3.1 — Capability requirement model

Strengthen capability requirements so routing can account for:

- physical interface kind;
- electrical domain;
- directionality;
- timing/sampling requirements;
- bandwidth;
- read/interact/transmit/modify needs;
- runtime bounds;
- evidence schema;
- operator setup;
- recovery expectations.

Acceptance:

- provider compatibility is explained in domain terms rather than vendor names.

## Milestone 3.2 — Same capability, different provider

Choose one capability with at least two materially different implementation routes.

Good candidate:

```text
internal.uart.observe
```

Possible routes may include:

- a compatible host serial path;
- Flipper GPIO/UART implementation;
- later a programmable board or logic analyzer route.

Acceptance:

- the TestCase semantics remain unchanged;
- the resolver can select different implementations based on available hardware and constraints;
- evidence is normalized enough that the assessment can interpret either route;
- selection is explainable.

## Milestone 3.3 — Second materially different provider

Only after the previous proof, add the provider that best stresses the abstraction.

Preferred candidates:

- RP2040 for programmable timing/PIO;
- logic analyzer/sigrok for high-fidelity bus capture;
- OpenOCD-compatible debug probe for SWD/JTAG;
- ESP32 when a radio/network capability is the best next proof.

Do not choose the next provider because it is popular. Choose it because it exposes a capability or constraint the existing providers cannot prove.

---

# Phase 4 — Capability-gap handling and executable capability memory

## Goal

Prove the system can encounter a missing capability during an assessment, represent the gap correctly, and create a bounded implementation when synthesis is justified.

## Milestone 4.1 — Generalized synthesis request

A `CapabilitySynthesisRequest` should be hardware-neutral and include:

```text
objective
required physical interfaces
electrical/timing/bandwidth constraints
action class
runtime bounds
expected evidence schema
target constraints
candidate providers
```

The synthesis backend is chosen only after these requirements are known.

## Milestone 4.2 — Build/deployment/evidence contracts

Keep separate contracts for:

```text
CapabilitySynthesisBackend
BuildProvider
DeploymentProvider
EvidenceChannel
```

Flipper FAP/uFBT remains backend #1.

Future backends may include RP2040, ESP32, generated sigrok decoders, OpenOCD/GDB automation artifacts, or bounded host-side tools.

## Milestone 4.3 — Real capability-gap experiment

Reference scenario:

```text
unknown authorized PCB
  -> suspected UART header
  -> need internal.uart.autodetect
  -> no exact verified route
  -> derive physical requirements
  -> choose compatible provider
  -> synthesize bounded implementation
  -> build/deploy
  -> operator setup
  -> execute
  -> collect evidence
  -> HIL verify
  -> persist implementation
  -> resume assessment
```

Acceptance:

- the missing implementation is created inside the assessment lifecycle;
- source/build/deployment/evidence are reproducible;
- compilation alone cannot mark the implementation verified;
- a fresh session can reuse the promoted implementation without model memory.

---

# Phase 5 — Physical safety and connection planning

## Goal

Make low-level electrical safety and operator setup explicit enough that the agent can reason about what is safe to observe or drive.

## Milestone 5.1 — Physical connection model

Represent facts such as:

- pin/test-point identity;
- measured voltage;
- ground/reference confirmation;
- signal direction hypothesis;
- pull-up/pull-down state;
- powered/unpowered state;
- shared bus ownership;
- contention risk;
- required level shifting/isolation;
- probe/cable placement;
- recovery action.

## Milestone 5.2 — Passive-before-active gate

Reference behavior:

```text
pin 1 -> GND             confirmed
pin 2 -> 3.31 V          measured
pin 3 -> candidate TX    observe allowed
pin 4 -> candidate RX    drive blocked
```

Acceptance:

- active actions can be blocked by unresolved physical facts even when the provider technically supports the operation;
- operator actions are durable state, not prompt text.

---

# Phase 6 — Real target-class proofs

These milestones prove the target model and methodology, not device-specific automation.

## Milestone 6.1 — Unknown PCB

Flow:

```text
human/visual inspection
  -> component/test-point hypotheses
  -> electrical confirmation
  -> passive bus/debug detection
  -> protocol identification
  -> firmware acquisition
  -> targeted follow-up experiments
```

Acceptance:

- the component graph evolves from evidence;
- the assessment can proceed incrementally from very little initial knowledge.

## Milestone 6.2 — Embedded camera/router-class target

Potential components:

```text
device
  +-- SoC / MCU
  +-- Wi-Fi/Ethernet
  +-- UART/debug header
  +-- SPI flash
  +-- removable storage
  +-- firmware/update path
```

Acceptance:

- one assessment mixes host capabilities and at least one external provider;
- provider routing is dynamic;
- no target-specific agent loop is required.

## Milestone 6.3 — Drone

Potential components:

- flight controller;
- radio link;
- GNSS;
- ESC/CAN/UART buses;
- storage;
- camera;
- companion computer;
- debug/programming interfaces.

Acceptance:

- one assessment state spans multiple components and providers;
- irrelevant connected providers are ignored;
- methodology remains generic rather than becoming drone-specific.

---

# Phase 7 — Multi-provider lab runtime

## Goal

Operate a real hardware-security bench where the agent can discover and select among several connected providers.

Example:

```text
host             -> artifact/USB/serial/network analysis
Flipper          -> broad wireless / selected GPIO interaction
RP2040/ESP32     -> programmable timing/bus/radio helper
logic analyzer   -> high-fidelity digital capture
debug probe      -> authorized SWD/JTAG checks
Proxmark3        -> deeper RFID/NFC
SDR              -> RF capture/analysis where authorized
```

Acceptance:

- one target assessment routes across providers without planner-specific device branches;
- evidence/provenance remains continuous;
- provider addition/removal is reflected dynamically;
- the resolver explains why each provider was selected.

---

# Phase 8 — Remote hardware node

## Goal

Separate the reasoning client from the physical bench without changing domain semantics.

A Linux SBC such as a Raspberry Pi can act as a **hardware execution node** hosting the local runtime and attached instruments.

```text
outer authorized harness
        |
 authenticated domain protocol
        |
 Hardware Pentest Node
 Linux SBC / bench host
        |
   +----+-----------------------------+
   |          |          |            |
Flipper    debugger   analyzer       target
```

The node is not merely another pentest capability. It is a deployment topology for providers and the local runtime.

Acceptance:

- remote connectivity does not expose generic shell/serial control to the outer agent;
- policy, gates, evidence, provider semantics, and assessment state remain identical to local operation.

---

# Future provider families

Only add these when they support a validated capability need or architecture proof:

- RP2040 / ESP32 / STM32 programmable boards;
- OpenOCD-compatible probes;
- logic analyzers / sigrok;
- Proxmark3-class RFID/NFC tools;
- SDRs such as HackRF-class devices;
- ChipWhisperer-class side-channel/fault-injection hardware;
- CAN/LIN tooling;
- USB protocol hardware;
- firmware programmers/extractors;
- emulation/rehosting environments;
- automated fixtures and lab robotics.

Prefer integrating mature specialist systems behind provider/adapter contracts over reimplementing them.

---

# Release discipline

Do not advertise planned capability as implemented.

Use capability maturity consistently:

- `declared`;
- `simulated`;
- `implemented`;
- `hardware_verified`;
- `assessment_verified`.

For synthesized implementations, artifact/build success remains distinct from physical verification.

## Long-term success criterion

The product is successful when it can reliably answer:

> **Given this authorized hardware target and the providers available right now, what can I test, how should I test it safely, what can I prove from evidence, and what additional capability is required for the tests I cannot yet perform?**

The number of integrated tools is secondary.
