# ADR 0004: Value Set and Value Inclusions

Date: 2025-09-05

## Status
Accepted

## Context
There was a proposal in the initial draft of the MDR Design Document for the MDR to support explicitly including/excluding value sets and values from an organization or partner data mode.

Capabilities and Features of the Organization's LIF data model used to include the line: "Ability to explicitly include entities and attributes<u>**, value sets, and values**</u> from the *LIF data model* for inheritance"

## Decision
We are deciding not to implement this feature at this time.

### Main Reasons
1. Value sets and values can be presumed to be included when its associated attribute is included.

## Alternatives
Value sets and values are automatically included in a data model when the relevant attribute is included.

## Consequences
By automatically including value sets and values when a relevant attribute is included, this reduces complexity and storage requirements for the MDR. However, this may limit the flexibility of value sets requiring that new ones are made more frequently. However, we also generally recommend against utilizing value sets altogether as often as possible as this can lead to data loss in translation.

## References
N/A
