# Bruce Internal UI Routing

This repository-local pointer applies only to substantial Bruce internal
operational, admin, CRM, or backoffice web-panel UI work. It does not apply to
non-UI projects, public marketing sites, or native mobile apps.

The canonical source is the [Bruce UI Standard v2](https://github.com/dedtsss/agent-dispatch/blob/main/docs/bruce-ui-standard.md).
The canonical path is maintained on `agent-dispatch/main`.
Read it for the shared visual, interaction, accessibility, responsive, and
implementation-profile baseline. This file intentionally does not duplicate
that standard.

Inheritance and ownership:

- `docs/UX_CONTRACT.md` owns product behavior, information architecture,
  workflows, and domain-specific states.
- `docs/DESIGN.md` records project-specific visual decisions and justified
  deviations. The project inherits the canonical standard unless that file
  documents an approved override.
- The implementation owns framework-specific components and code. Choose the
  lightweight server-rendered or React/Ant profile only when it fits the
  project; neither is universal.

For a non-trivial UI change, read the UX contract first, then the canonical
standard, then the project design contract and implementation constraints.
