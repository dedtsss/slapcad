# [Project] UX Contract

This document owns product behavior, information architecture, workflows, and
domain-specific states. It is separate from the shared [Bruce UI Standard](https://github.com/dedtsss/agent-dispatch/blob/main/docs/bruce-ui-standard.md),
which supplies the visual and interaction baseline for applicable Bruce
internal web panels.

## Product scope and users

- Product/panel: [name]
- Primary users and jobs: [users/jobs]
- Out-of-scope surfaces or products: [scope]

## Information architecture

- Global sections: [project-specific sections]
- Entry points and drill-down targets: [routes/contexts]
- Mobile navigation model: [project decision]

## Core workflows

### [Workflow name]

1. [step and allowed responsibility]
2. [step and allowed responsibility]
3. [step and allowed responsibility]

Primary action and prerequisite for each step: [decision].

## States and recovery

Define the product meaning and recovery action for loading, empty, warning,
error, success, stale/dirty, and permission/validation states. Do not use raw
backend enums as the primary user-facing copy.

## Data and safety boundaries

- Data that may be shown: [rules]
- Data that must never be shown or logged: [rules]
- Persistence, auth, and domain invariants UI work must preserve: [rules]

## Accessibility and responsive acceptance

Record product-specific requirements in addition to the shared standard:
[keyboard, touch, modal/drawer, map/list alternative, widths, and evidence].
