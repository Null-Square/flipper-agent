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
        +-- durable assessment state
        +-- pentest methodology and test semantics
        +-- capability registry/routing
        +-- engagement policy and approvals
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

The first service operations are deliberately read-oriented:

- `service_info`
- `hardware_discover`
- `assessment_list`
- `assessment_context`
- `verification_records`
- `preflight_records`

`assessment_context` is intentionally bounded. It exposes durable pentest state for one reasoning turn without depending on an LLM conversation transcript. Target metadata values are not copied into the compact context; only metadata keys are surfaced by this first interface.

Future execution operations must call the existing policy/assessment/runtime APIs rather than reimplementing device behavior in the interface layer.

## MCP

Install the optional MCP support:

```bash
pip install -e ".[mcp,flipper]"
```

### Local agent harnesses

Run the server over stdio:

```bash
hardware-pentest-mcp
```

A local MCP-capable harness can launch this command as a child process. This is the preferred development integration because no TCP listener is required.

### Local Streamable HTTP

The same tools can be exposed on a local port:

```bash
hardware-pentest-mcp --transport streamable-http --host 127.0.0.1 --port 8765
```

The MCP endpoint is `/mcp`.

The built-in launcher deliberately refuses non-loopback binding. Do not turn this development server into an unauthenticated public hardware-control endpoint.

For an online harness, keep the service bound to localhost and use a secure MCP tunnel, VPN/private overlay, or a separately deployed authenticated MCP/ASGI gateway. Production remote access must add authentication, authorization, TLS, host allowlisting, audit identity, and explicit action controls before exposing write/execute tools.

## Interface invariants

Every interface must preserve these rules:

1. No raw Flipper CLI tool.
2. No raw Marauder command tool.
3. No generic serial-write tool.
4. No interface-local bypass of engagement policy, approval, preflight, verification, or evidence capture.
5. Mocks and recorded transcripts never create `hardware_verified` state.
6. Secrets are represented by references, not copied into durable agent context.
7. Remote/network exposure does not change capability semantics or action classification.

## Context ownership

The outer harness may compact or discard its conversation. The pentest must still be recoverable from runtime state.

```text
conversation context       -> outer harness
assessment context         -> Hardware Pentest Agent
hardware state             -> Hardware Pentest Agent
verification/evidence      -> Hardware Pentest Agent
```

An agent should refresh its working state from `assessment_context` instead of relying on remembered prose from previous model turns.

## Long-term plug-and-play target

The desired matrix is:

| Consumer | Preferred interface |
| --- | --- |
| Codex local | MCP stdio |
| Human / CI | CLI |
| Null-AI | Python service or MCP |
| Other local agent harness | MCP stdio or local Streamable HTTP |
| Hosted/online agent harness | Authenticated remote MCP gateway/tunnel |

The domain behavior must remain the same across all of them. Agent evaluations should run identical assessment scenarios through different outer harnesses and compare safety, evidence quality, test coverage, and findings.
