<div align="center">

<img src="docs/assets/cover-2.png" alt="Flipper Agent — AI-driven hardware security testing, for authorized use" width="100%">

# Flipper Agent

**An AI agent for the Flipper Zero** — plan and run hardware security assessments in plain language, with every action operator-approved, fully logged, and scoped to authorized engagements.

![Status](https://img.shields.io/badge/status-early%20%2F%20concept-FED900)
![Use](https://img.shields.io/badge/use-authorized%20only-000000)
![By NullSquare](https://img.shields.io/badge/by-NullSquare-FED900)

</div>

> 🚧 **Early / vision stage.** The repository is being scaffolded. This README describes the direction and the guardrails it will be built around.

## Overview

Flipper Agent pairs a large language model with a **Flipper Zero** so a security operator can drive
its capabilities through natural language. Instead of memorizing menus and parameters, the operator
states an objective within an **authorized scope**; the agent proposes a plan, and — only after the
operator approves — orchestrates the device step by step, capturing results as an auditable record.

The goal is to make legitimate hardware-security work **faster and more repeatable for authorized
teams**, while keeping a human firmly in control of every action.

## How it works (planned)

```text
Operator states an objective (within an authorized scope)
        │
        ▼
Agent drafts a plan  ──►  Operator reviews & APPROVES each step
        │                              │
        ▼                              ▼
Device executes the approved action ──► Results captured, logged, summarized
```

- **Human-in-the-loop by default** — nothing runs without explicit operator approval.
- **Scope-aware** — actions are tied to a defined engagement scope and target list.
- **Observable** — every command, parameter, and result is logged for review and reporting.

## Capability domains

The agent orchestrates the Flipper Zero's standard capability domains at a high level — it does not
add new hardware abilities, it makes the existing ones easier to plan, sequence, and document:

`Sub-GHz` · `125 kHz RFID` · `NFC` · `Infrared` · `GPIO` · `iButton` · `BadUSB`

## Design principles

- **Authorized scope first** — the tool assumes a defined, permitted engagement.
- **Approve before execute** — the operator confirms each action; safe/read-only enumeration is preferred before anything active.
- **Least privilege & safe defaults** — conservative parameters, clear confirmations.
- **Full audit trail** — logs suitable for evidence and client reporting.

## Responsible use

Flipper Agent is intended **only for authorized security testing and research** — assessments you
are explicitly permitted to perform on systems and hardware you own or have written authorization
to test.

- Obtain **written authorization** and define scope before any engagement.
- Comply with all applicable **laws and radio/RF regulations** in your jurisdiction; some capabilities are regulated or restricted.
- Do **not** use this project to access, disrupt, or interfere with systems, devices, or signals without permission.

Using this software means agreeing to operate within the law and your authorized scope.

## Status

- [ ] Repository scaffolding
- [ ] Agent ↔ device control layer
- [ ] Approval & audit-logging pipeline
- [ ] Scope / engagement model
- [ ] Reporting output

---

<div align="center">
<sub>A <b><a href="https://nullsquare.net">NullSquare</a></b> project · authorized security testing.</sub>
</div>
