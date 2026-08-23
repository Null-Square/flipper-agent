# Harness-Neutral Agent Integration

## Principle

Hardware Pentest Agent owns the hardware-pentesting domain. It does not need to own the generic LLM agent loop.

```text
Codex / Null-AI / another agent harness
        |
        | MCP / CLI / Python
        v
Hardware Pentest Agent service boundary
        |
        +-- durable engagement scope
        +-- durable target/component + assessment state
        +-- pentest methodology and candidate-test semantics
        +-- capability implementations / routing
        +-- hardware providers / descriptors
        +-- synthesis / build / deployment provenance
        +-- physical preflight and HIL verification
        +-- evidence / observations / findings
        |
        v
real hardware
```

The outer harness may own model invocation, conversation compaction, generic retries, generic coding tools, and user interaction. Those concerns must not become prerequisites for the domain runtime.

This lets Codex remain useful during development and later production use without making Codex the product architecture.

## Stable service facade

`hardware_pentest.service.HardwarePentestService` is the framework-free integration boundary.

Current read/domain-context operations include:

- `service_info`
- `hardware_discover`
- `engagement_list`
- `assessment_list`
- `assessment_context`
- `assessment_candidates`
- `verification_records`
- `preflight_records`

Current mutating/execution operations include:

- `assessment_create`
- `assessment_execute_next`
- `assessment_recover_interrupted`

`assessment_context` is intentionally bounded and durable. `assessment_candidates` returns deterministic methodology semantics such as purpose, prerequisites, expected evidence, stop conditions, result rules, capability, action class and gate requirements. Different outer harnesses therefore reason over the same pentest domain rather than inventing their own checklist from prompt text.

Execution goes through the existing assessment runner, policy engine, capability registry, hardware-verification resolver, preflight store and evidence store. The interface layer does not reimplement device behavior.

## Future provider/synthesis operations

As the programmable-hardware architecture lands, the harness-neutral surface should grow by **domain concepts**, not vendor commands.

Expected directions include:

```text
hardware.describe
hardware.providers
capability.search
capability.implementations
synthesis.propose
synthesis.status
synthesis.implementations
evidence.get
```

An outer harness may help generate code for a requested capability, but it should not have to understand whether the implementation eventually becomes a Flipper FAP, ESP-IDF project, RP2040 PIO program or another artifact.

```text
outer harness
   -> capability need
   -> Hardware Pentest Agent synthesis request
   -> selected provider/backend
   -> optional coding/model assistance
   -> runtime build/deploy/evidence
```

See `PROGRAMMABLE_HARDWARE.md` and `CAPABILITY_SYNTHESIS.md`.

## Operator-owned scope

An outer agent must not redefine its technical assessment scope while executing. Import the engagement manifest through the operator interface:

```bash
hardware-pentest-operator engagement-import --manifest ./engagement.yaml
```

The runtime persists a normalized integrity-checked copy under `.hardware-pentest/engagements/`. Assessment creation/execution resolves scope by ID from this store rather than trusting an arbitrary model-supplied manifest path.

## Deterministic planning across harnesses

A harness creates an assessment from persisted scope and a known provider backend, then reads candidate tests from the runtime.

Conceptually:

```text
engagement ID + target ID
        |
        v
assessment_create
        |
        v
persisted deterministic plan
        |
        v
assessment_candidates
        |
        +-- purpose
        +-- prerequisites
        +-- expected evidence
        +-- stop conditions
        +-- result rules
        +-- action class
        +-- operator gates
```

This is deliberate: model choice may influence which useful candidate is selected next, but it does not redefine test semantics.

## Operator gates

The outer agent cannot satisfy approval, physical-human-action or interrupted-execution recovery gates by passing booleans such as `approve=true`.

When a step pauses, an operator may grant exactly one short-lived gate from an interactive terminal:

```bash
hardware-pentest-operator gate-grant \
  --assessment-id assessment-123 \
  --step-id 'assessment-123:wifi.join.v1' \
  --kind approval
```

Physical setup and recovery use the same command with `human_action` or `recovery` gate kinds.

Gate creation remains outside MCP.

## MCP

Install MCP support:

```bash
pip install -e ".[mcp,flipper]"
```

### Read-oriented local harness

```bash
hardware-pentest-mcp
```

### Local harness with assessment creation/execution

```bash
hardware-pentest-mcp --allow-execution
```

Execution remains high-level and one-step-at-a-time. The MCP tool cannot self-assert operator gates.

### Local Streamable HTTP

```bash
hardware-pentest-mcp \
  --transport streamable-http \
  --host 127.0.0.1 \
  --port 8765
```

The endpoint is `/mcp`.

Local HTTP execution requires both explicit server enablement and the additional remote-execution environment opt-in already enforced by the launcher.

The built-in launcher deliberately refuses non-loopback binding.

## Hosted/online harness direction

A future online GPT/agent should not receive direct USB/serial access. It connects to a hardware-host service boundary:

```text
online harness
      |
authenticated MCP gateway / private tunnel
      |
localhost Hardware Pentest Agent daemon
      |
hardware providers
```

The hardware daemon remains physically near the bench. Remote connectivity changes only the interface transport, not assessment/policy/evidence semantics.

Production remote access must add deployment-specific authentication, authorization, TLS/private transport, audit identity and session/rate controls.

## Trust distinction: local development vs hosted agents

A local coding harness with repository shell access is a highly trusted development actor and can potentially edit/invoke local commands. Use that mode for controlled development/bench work.

A hosted production agent should receive only the domain MCP surface and no shell on the hardware host.

```text
Development Codex
  -> local repo/shell + MCP
  -> cheap interactive bench engineering

Hosted agent
  -> authenticated domain MCP only
  -> no generic shell/serial access
```

## Context ownership

The outer harness may compact or discard its conversation. The pentest remains recoverable because domain state is durable.

```text
conversation context              -> outer harness
engagement scope                  -> Hardware Pentest Agent
target/component graph            -> Hardware Pentest Agent
assessment/TestCase state         -> Hardware Pentest Agent
hardware descriptors/providers    -> Hardware Pentest Agent
capability implementation memory  -> Hardware Pentest Agent
build/deployment provenance       -> Hardware Pentest Agent
verification/evidence             -> Hardware Pentest Agent
```

An agent should refresh from `assessment_context`, `assessment_candidates`, and future provider/implementation APIs rather than trust remembered prose.

## Coding assistance vs physical capability ownership

The outer harness can be excellent at writing code. That does not mean it should own deployment semantics.

Example:

```text
runtime: "need internal.uart.autodetect on this provider"
   |
Codex: generate candidate implementation source
   |
runtime: review/build/hash/deploy/execute/evidence/HIL
```

A different coding model can be substituted without changing the capability implementation record or assessment evidence.

## Interface invariants

Every interface must preserve these design rules:

1. Assessment semantics are capability/TestCase based, not vendor-command based.
2. Provider/toolchain details stay below the service boundary where possible.
3. Harness changes do not reset target/assessment/evidence state.
4. Mocks and transcript replay never create real hardware verification.
5. Generated artifacts remain explicit implementations with build/deployment provenance.
6. A capability synthesized for one provider is not assumed compatible with another without descriptor matching and verification.
7. A camera/drone/router target does not require a new generic agent harness; it extends the target/component and capability/provider domain.

## Plug-and-play target

| Consumer | Preferred interface |
| --- | --- |
| Codex local | MCP stdio with optional execution + local coding tools |
| Human / CI | CLI |
| Null-AI | Python service or MCP |
| Other local agent harness | MCP stdio or local HTTP |
| Hosted/online harness | authenticated MCP gateway/tunnel |

Agent evaluations should run identical assessment scenarios through multiple outer harnesses and compare coverage, capability choices, unnecessary actions, evidence quality, synthesized-tool quality and findings.

The goal is not identical prose. The goal is that the same durable hardware-pentest domain produces consistently strong and reproducible physical work regardless of which competent outer harness is plugged in.
