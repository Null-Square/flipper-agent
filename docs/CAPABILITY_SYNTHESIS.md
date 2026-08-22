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
  application.fam
  synthesis.json
      |
      v
bounded uFBT build
      |
      v
source/FAM/manifest/log/FAP hashes
      |
      v
future deployment gate
      |
      v
normal engagement policy + approval
      |
      v
bounded execution + evidence
      |
      v
HIL verification
      |
      v
optional promotion into reusable capability
```

## Why FAPs

Flipper Zero supports external applications packaged as FAP files. Generated tools use ordinary external-app projects with an `application.fam` and target `f7`. The build backend is uFBT and never invokes a shell.

Generated tools use the reserved `hpa_gen_` app-id namespace and `NullSquare` FAP category. They are not allowed to overwrite known/catalo­gued applications.

## Source policy

The first synthesis profile intentionally permits only bounded `OBSERVE` and `INTERACT` helpers. Supported declared interfaces are initially:

- GPIO
- UART
- I2C
- SPI
- read-only storage access
- infrared receive

The policy rejects undeclared hardware-interface use and blocks APIs/behaviors that must be represented by separately typed capabilities, including RF/IR transmission, USB HID/BadUSB behavior, NFC emulation, destructive storage operations, device power/reset and inline assembly.

An operator-controlled policy profile can raise the action-class ceiling later, but raising the ceiling does not remove prohibited API rules. Advanced RF/Wi-Fi simulation should therefore enter as reviewed typed capability profiles rather than arbitrary source bypasses.

Static analysis is not considered proof that code is safe. It is only the first enforcement layer.

## Build provenance

For every accepted generated project, the runtime records SHA-256 hashes for:

- generated source;
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

## What this slice does not do yet

This slice builds a trustworthy synthesis boundary. It does **not** yet deploy or execute generated FAPs on a Flipper.

The next slice should add a generated-app deployment/runtime adapter with these requirements:

1. destination limited to the generated NullSquare namespace;
2. FAP SHA-256/MD5 verified before and after transfer;
3. exact running-app identity verified through the Flipper loader;
4. engagement policy evaluated using the generated capability ID and declared action class;
5. explicit operator approval for profiles that require it;
6. bounded execution and deterministic stop/close behavior;
7. raw output and runtime evidence linked to source/build provenance;
8. HIL verification before a generated capability can be promoted/reused.

## Product principle

The long-term product is not "full Marauder CLI access" or "arbitrary code execution." It is a hardware pentester that can reason about the available instruments and create a new, reviewable instrument capability when necessary.
