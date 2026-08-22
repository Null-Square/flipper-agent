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

## Harness-neutral by design

Hardware Pentest Agent owns the **hardware-pentesting domain**, not the generic LLM loop.

Codex, Null-AI, another MCP-capable harness, or a future hosted agent can sit outside the runtime:

```text
Codex / Null-AI / another agent harness
        |
        | MCP / CLI / Python
        v
Hardware Pentest Agent
        |
        +-- durable assessment context
        +-- methodology / TestCases
        +-- capability registry
        +-- scope / policy / approvals
        +-- physical preflight / HIL verification
        +-- evidence / observations / findings
        |
        v
Flipper / Marauder / future instruments
```

The outer harness may own model inference, conversation compaction, generic retries, and user interaction. Critical pentest state must remain durable in this runtime so changing harnesses does not change safety or evidence semantics.

See [`docs/HARNESS_INTEGRATION.md`](docs/HARNESS_INTEGRATION.md).

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

Policy-reviewed generated FAPs may be synthesized and executed only through the reserved NullSquare generated-app pipeline with immutable build provenance, bounded runtime, structured evidence, approval, and cleanup. That is not an arbitrary FAP execution escape hatch.

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
  service/       harness-neutral domain service facade
  policy/        scope, risk, approvals, physical constraints
  evidence/      artifacts, provenance, observations, findings
  adapters/      device/tool integrations
    flipper/     first instrument adapter
    marauder/    ESP32 Marauder Wi-Fi adapter
  interfaces/    CLI and thin MCP adapters
  reporting/     assessment output
  synthesis/     policy-gated generated Flipper capabilities

docs/
  ARCHITECTURE.md
  HARNESS_INTEGRATION.md
  TESTING.md
  MVP.md
  ROADMAP.md
  SECURITY_MODEL.md
  CAPABILITY_MODEL.md
```

## Interfaces

MCP is an interface, not the architecture.

The runtime is intended to remain usable from:

- a native Python service facade;
- the local CLI;
- an MCP server;
- Null-AI or another outer agent harness.

Install MCP support with:

```bash
pip install -e ".[mcp]"
```

Local MCP via stdio:

```bash
hardware-pentest-mcp
```

Local Streamable HTTP MCP:

```bash
hardware-pentest-mcp --transport streamable-http --host 127.0.0.1 --port 8765
```

The built-in MCP launcher refuses non-loopback binding. Hosted/online harnesses should reach a localhost service through a secure MCP tunnel or a separately authenticated deployment layer rather than exposing unauthenticated hardware control publicly.

The initial MCP surface is intentionally high-level and read-oriented. Raw serial, raw Flipper CLI, and raw Marauder commands are not tools.

## Testing

Use the named test harness profiles:

```bash
python scripts/test_harness.py quick
python scripts/test_harness.py contract
python scripts/test_harness.py ci
```

Real hardware HIL is explicit and opt-in. Recorded sanitized device transcripts can be replayed through production transports in ordinary CI, but replay never creates hardware-verification evidence.

See [`docs/TESTING.md`](docs/TESTING.md).

## Roadmap summary

1. Define schemas and deterministic simulator. **Done**
2. Build the Flipper USB transport and adapter. **Done**
3. Implement capability discovery and passive-first actions. **In progress / working MVP**
4. Add engagement policy, approval gates, and evidence capture. **Done**
5. Run a reproducible multi-step Flipper assessment. **Done in software; physical coverage expanding**
6. Add a harness-neutral service facade and MCP interface. **In progress**
7. Harden real-device HIL, transcript replay, and agent evaluations. **In progress**
8. Add Proxmark3 as the second instrument and prove vendor-neutral routing.
9. Add logic/debug/RF/firmware tool adapters.
10. Build multi-instrument IoT hardware assessments and integrate with Null-AI/other harnesses.

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

**Phase:** Flipper-first harness kernel, real-hardware hardening, and harness-neutral integration.

The repository is not yet a production pentesting system.

---

<div align="center">
<sub>A <b><a href="https://nullsquare.net">NullSquare</a></b> project.</sub>
</div>
