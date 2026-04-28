# ADR 0001: Base LIF Automation

Date: 2025-09-05

## Status
Accepted

## Context
There was a proposal in the initial draft of the MDR Design Document to support an automated, algorithmic process to incorporate updates to the base LIF data model.

Line 93 of the documentation previously stated: "The *LIF data model* will be maintained and governed by the steward and will be made available to the LIF community to extend as needed. Extensions and modifications made by LIF implementers will be reviewed by the steward <u>**through an automated, algorithmic process**</u> and incorporated into the *LIF data model*."

## Decision
We are deciding not to implement this feature at this time.

### Main Reasons
1. This is very complicated.

## Alternatives
At this time, we recommend that decisions regarding updating the base LIF data model are left to the steward and/or community rather than determined by an automated algorithm.

## Consequences
By not automating the process to decide what changes are incorporated into the base LIF data model, these decisions can be made by humans who have immediate context to the relevant use cases and experience in these types of decisions. While this could lead to the decision making process being slowing, it is likely to be more well thought out and have appropriate impact on downstream stakeholders.

## References
N/A
