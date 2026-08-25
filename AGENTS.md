# Hardware Pentest Agent — Agent Instructions

This repository controls real security hardware. Treat the runtime, engagement store, operator gates, preflight, verification, evidence, provider/adapters, synthesis pipeline, and harness-neutral service as domain boundaries. Do not bypass them to make a test pass.

## Product direction

The product is **Hardware Pentest Agent**.

It is not a Flipper command collection, not a catalog of device integrations, and not a bespoke generic LLM harness.

The long-term product is a hardware-native pentesting runtime where an outer agent can turn an authorized security objective into a reproducible physical experiment using whatever compatible capabilities are available at that moment.

The fundamental model is:

```text
TARGET
  = the system being assessed

PROVIDER
  = a controllable resource that contributes capabilities

CAPABILITY
  = a stable vendor-neutral operation required by a TestCase
```

Examples:

- drone/camera/router/PCB under assessment -> target;
- host computer -> provider #0;
- Flipper Zero -> external provider #1;
- debugger/logic analyzer/RP2040/ESP32/SDR -> additional providers;
- `internal.uart.observe` -> capability.

Never make a provider the product architecture.

Read:

- `README.md`
- `docs/PROGRAMMABLE_HARDWARE.md`
- `docs/ARCHITECTURE.md`
- `docs/CAPABILITY_SYNTHESIS.md`
- `docs/HARNESS_INTEGRATION.md`
- `docs/ROADMAP.md`

## Provider #0: host environment

The runtime should remain useful without any external pentesting device connected.

Treat the local host as the baseline provider for bounded capabilities backed by resources such as USB, serial, network interfaces, firmware-analysis tools, debuggers, build toolchains, and evidence-processing utilities.

Do **not** interpret this as permission to expose an unrestricted shell, arbitrary process execution, raw serial passthrough, or generic package execution to an outer model.

Host operations must be:

- typed;
- capability-scoped;
- policy-controlled;
- bounded;
- evidence-producing;
- subject to the same engagement and operator gates as physical providers.

Adding a provider changes the available capability set. It must not change assessment semantics.

```text
host only
  -> baseline capabilities

+ Flipper
  -> baseline + Flipper capabilities

+ debugger
  -> previous + debug capabilities
```

A connected provider that is irrelevant to the current target/TestCase should not be selected.

## Capability-first design

Before adding another fixed device command, ask:

1. Is this a stable capability need?
2. Is the capability applicable to the current target/component?
3. Does a verified implementation already exist?
4. Can verified primitives compose it?
5. Is there a mature specialist provider/tool that already solves it?
6. If not, should a bounded host-side or provider-specific implementation be synthesized?
7. If no compatible provider exists, should the runtime return a capability/setup gap instead?

Do not grow MCP, CLI, or provider code into a mirror of vendor commands.

## Physical reality is part of the domain

A provider being technically capable of an operation does not mean the operation is physically safe or applicable.

Model relevant constraints such as:

- voltage domain;
- ground/reference state;
- signal direction;
- target power state;
- bus ownership;
- contention risk;
- pull-up/pull-down requirements;
- required level shifting or isolation;
- probe/cable placement;
- reset/recovery path.

When these facts are unresolved, return a physical/operator gate or capability/setup gap. Do not bypass the uncertainty with raw commands.

## Default development workflow

Use the named harness profiles:

```bash
python scripts/test_harness.py quick
python scripts/test_harness.py contract
python scripts/test_harness.py ci
```

`quick`, `contract`, and `ci` must not require real hardware. Before merging a PR, run the same `ci` profile used by GitHub Actions.

## Harness-neutral integration

The project owns hardware-pentest domain state, not the generic LLM loop. Prefer:

1. `hardware_pentest.service.HardwarePentestService` for native Python integration.
2. `hardware-pentest-mcp` for MCP-capable harnesses.
3. typed CLI commands for humans, CI, and trusted local development agents.

Do not create a second implementation of assessment state, engagement scope, provider state, capability semantics, synthesis provenance, verification, gates, or evidence inside an MCP/HTTP/agent adapter.

Read-oriented local MCP:

```bash
hardware-pentest-mcp
```

High-level assessment creation/execution for a trusted local harness:

```bash
hardware-pentest-mcp --allow-execution
```

A local HTTP endpoint may be started explicitly:

```bash
hardware-pentest-mcp --transport streamable-http --host 127.0.0.1 --port 8765
```

Do not weaken network-binding or remote-execution guards for convenience.

## Durable planning/context

Outer-agent conversation memory is not the assessment state.

Use runtime context/candidate operations so different harnesses reason over the same methodology:

```text
persisted engagement
  -> assessment_create
  -> assessment_context
  -> assessment_candidates
  -> assessment_execute_next
```

The candidate surface should carry TestCase purpose, prerequisites, expected evidence, stop conditions, result rules, action class and gate requirements rather than relying on prompt prose.

## Programmable hardware providers

New hardware support should use the `HardwareDescriptor`/provider model describing physical resources, toolchains, artifact formats, deployment/recovery paths and evidence channels.

Examples of provider backends include:

- host provider with bounded local capabilities;
- Flipper FAP/uFBT;
- ESP32/ESP-IDF or PlatformIO;
- RP2040/Pico SDK/PIO;
- STM32/Zephyr/OpenOCD paths;
- specialist Proxmark/sigrok/OpenOCD/SDR providers;
- bounded Linux/SBC execution nodes.

A camera or drone is normally a target/component graph, not a new generic agent harness. The assessment may use several providers against that target.

The next provider should be chosen because it proves an architectural property or unlocks a real capability gap, not because the roadmap needs another device name.

## Capability synthesis

Generated FAPs are the first synthesis backend, not the final abstraction.

Long-term flow:

```text
capability need
  -> existing implementation?
  -> compose?
  -> specialist provider?
  -> host-side bounded implementation?
  -> generalized CapabilitySynthesisRequest
  -> provider/backend selection
  -> build/deploy/evidence
  -> HIL verification
  -> reusable CapabilityImplementation
```

Do not let provider-specific generated source or toolchain commands leak into assessment/TestCase logic.

Successful generated implementations should become executable capability memory only after appropriate HIL verification. Compilation alone is not proof of physical correctness.

## Operator-owned actions

Agents must not import/expand their own engagement scope or satisfy their own approval, physical-action, or recovery gates through MCP.

Operator scope is imported separately:

```bash
hardware-pentest-operator engagement-import --manifest ./engagement.yaml
```

One-shot gates are created only through the interactive operator CLI:

```bash
hardware-pentest-operator gate-grant \
  --assessment-id <assessment> \
  --step-id <exact-step-id> \
  --kind approval
```

Gate kinds are `approval`, `human_action`, and `recovery`.

## Real hardware

Real hardware tests are opt-in only.

```bash
export HPA_HIL=1
export HPA_FLIPPER_PORT=/dev/...
export HPA_MARAUDER_PORT=/dev/...   # when applicable
python scripts/test_harness.py hil
```

Do not run HIL when `HPA_HIL` is absent or not `1`.

Preferred current Flipper inspection commands include:

```bash
hardware-pentest flipper-ports
hardware-pentest flipper-probe --port "$HPA_FLIPPER_PORT"
hardware-pentest flipper-self-test --port "$HPA_FLIPPER_PORT"
hardware-pentest-preflight --flipper-port "$HPA_FLIPPER_PORT" --marauder-port "$HPA_MARAUDER_PORT"
```

Use existing typed transports instead of ad-hoc pyserial scripts when the repository already models the operation.

## Current implementation invariants

- Do not mark capabilities `hardware_verified` from simulator/mocks/transcript replay.
- Wi-Fi secrets remain references, not persisted values.
- Generated Flipper apps remain in the reserved namespace and go through immutable provenance, bounded execution, evidence and cleanup.
- Physical target/component state and provider state must remain distinct.
- The host provider must not become a generic shell escape hatch.
- Network exposure must not alter capability/TestCase semantics.
- Hosted agents should receive domain MCP, not generic shell/serial access on the bench host.
- Provider presence alone is never a reason to execute a capability.
- An unsupported physical requirement must remain a visible capability/setup gap.

## Test expectations

New hardware/provider/transport/build/deployment code needs negative and failure-path coverage appropriate to its boundary: malformed protocol output, timeout, disconnect, partial transfer, stale identity, changed firmware/toolchain, tampered artifact, cleanup failure, incompatible descriptor, deployment failure, evidence-schema failure, unsafe electrical constraints, or unavailable host privilege.

Recorded real-device fixtures must be sanitized and must run through production parsers/transports.

Provider selection and generalized synthesis should have scenario tests proving that:

- an existing implementation is preferred over unnecessary generation;
- incompatible hardware is rejected;
- irrelevant connected hardware is ignored;
- attaching a provider expands candidate routes without rewriting the assessment;
- the same capability need can resolve to different providers;
- a synthesized implementation cannot become reusable solely from build success;
- assessment state resumes after capability creation without depending on conversation history;
- a capability/setup gap is returned when no valid route exists.

## Architecture shorthand

Reason in this order:

```text
target/component security question
  -> TestCase
  -> capability need
  -> applicability + physical requirements
  -> implementation resolution
       reuse / compose / specialist / host / synthesize
  -> hardware provider
  -> physical/operator gates
  -> build/deploy when applicable
  -> execution
  -> evidence
  -> observation
  -> finding only after validation
```

When no route exists, model the capability gap. Do not solve architectural gaps with a raw command escape hatch.
