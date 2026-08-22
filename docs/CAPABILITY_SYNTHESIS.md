# Agent Capability Synthesis

## Goal

The hardware pentest agent should behave like an experienced hardware pentester, not a fixed command router.

When a test objective is not covered by an existing verified capability, the agent may propose a purpose-built Flipper helper. The helper is still subject to deterministic policy, build provenance, engagement scope, approval, deployment and hardware verification gates.

```text
assessment objective
      |
      v
existing verified capability? -- yes --> execute normally
      |
      no
      v
CapabilitySynthesisRequest
      |
      v
agent generates source + GeneratedAppManifest
      |
      v
GeneratedSourcePolicy
      |
      +-- reject --> no project/build/deployment
      |
      v
immutable generated project
  main.c
  hpa_runtime.c/.h
  application.fam
  synthesis.json
      |
      v
bounded uFBT build
      |
      v
source-tree/FAM/manifest/log/FAP hashes
      |
      v
GeneratedFlipperAdapter
      |
      v
normal engagement policy + explicit approval
      |
      v
bounded one-shot FAP execution
      |
      v
private result.json -> normal ExecutionResult
      |
      v
HIL verification
      |
      v
optional promotion into reusable capability
```

## Why FAPs

Flipper Zero supports external applications packaged as FAP files. Generated tools use ordinary external-app projects with an `application.fam` and target `f7`. The build backend is uFBT and never invokes a shell.

Generated tools use the reserved `hpa_gen_` app-id namespace and `NullSquare` FAP category. They cannot overwrite catalogued applications.

## Source policy

The first synthesis profile intentionally permits only bounded `OBSERVE` and `INTERACT` helpers. Supported declared interfaces are initially:

- GPIO
- UART
- I2C
- SPI
- read-only storage access
- infrared receive

The policy rejects undeclared hardware-interface use and blocks APIs/behaviors that must be represented by separately typed capabilities, including RF/IR transmission, USB HID/BadUSB behavior, NFC emulation, arbitrary storage writes, destructive storage operations, device power/reset and inline assembly.

Generated source must return structured evidence through the injected `hpa_write_evidence_json()` helper. Agent-written code cannot choose an arbitrary storage path or call `storage_file_write` directly. The trusted helper limits output to 4096 bytes and writes only `APP_DATA_PATH("result.json")` after asking the Flipper storage layer to ensure the app-private data directory exists.

An operator-controlled policy profile can raise the action-class ceiling later, but raising the ceiling does not remove prohibited API rules. Advanced RF/Wi-Fi simulation should therefore enter as reviewed typed capability profiles rather than arbitrary source bypasses.

Static analysis is not considered proof that code is safe. It is only the first enforcement layer.

## Build provenance

For every accepted generated project, the runtime records SHA-256 hashes for:

- agent-generated source;
- the complete source tree including the trusted evidence helper;
- `application.fam`;
- synthesis manifest;
- build log;
- compiled FAP.

The builder re-hashes the reviewed project immediately before invoking uFBT. Any modification after review fails closed.

The subprocess contract is deliberately narrow:

- fixed executable (`ufbt` by default);
- no user-controlled command arguments;
- `shell=False`;
- project root as the only working directory;
- bounded timeout;
- reduced child environment;
- one expected FAP artifact under `dist/`.

## Generated FAP runtime

`GeneratedFlipperAdapter` exposes one synthesized capability at `IMPLEMENTED` maturity. It is intentionally **not** called `hardware_verified` merely because policy and compilation succeeded.

First execution requires an approval-bearing Action and accepts no runtime parameters in v1. Changing the test parameters means creating a new reviewed artifact.

The runtime:

1. re-verifies local source/build provenance;
2. re-probes the exact Flipper identity and firmware state;
3. refuses to interrupt another running Flipper application;
4. creates only `/ext/apps/NullSquare` when required;
5. transfers only `/ext/apps/NullSquare/hpa_gen_*.fap` and verifies device MD5;
6. removes any stale private `result.json`;
7. launches the exact generated FAP;
8. verifies the expected app identity while it is running;
9. enforces the manifest runtime bound and closes an over-running helper;
10. reads at most 4096 bytes from `/ext/apps_data/<app-id>/result.json`;
11. validates a strict result schema;
12. links the ExecutionResult to source, source-tree, FAM, synthesis, build-log and FAP hashes;
13. removes the generated result and FAP after success or failure when ephemeral cleanup is enabled.

The generated result schema is deliberately small:

```json
{
  "schema_version": "1",
  "status": "success",
  "observations": {}
}
```

`status` may be `success`, `inconclusive`, or `failed`. Missing/malformed evidence causes execution failure and must not be promoted into a target finding.

## Remaining M4 work

The synthesis and one-shot runtime boundaries now exist. Remaining work before synthesized tools can become reusable capabilities is:

1. persist immutable build/runtime records so an agent session can reconstruct a generated capability without trusting mutable local paths;
2. integrate capability synthesis into assessment planning as a fallback when no suitable verified route exists;
3. add generated-tool HIL verification that binds the tool hash to an exact Flipper/firmware state and known physical fixture;
4. promote only successful HIL-tested generated tools into a reusable capability catalogue;
5. move compilation into a stronger isolated build sandbox before enabling broader generated-code profiles.

## Product principle

The product is not "full Marauder CLI access" or "arbitrary code execution." It is a hardware pentester that can reason about the available instruments and create a new, reviewable instrument capability when necessary.
