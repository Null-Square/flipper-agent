<div align="center">

# Hardware Pentest Agent

**Agent-native hardware and embedded security testing.**

Connect supported security instruments, define an authorized assessment objective, and let the runtime discover available capabilities, plan bounded tests, execute approved actions, capture evidence, and produce reproducible findings.

![Status](https://img.shields.io/badge/status-Flipper--first%20MVP-FED900)
![Use](https://img.shields.io/badge/use-authorized%20only-000000)
![By NullSquare](https://img.shields.io/badge/by-NullSquare-FED900)

</div>

> **Current repository name:** `flipper-agent`. The project direction has expanded beyond one device. The intended repository name is `hardware-pentest-agent`. Flipper Zero is the first supported instrument, not the architecture.

## Mission

Give AI pentesters controlled, vendor-neutral access to physical and embedded security-testing capabilities.

The runtime sits between an agent and specialist security instruments. It does not replace those instruments. It gives the agent a stable capability model, authorization gates, physical-safety validation, evidence capture, and a reproducible assessment state.

```text
Security Agent
      |
      v
Hardware Pentest Agent
      |
      +-- Target and assessment model
      +-- Capability registry and routing
      +-- Scope, policy, and approval gates
      +-- Evidence and findings
      |
      +-- Instrument adapters
             |
             +-- Flipper Zero   <- MVP
             +-- Proxmark3      <- next proof of abstraction
             +-- sigrok/Saleae  <- planned
             +-- OpenOCD        <- planned
             +-- HackRF         <- planned
             +-- other tools    <- future
```

## Why this project exists

IoT and embedded assessments cross several attack surfaces: wireless interfaces, internal buses, debug ports, storage, firmware, physical interfaces, network services, mobile applications, APIs, and cloud services.

Specialist tools already solve many low-level tasks well. The missing layer is a security-agent runtime that can:

1. model the authorized target;
2. determine which tests apply;
3. discover connected instruments and their capabilities;
4. choose an appropriate instrument for each test step;
5. validate scope and physical constraints before execution;
6. require human action or approval when needed;
7. preserve raw evidence and provenance;
8. separate observations from confirmed findings;
9. produce a reproducible assessment record.

The project uses the OWASP IoT Security Testing Guide (ISTG) as an initial testing ontology and methodology reference. It does not copy the guide or claim formal compliance.

## Core abstraction: capabilities, not devices

The agent should reason about assessment capabilities such as:

```text
wireless.nfc.identify
wireless.nfc.observe
wireless.rfid.identify
wireless.subghz.observe
internal.uart.observe
internal.spi.capture
internal.i2c.capture
debug.jtag.detect
debug.swd.detect
memory.acquire
firmware.extract
firmware.analyze
protocol.decode
evidence.capture
```

Device-specific commands stay inside adapters.

```text
Assessment test
      |
      v
Required capability
      |
      v
Capability registry
      |
      v
Best available instrument
      |
      v
Policy + constraints
      |
      v
Adapter execution
      |
      v
Evidence
```

This lets the same assessment engine use different instruments without rewriting agent logic.

## Flipper-first MVP

The first MVP uses a USB-connected Flipper Zero because one device exposes several useful physical capability families and has a documented CLI/RPC control surface.

### MVP goal

Given an authorized IoT target and a USB-connected Flipper Zero, the runtime must:

- discover the device and supported capabilities;
- create a structured target and engagement state;
- build a passive-first, non-destructive assessment plan;
- execute approved observation steps across multiple capability families;
- block actions outside the engagement policy without relying on the LLM;
- capture structured evidence with hashes and provenance;
- keep inconclusive observations separate from findings;
- generate an OWASP-ISTG-aligned assessment report.

### MVP capability families

The MVP targets at least four working families from the Flipper Zero where supported by the selected transport and firmware:

- NFC observation and identification;
- low-frequency RFID observation and identification;
- Sub-GHz observation;
- infrared observation;
- GPIO/UART-oriented inspection where safe and technically available.

### Explicit MVP non-goals

The MVP does not provide autonomous destructive or high-impact testing. The initial release excludes arbitrary shell execution, unrestricted FAP execution, credential attacks, autonomous emulation, arbitrary BadUSB payload execution, fault injection, invasive memory extraction, and unrestricted RF transmission.

These actions can only enter later milestones after the authorization, policy, legal, and physical-safety model is proven.

## Safety model

The language model is not the enforcement boundary.

Every physical action passes through deterministic checks:

```text
Agent proposal
      |
      v
Typed capability schema
      |
      v
Engagement scope
      |
      v
Instrument constraints
      |
      v
Risk policy
      |
      +--> blocked
      +--> human approval required
      +--> allowed
      |
      v
Execution
```

Initial action classes:

- `OBSERVE` - passive or read-only activity;
- `INTERACT` - bounded interaction with a target;
- `TRANSMIT` - intentional RF/IR transmission;
- `MODIFY` - changes target or instrument state relevant to the assessment;
- `EMULATE` - impersonates or emulates an authorized device/tag/signal;
- `DESTRUCTIVE` - fault injection or invasive/destructive work.

The default MVP policy permits only explicitly scoped low-risk actions. Higher-risk classes are blocked or require explicit operator approval.

## Human actions are first-class

Hardware testing cannot be fully autonomous. Some steps require a person to open an enclosure, identify ground, measure voltage, place probes, attach adapters, or confirm a physical connection.

The assessment engine therefore supports `HUMAN_ACTION_REQUIRED` as a normal step state. The agent must not guess that physical setup is safe or complete.

## Evidence model

Every executed step should produce a durable record containing:

- engagement and target identifiers;
- test case and capability;
- instrument and adapter version;
- exact normalized inputs;
- timestamps;
- raw output or artifact reference;
- artifact hash when applicable;
- normalized observation;
- execution result and limitations.

The reporting layer promotes an observation to a finding only when evidence supports the claim.

## Repository layout

```text
src/hardware_pentest/
  core/          domain models and capability contracts
  runtime/       discovery, registry, routing, execution, jobs
  policy/        scope, risk, approvals, physical constraints
  evidence/      artifacts, provenance, observations, findings
  adapters/      device/tool integrations
    flipper/     first instrument adapter
  interfaces/    CLI, Python API, MCP adapter
  reporting/     assessment output

docs/
  ARCHITECTURE.md
  MVP.md
  ROADMAP.md
  SECURITY_MODEL.md
  CAPABILITY_MODEL.md
```

## Interfaces

MCP is an interface, not the architecture.

The core runtime should remain usable from:

- a Python API;
- a local CLI;
- an MCP server;
- Null-AI or another agent harness through a native integration later.

The first MCP surface should expose high-level assessment operations instead of raw device commands.

## Roadmap summary

1. Define schemas and deterministic simulator.
2. Build the Flipper USB transport and adapter.
3. Implement capability discovery and passive-first actions.
4. Add engagement policy, approval gates, and evidence capture.
5. Run a reproducible multi-step Flipper assessment.
6. Add a small MCP interface over the runtime.
7. Add Proxmark3 as the second instrument and prove vendor-neutral routing.
8. Add logic/debug/RF/firmware tool adapters.
9. Build multi-instrument IoT hardware assessments.
10. Integrate the runtime with Null-AI.

See [`docs/ROADMAP.md`](docs/ROADMAP.md) and [`docs/MVP.md`](docs/MVP.md).

## Reference methodology

Initial design references include:

- [OWASP IoT Security Testing Guide](https://owasp.org/owasp-istg/)
- [Flipper Zero CLI documentation](https://docs.flipper.net/zero/development/cli)
- [Flipper Zero protobuf definitions](https://github.com/flipperdevices/flipperzero-protobuf)
- [NIST IR 8259 Rev. 1](https://csrc.nist.gov/pubs/ir/8259/r1/final)

These sources guide terminology and test coverage. The project remains responsible for its own implementation, validation, and safety controls.

## Responsible use

This project is for authorized security testing and research only.

Use it only on targets that you own or are explicitly authorized to assess. Follow applicable radio, privacy, access-control, export, and cybersecurity laws. A configured engagement scope does not create legal authorization by itself.

## Current status

**Phase:** architecture and Flipper-first MVP foundation.

The repository is not yet a production pentesting system.

---

<div align="center">
<sub>A <b><a href="https://nullsquare.net">NullSquare</a></b> project.</sub>
</div>
