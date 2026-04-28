# ADR 0003: Not Required Deprecation Advance Notice

Date: 2025-09-05

## Status
Accepted

## Context
There was a proposal in the initial draft of the MDR Design Document for the MDR to support a validation requiring that deprecation date is configurable so that it MUST be a specific number of days in the future. There was also a proposal in the initial draft of the MDR Design Document for the MDR to support the ability to send alerts to people when deprecation dates are nearing.

Functional Requirements regarding changes to the Base LIF data model over time used to include the following statement: "<u>**Ability to ensure that the deprecation date is not earlier than a configurable minimum number of days**</u>"

Functional Requirements regarding changes to the Organization's LIF data model over time used to include the following statements:
- <u>**Similar to the *LIF data model*, support the ability to enforce that the deprecation date is not earlier than a configurable minimum number of days**</u>
- <u>**Ability to alert users when the deprecation date falls within a configurable timeframe for model elements inherited from the *LIF data model**</u>

## Decision
We are deciding not to implement this feature at this time.

### Main Reasons
1. This is a low priority. The use cases around the deprecation of LIF data model elements are not yet clear.
2. The MDR does not currently support authentication, which would be a prerequisite to being able to send notifications to other authorized instances.

## Alternatives
At this time, we recommend that the steward, community, and implementing organizations utilize their expertise to consider the downstream impacts of deprecating any portion of the LIF data model and appropriately notify anyone affected.

## Consequences
In the event that the steward, cummunity, and implementing organizations are not fully aware of all downstream LIF stakeholders, they may be adversely impacted by the premature deprecetation of data model elements. However, by not requiring a deadline for this at this time, these folks can consider the downstream impacts of deprecation and determine how they feel it would be best to handle these cases.

## References
N/A
