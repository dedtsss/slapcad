# [Project] UI Design Contract

This project inherits the [Bruce UI Standard](https://github.com/dedtsss/agent-dispatch/blob/main/docs/bruce-ui-standard.md)
when it is a Bruce internal web panel. This file records project-specific
visual choices and approved deviations; it does not copy the shared standard or
define product information architecture.

## Project context

- Product/panel: [name]
- Supported profile: [lightweight server-rendered | React/Ant | other]
- Approved direction and approver/date: [decision]
- Relevant UX contract: [`UX_CONTRACT.md`](UX_CONTRACT.md)

## Project-specific decisions

- Shell/navigation treatment: [decision]
- Typography changes: [decision]
- Density and responsive composition: [decision]
- Surface/radius/elevation changes: [decision]
- Component or map-specific treatment: [decision]

## Deviations from Bruce UI Standard

For each exception, record the rule, reason, scope, evidence, and approver. Do
not use this section to replace the shared baseline wholesale.

| Standard rule | Project deviation | Reason/evidence | Approved by/date |
| --- | --- | --- | --- |
| [rule] | [change] | [reason] | [approval] |

## Validation contract

- Required states: [loading / empty / warning / error / success / stale]
- Responsive widths: [relevant widths from the shared standard]
- Keyboard/focus checks: [checks]
- Browser screenshot and QA evidence: [links or paths]
