# Harness-Neutral Agent Integration

## Principle

Hardware Pentest Agent owns the hardware-pentesting domain. It does not need to own the generic LLM agent loop.

```text
Codex / Null-AI / another agent harness
        |
        |  MCP / CLI / Python
        v
Hardware Pentest Agent service boundary
        |
        +-- durable engagement scope
        +-- durable assessment state
        +-- pentest methodology and test semantics
        +-- capability registry/routing
        +-- policy and operator gates
        +-- physical preflight and HIL verification
        +-- evidence, observations, and findings
        +-- instrument and generated-tool adapters
        |
        v
real hardware
```

The outer harness may own model invocation, conversation compaction, generic retries, file/shell tools, and user interaction. Those concerns must not become prerequisites for the domain runtime.

## Stable service facade

`hardware_pentest.service.HardwarePentestService` is the framework-free integration boundary.

Read/domain-context operations include:

- `service_info`
- `hardware_discover`
- `engagement_list`
- `assessment_list`
- `assessment_context`
- `verification_records`
- `preflight_records`

Execution operations include:

- `assessment_execute_next`
- `assessment_recover_interrupted`

`assessment_context` is intentionally bounded. It exposes durable pentest state for one reasoning turn without depending on an LLM conversation transcript. Target metadata values are not copied into the compact context; only metadata keys are surfaced by this interface.

Execution goes through the existing assessment runner, policy engine, capability registry, hardware-verification resolver, preflight store, and evidence store. The service layer does not reimplement device behavior.

## Operator-owned scope

An outer agent must not be allowed to redefine its legal/technical scope while executing an assessment. Import the engagement manifest through the operator interface:

```bash
hardware-pentest-operator engagement-import --manifest ./engagement.yaml
```

The runtime persists a normalized integrity-checked copy under `.hardware-pentest/engagements/`. Assessment execution resolves the engagement by ID from this store; it does not trust an arbitrary manifest path supplied by the model during execution.

## Operator gates

The outer agent cannot satisfy approval, physical-human-action, or interrupted-execution recovery gates by passing booleans such as `approve=true`.

When a step pauses, an operator may grant exactly one short-lived gate from an interactive terminal:

```bash
hardware-pentest-operator gate-grant \
  --assessment-id assessment-123 \
  --step-id 'assessment-123:wifi.join.v1' \
  --kind approval
```

For a physical setup confirmation:

```bash
hardware-pentest-operator gate-grant \
  --assessment-id assessment-123 \
  --step-id 'assessment-123:gpio.inspect.v1' \
  --kind human_action
```

For acknowledging an interrupted step whose physical outcome is unknown:

```bash
hardware-pentest-operator gate-grant \
  --assessment-id assessment-123 \
  --step-id 'assessment-123:some-step' \
  --kind recovery
```

`gate-grant` requires an interactive TTY and asks the operator to type the exact step ID. Grants are integrity-checked, short-lived, exact-step scoped, and one-shot. They are consumed by the runtime when used.

Do **not** expose the operator CLI as an MCP tool.

## MCP

Install the optional MCP support:

```bash
pip install -e ".[mcp,flipper]"
```

### Read-only local agent harness

Run the server over stdio:

```bash
hardware-pentest-mcp
```

This is the safe default. No assessment execution tools are registered.

### Local executing agent harness

For a trusted local harness such as Codex running on the hardware host:

```bash
hardware-pentest-mcp --allow-execution
```

Execution is still high-level and one-step-at-a-time. The MCP tool has no approval/human-action arguments. Required gates must already exist in the operator gate store.

### Local Streamable HTTP

Read-only:

```bash
hardware-pentest-mcp \
  --transport streamable-http \
  --host 127.0.0.1 \
  --port 8765
```

The MCP endpoint is `/mcp`.

To expose execution tools on the local HTTP listener, two independent opt-ins are required:

```bash
export HPA_MCP_REMOTE_EXECUTION=1
hardware-pentest-mcp \
  --transport streamable-http \
  --host 127.0.0.1 \
  --port 8765 \
  --allow-execution
```

The built-in launcher deliberately refuses non-loopback binding.

For an online harness, keep the service bound to localhost and use a secure MCP tunnel, VPN/private overlay, or separately deployed authenticated MCP/ASGI gateway. Production remote access must add authentication, authorization, TLS, host allowlisting, audit identity, and deployment-specific rate/session controls.

## Trust distinction: local development vs hosted agents

A local coding harness with shell access to the repository is inherently a highly trusted development actor: it can potentially edit files or invoke operator commands. Use that mode for development and controlled bench work.

A production/hosted agent should **not** receive shell access on the hardware host. It should receive only the MCP service tools. The operator-only engagement import and gate-grant surfaces remain outside MCP.

```text
Development Codex
  -> local repo/shell + MCP
  -> trusted bench workflow

Hosted/production agent
  -> authenticated MCP only
  -> no shell on hardware host
  -> no gate-grant tool
  -> no engagement-import tool
```

## Interface invariants

Every interface must preserve these rules:

1. No raw Flipper CLI tool.
2. No raw Marauder command tool.
3. No generic serial-write tool.
4. No interface-local bypass of engagement policy, approval, human action, preflight, verification, or evidence capture.
5. An agent cannot self-assert operator approval or physical completion.
6. An agent cannot acknowledge an unknown interrupted hardware outcome without a recovery grant.
7. Mocks and recorded transcripts never create `hardware_verified` state.
8. Secrets are represented by references, not copied into durable agent context.
9. Remote/network exposure does not change capability semantics or action classification.
10. Remote execution remains one bounded assessment step per service call.

## Context ownership

The outer harness may compact or discard its conversation. The pentest must still be recoverable from runtime state.

```text
conversation context       -> outer harness
engagement scope           -> Hardware Pentest Agent
assessment context         -> Hardware Pentest Agent
hardware state             -> Hardware Pentest Agent
verification/evidence      -> Hardware Pentest Agent
operator gates             -> Hardware Pentest Agent / operator
```

An agent should refresh its working state from `assessment_context` instead of relying on remembered prose from previous model turns.

## Long-term plug-and-play target

The desired matrix is:

| Consumer | Preferred interface |
| --- | --- |
| Codex local | MCP stdio with optional execution |
| Human / CI | CLI |
| Null-AI | Python service or MCP |
| Other local agent harness | MCP stdio or local Streamable HTTP |
| Hosted/online agent harness | Authenticated remote MCP gateway/tunnel |

The domain behavior must remain the same across all of them. Agent evaluations should run identical assessment scenarios through different outer harnesses and compare scope adherence, safety, evidence quality, test coverage, and findings.
