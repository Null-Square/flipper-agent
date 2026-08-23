# Prior Art and Design Rationale

## Purpose

This document records external systems that shaped the architecture and clarifies where Hardware Pentest Agent should reuse existing work rather than duplicate it.

It is not a novelty claim or complete market survey. Re-check current projects before making competitive statements.

## Flipper MCP/control already exists

Several projects already expose Flipper Zero to MCP or other agent interfaces.

Examples include:

- `roostercoopllc/flipper-mcp`;
- `busse/flipperzero-mcp`;
- `pogorelov-labs/flipper-ble-mcp`.

References:

- https://github.com/roostercoopllc/flipper-mcp
- https://github.com/busse/flipperzero-mcp
- https://github.com/pogorelov-labs/flipper-ble-mcp

Flipper also provides documented CLI and protobuf control surfaces:

- https://docs.flipper.net/zero/development/cli
- https://github.com/flipperdevices/flipperzero-protobuf

### `busse/flipperzero-mcp` lesson

`busse/flipperzero-mcp` is especially relevant because it demonstrates a richer Flipper device-control layer than a simple serial wrapper, including modular MCP tools, protobuf RPC work and a Wi-Fi Dev Board TCP/UART bridge path.

That is useful prior art for our **Flipper provider implementation**.

The architectural lesson is not to turn Hardware Pentest Agent into another Flipper MCP server. It is to place strong transports such as USB/RPC/Wi-Fi bridge **under** our hardware-provider/capability layer.

```text
Hardware Pentest Agent capability
        |
Flipper provider
        |
CLI / protobuf RPC / Wi-Fi bridge / FAP runtime
        |
Flipper Zero
```

### Design implication

Do not position this project as the first AI/MCP integration for Flipper.

The stronger differentiation target is:

> **A hardware-native pentesting runtime that can understand physical resources and create/reuse capability implementations across programmable boards and specialist instruments.**

## Fixed device tools are not enough

A conventional tool integration assumes the needed function already exists:

```text
agent -> named tool -> device function
```

The intended architecture must also support:

```text
agent security objective
  -> physical capability need
  -> available hardware resources
  -> existing implementation? compose? specialist tool?
  -> if missing: synthesize implementation
  -> build/deploy/execute/evidence
```

That requirement is why the project needs hardware descriptors, capability implementation records, synthesis backends and executable capability memory rather than only larger MCP tool lists.

## Hardware pentesting already has strong specialist tools

The project should integrate mature specialist systems instead of replacing them.

### RFID/NFC

Proxmark3 provides deep RFID/NFC tooling.

- https://github.com/RfidResearchGroup/proxmark3

### Logic analysis and protocol decoding

sigrok provides acquisition and protocol decoding across many devices and protocols.

- https://sigrok.org/

Saleae exposes a Logic 2 automation API.

- https://saleae.github.io/logic2-automation/

### JTAG/SWD

OpenOCD provides automation surfaces and broad target/probe support.

- https://openocd.org/

### Firmware analysis

Examples include:

- EMBA — https://github.com/e-m-b-a/emba
- FACT — https://github.com/fkie-cad/fact_core
- FirmAE — https://github.com/pr0v3rbs/FirmAE

### Design implication

The resolver should prefer a mature verified specialist implementation when it already satisfies the capability need. Synthesis exists for gaps, not to recreate every mature tool.

## Programmable boards as pentest substrates

General-purpose microcontroller boards add a different possibility from specialist tools: the agent can create a task-specific physical instrument.

Relevant ecosystems include:

- Flipper external applications (FAP/uFBT);
- ESP32 / ESP-IDF / PlatformIO;
- RP2040 / Pico SDK / PIO;
- STM32 / Zephyr / vendor toolchains;
- Linux SBCs and small embedded computers.

### Design implication

Treat board/toolchain/deployment support as provider backends. The assessment should specify physical requirements and expected evidence before choosing a backend.

The key abstraction is not “ESP32 tool” or “Flipper command.” It is a verified `CapabilityImplementation` compatible with a `HardwareDescriptor`.

## IoT testing methodology already exists

The OWASP IoT Security Testing Guide (ISTG) provides a device model, attacker model, methodology and test catalog for IoT security testing.

References:

- https://owasp.org/owasp-istg/
- https://owasp.org/owasp-istg/02_framework/device_model.html
- https://owasp.org/owasp-istg/02_framework/methodology.html

### Design implication

Use OWASP ISTG as an initial ontology/mapping reference. Do not invent a Flipper-specific checklist and call it an IoT methodology.

Target classes such as cameras or drones should be represented as component graphs and applicable TestCases rather than separate bespoke agent harnesses.

## Product-security references

Relevant baseline references include:

- NIST IR 8259 Rev. 1 — https://csrc.nist.gov/pubs/ir/8259/r1/final
- ETSI EN 303 645 — https://www.etsi.org/technologies/consumer-iot-security

Standards can enrich methodology/reporting but do not replace physical evidence.

## Agentic pentesting lessons

Research systems such as PentestGPT demonstrate the value of language models for pentest reasoning and the difficulty of maintaining long-running assessment state.

- https://arxiv.org/abs/2308.06782

### Design implication

Do not make conversation history the assessment database.

Persist:

- target/component graph;
- assessment plan;
- capability implementations;
- hardware/provider state;
- build/deployment provenance;
- evidence/observations/findings.

This also makes the runtime portable across Codex, Null-AI and other agent harnesses.

## Current differentiation hypothesis

The project should be evaluated as the combination of:

```text
hardware/IoT test semantics
+ target/component model
+ hardware descriptors
+ vendor-neutral capability needs
+ reusable capability implementations
+ dynamic capability synthesis
+ build/deployment provenance
+ physical HIL verification
+ multi-provider routing
+ durable assessment/evidence state
+ harness-neutral MCP/Python/CLI access
```

The central hypothesis is stronger than “AI can control security hardware”:

> **An AI pentester can turn an authorized physical security question into a reproducible experiment by selecting, composing or programming whatever compatible hardware providers are available.**

That hypothesis still needs to be proven through real hardware assessments. The first decisive proof should be a capability-gap experiment that creates a missing implementation during a Flipper-first assessment, followed by a second backend proving the same synthesis model is not FAP-specific.
