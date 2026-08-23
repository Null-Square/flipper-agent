# Roadmap

## North star

Build a hardware-native pentesting runtime that can use **programmable physical hardware as a substrate**, not merely call a fixed set of prebuilt device functions.

The agent should be able to:

```text
understand target
   -> identify security question
   -> determine required physical capability
   -> inspect available hardware providers
   -> reuse / compose / synthesize an implementation
   -> deploy and execute it
   -> collect evidence
   -> refine the assessment
```

Flipper Zero is the first reference provider because it gives us a practical platform to prove the full lifecycle. It must not become the boundary of the architecture.

The generic LLM harness is intentionally outside this roadmap. Codex, Null-AI or another harness may own inference, generic context management and the agent tool loop. Hardware Pentest Agent owns durable pentest state, hardware semantics, methodology, implementations, physical execution and evidence.

See `PROGRAMMABLE_HARDWARE.md`.

---

## Phase A — Harness kernel and Flipper reference provider

### Milestone A0 — Core domain foundation — **done**

Deliverables:

- engagement, target, instrument, capability, action, evidence, observation and finding models;
- capability registry;
- deterministic policy decisions;
- adapter protocol;
- simulator;
- local durable state and evidence;
- routing and policy tests.

Architectural acceptance:

- assessment logic contains no Flipper command strings;
- denied actions fail below the model layer;
- the simulator and real adapters implement the same contracts.

### Milestone A1 — Flipper transport and typed adapter — **done in software**

Deliverables:

- USB discovery and identity;
- typed Flipper transport operations;
- connection/timeout/error handling;
- capability registration;
- app installation/loader support;
- transport contract tests and transcript replay.

Next hardening:

- introduce structured Flipper protobuf RPC where it provides a stronger control surface;
- support transport selection without leaking transport details into capability semantics.

### Milestone A2 — Flipper/Marauder capability slice — **implemented; physical verification incomplete**

Implemented families include native Flipper observation/inspection and Marauder Wi-Fi observation plus approved network-discovery operations.

Acceptance still requires real HIL evidence. Software mocks and recorded transcripts never satisfy this milestone alone.

### Milestone A3 — Persistent assessment engine — **done**

Deliverables:

- versioned TestCase catalog;
- passive-first planning;
- persistent assessment state;
- pause/resume/recovery;
- evidence-linked observations/findings;
- deterministic candidate-test semantics.

### Milestone A4 — Harness-neutral service and MCP — **done for current surface**

Deliverables:

- Python service facade;
- MCP stdio and local Streamable HTTP;
- durable assessment context;
- deterministic assessment creation/candidates;
- high-level one-step execution;
- persisted engagement scope;
- one-shot operator gate grants;
- no dependence on outer-agent conversation memory.

Acceptance:

- Codex/Null-AI/another MCP client can use the same runtime without rewriting policy, state or device adapters;
- replacing the outer harness does not change evidence semantics.

### Milestone A5 — Real bench certification — **next physical milestone**

Goal: prove that the software contracts survive the real Flipper + Wi-Fi board stack.

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
- expected real-device transcripts are committed in sanitized replay form;
- release claims are backed by hardware verification records.

---

## Phase B — Generalize from instruments to programmable hardware providers

### Milestone B1 — `HardwareDescriptor`

Goal: describe what a board/tool can physically and computationally provide independently of vendor command syntax.

Descriptor areas:

- identity / revision / MCU or SoC family;
- architecture and relevant compute/memory limits;
- GPIO/electrical domain;
- UART/SPI/I2C/CAN and other buses;
- Wi-Fi/BLE/NFC/Sub-GHz/SDR resources;
- USB roles;
- timers/ADC/DAC/DMA/PIO where relevant;
- debug/programming interfaces;
- installed firmware/runtime state;
- build toolchains;
- artifact types;
- deployment/recovery methods;
- evidence channels;
- verified limitations.

Deliverables:

- normalized descriptor schema;
- descriptor validation;
- provider discovery contract;
- Flipper descriptor implementation;
- descriptor snapshots in evidence/provenance where relevant.

Acceptance:

- core planning can ask what hardware resources are available without knowing the device vendor;
- Flipper-specific details are isolated behind provider/backend implementations.

### Milestone B2 — Physical capability graph

Goal: move beyond a flat capability registry and represent what capabilities can be implemented from available physical resources.

The graph should answer:

- which verified capability already exists;
- which lower-level primitives can compose a solution;
- which external tool can satisfy the requirement;
- which provider can host synthesized code;
- what timing/electrical/bandwidth constraints apply;
- what operator setup and evidence channel are required.

Acceptance:

- the resolver can explain *why* a provider/implementation was selected;
- generation is not chosen when an existing/composed implementation is sufficient.

### Milestone B3 — Generalize `CapabilitySynthesisRequest`

Goal: remove Flipper/FAP assumptions from the synthesis intent model.

Generic request fields should include:

```text
objective
required physical interfaces
read/interact/transmit/modify needs
timing/bandwidth constraints
runtime bounds
expected evidence schema
target constraints
candidate providers
```

The request should select a backend only after capability requirements are understood.

### Milestone B4 — Build/deployment provider contracts

Separate:

```text
CapabilitySynthesisBackend
BuildProvider
DeploymentProvider
EvidenceChannel
```

First implementations:

- Flipper FAP / uFBT;
- Flipper storage/loader and later RPC-assisted deployment.

Next candidate implementations:

- ESP-IDF / PlatformIO + esptool;
- RP2040 Pico SDK / PIO + UF2;
- STM32/Zephyr + DFU/OpenOCD;
- bounded Linux/SBC build and execution;
- sigrok decoder generation;
- OpenOCD/GDB automation artifacts.

Acceptance:

- assessment/synthesis logic contains no direct toolchain command construction;
- backend provenance is immutable and reproducible.

### Milestone B5 — Refactor generated FAPs as backend #1

Goal: prove the generalized synthesis contracts with the functionality we already have.

Deliverables:

- existing FAP source policy/build/runtime moved behind generic synthesis interfaces;
- Flipper-specific source/runtime rules remain in the Flipper backend;
- common implementation metadata for source/artifact hashes, descriptor compatibility, evidence schema and HIL records.

Acceptance:

- no behavior regression in current generated-FAP tests;
- generic runtime can describe the FAP as one capability implementation among future backends.

### Milestone B6 — Persist executable capability memory

Goal: make newly created physical capabilities reusable across agent sessions.

Store:

- normalized capability ID;
- synthesis request;
- source and artifact hashes;
- hardware-descriptor compatibility;
- toolchain/version constraints;
- evidence schema;
- known limitations;
- HIL verification records;
- assessment usage history.

Lifecycle:

```text
generated -> implemented -> HIL verified -> reusable route
```

Acceptance:

- a fresh outer-agent session can discover and reuse an old verified synthesized implementation without relying on conversation memory.

---

## Phase C — Prove adaptive physical capability creation

### Milestone C1 — Flipper capability-gap experiment

This is the most important Flipper milestone after baseline HIL.

Goal: solve a physical problem that was **not pre-implemented as a fixed capability handler**.

Reference scenario:

```text
unknown authorized PCB
  -> likely UART header
  -> required capability: internal.uart.autodetect
  -> no exact existing route
  -> resolver chooses Flipper resources
  -> synthesize bounded FAP
  -> deploy
  -> collect structured evidence
  -> HIL verify
  -> persist implementation
  -> resume assessment
```

Acceptance:

- the missing implementation is created during the assessment lifecycle;
- source/build/deployment/evidence are reproducible;
- a later assessment can reuse the promoted implementation.

### Milestone C2 — Second programmable provider

Goal: prove that synthesis is not a renamed FAP generator.

Preferred candidates are a materially different provider such as RP2040 or ESP32 because they expose different compute/timing/radio resources and require different toolchains/deployment paths.

Example proof:

- create a bus/sniffing or timing capability on RP2040 PIO that is not practical on the Flipper implementation;
- route the same capability need to the better provider without changing the TestCase semantics.

Acceptance:

- same generalized synthesis request can resolve to different backends;
- provider selection is explainable and evidence-linked.

### Milestone C3 — Specialist provider proof

Add one non-general-purpose specialist path:

- Proxmark3 for RFID/NFC, or
- sigrok/logic analyzer for digital capture, or
- OpenOCD-compatible probe for SWD/JTAG.

This proves the resolver can choose between “synthesize on a board” and “use a mature specialist instrument.”

---

## Phase D — Real target classes

### Milestone D1 — Camera hardware assessment

Goal: assess a lab-owned embedded camera as a multi-component target rather than a single device command sequence.

Potential component graph:

```text
camera
  +-- Wi-Fi/network
  +-- UART/debug header
  +-- SPI flash
  +-- removable storage
  +-- image subsystem
  +-- firmware/update path
```

The assessment should mix existing capabilities, specialist tools and synthesized helpers when required.

Acceptance:

- target/component graph evolves from evidence;
- at least one capability route is selected dynamically from available providers;
- no camera-specific agent loop is required.

### Milestone D2 — Drone hardware assessment

Goal: prove the target model scales to a more complex embedded system.

Potential components:

- flight controller;
- RF link;
- GNSS;
- ESC/CAN/UART buses;
- storage;
- camera;
- companion computer;
- debug/programming interfaces.

Acceptance:

- one assessment state spans multiple physical components/providers;
- the methodology remains generic rather than becoming drone-specific.

### Milestone D3 — Unknown PCB workflow

Goal: support progressive low-level discovery where little is known initially.

Flow:

```text
visual/human inspection
  -> component/test-point hypotheses
  -> electrical confirmation
  -> passive bus/debug detection
  -> protocol identification
  -> firmware acquisition
  -> deeper targeted experiments
```

Vision-assisted PCB understanding may become one input, but physical measurements remain evidence.

---

## Phase E — Multi-provider hardware pentester

### Milestone E1 — Multi-provider assessment graph

Example:

```text
Flipper        -> broad wireless / quick physical interaction
RP2040/ESP32   -> synthesized timing/bus/radio helper
Proxmark3      -> deeper RFID/NFC analysis
logic analyzer -> high-fidelity bus capture
OpenOCD probe  -> authorized debug checks
firmware tools -> artifact analysis
```

Acceptance:

- one target assessment routes across providers without planner-specific device branches;
- evidence/provenance remains continuous across transitions.

### Milestone E2 — Harness evaluations

Run identical assessment scenarios through different outer harnesses:

- Codex;
- Null-AI;
- another MCP-capable harness;
- future native orchestrator if needed.

Compare:

- test coverage;
- unnecessary actions;
- capability selection;
- evidence quality;
- findings;
- recovery behavior;
- synthesized-tool quality.

The purpose is to keep domain behavior strong without coupling the product to one LLM harness.

### Milestone E3 — Hosted/remote bench operation

Goal: allow an authorized online harness to operate a local/remote hardware lab through an authenticated service boundary.

The hardware daemon remains local to the bench. Remote connectivity is a transport/deployment concern, not a new execution architecture.

---

## Phase F — Broader embedded-security workflows

Future providers/integrations may include:

- SDRs such as HackRF-class devices;
- ChipWhisperer-class side-channel/fault-injection hardware;
- CAN/LIN tooling;
- USB protocol hardware;
- firmware extraction/programmers;
- EMBA/FACT/Binwalk-compatible artifact analysis;
- emulation/rehosting;
- automated fixture control and lab robotics.

Do not reimplement mature specialist platforms when they can be integrated behind a provider/adapter contract.

---

## Release discipline

Do not advertise a planned capability as implemented.

Use capability maturity consistently:

- `declared`;
- `simulated`;
- `implemented`;
- `hardware_verified`;
- `assessment_verified`.

For synthesized implementations, also distinguish artifact/build success from physical verification.

The long-term success criterion is not the number of hard-coded tools. It is:

> **How reliably can the agent turn an authorized physical security question into a reproducible experiment using whatever compatible hardware is available?**
