# Prior Art and Design Rationale

## Purpose

This document records the main external systems that shaped the project direction.

It is not a complete market survey. Re-check current projects before making novelty or competitive claims.

## Flipper control is not the product gap

Several projects already connect agent/MCP interfaces to Flipper Zero.

Examples include:

- `roostercoopllc/flipper-mcp` - MCP-oriented Flipper control using a Wi-Fi Dev Board path;
- `busse/flipperzero-mcp` - host-side Flipper/MCP integration;
- `pogorelov-labs/flipper-ble-mcp` - Flipper control over Bluetooth Low Energy (BLE).

References:

- https://github.com/roostercoopllc/flipper-mcp
- https://github.com/busse/flipperzero-mcp
- https://github.com/pogorelov-labs/flipper-ble-mcp

Flipper also has documented command-line and RPC control surfaces:

- https://docs.flipper.net/zero/development/cli
- https://github.com/flipperdevices/flipperzero-protobuf

### Design implication

Do not position this project as the first MCP server or the first agent that can control a Flipper Zero.

MCP is an external interface. Flipper is the first instrument adapter.

## Hardware pentesting already has strong specialist tools

The project should integrate mature tools instead of replacing them.

### RFID/NFC

Proxmark3 provides deep RFID/NFC tooling and automation surfaces.

Reference:

- https://github.com/RfidResearchGroup/proxmark3

### Logic analysis and bus decoding

sigrok provides open-source acquisition and protocol decoding across many supported devices and protocols.

Reference:

- https://sigrok.org/

Saleae exposes an automation API for Logic 2.

Reference:

- https://saleae.github.io/logic2-automation/

### JTAG/SWD

OpenOCD provides a machine-oriented Tcl/RPC interface and supports many debug adapters and targets.

Reference:

- https://openocd.org/

### Firmware analysis

Existing platforms already automate substantial firmware analysis.

Examples:

- EMBA - https://github.com/e-m-b-a/emba
- FACT - https://github.com/fkie-cad/fact_core
- FirmAE - https://github.com/pr0v3rbs/FirmAE

### Design implication

Hardware Pentest Agent should provide normalized capabilities, routing, policy, assessment state, and evidence across these tools.

It should not reimplement each specialist engine.

## IoT testing methodology already exists

The OWASP IoT Security Testing Guide (ISTG) provides a device model, attacker model, methodology, and test catalog for IoT security testing.

References:

- https://owasp.org/owasp-istg/
- https://owasp.org/owasp-istg/02_framework/device_model.html
- https://owasp.org/owasp-istg/02_framework/methodology.html

### Design implication

Use OWASP ISTG as an initial testing ontology and mapping reference.

Do not invent a Flipper-specific checklist and call it an IoT methodology.

The runtime should translate a security test into required capabilities and then choose instruments.

## Product-security references

NIST IR 8259 Rev. 1 provides current foundational cybersecurity activities for IoT product manufacturers.

Reference:

- https://csrc.nist.gov/pubs/ir/8259/r1/final

ETSI EN 303 645 is another relevant baseline for consumer IoT cybersecurity.

Reference:

- https://www.etsi.org/technologies/consumer-iot-security

### Design implication

Standards and guidance can enrich reporting and remediation mappings.

They do not replace technical evidence or test execution.

## Agentic pentesting lessons

Research systems such as PentestGPT show that language models can help with individual pentest tasks but need structured state and orchestration across a longer engagement.

Reference:

- https://arxiv.org/abs/2308.06782

### Design implication

Do not use conversation history as the assessment state.

Persist the target model, plan, executions, evidence, observations, and findings as explicit objects.

## Physical instrumentation lessons

Physical instruments differ from ordinary software tools because invalid commands can affect equipment or targets.

The runtime therefore uses:

- schema-bound actions;
- deterministic validation;
- capability-specific constraints;
- explicit human physical actions;
- safe failure behavior.

### Design implication

The agent is a planner and interpreter. It is not the enforcement boundary.

## Current differentiation hypothesis

The project should be evaluated as the combination of:

```text
IoT/hardware test semantics
+ vendor-neutral capability model
+ live instrument discovery
+ deterministic capability routing
+ engagement authorization
+ physical constraints
+ human/agent hybrid workflow
+ evidence provenance
+ cross-instrument assessment state
```

Any one item alone is not the novelty claim.

The project must prove value through implementation and real assessments before NullSquare makes strong novelty claims.
