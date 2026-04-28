# ADR 0006: Reverse Translation

Date: 2025-09-05

## Status
Accepted

## Context
There was a proposal in the initial draft of the MDR Design Document for the MDR to support the ability to reverse data model transformation mappings to go from LIF to source.

Functional Requirements for Source to LIF transformation used to state: "Ability to maintain transformation rules from source data models to organization-specific LIF models <u>**and from organization-specific LIF models back to source data models**</u>."

Line 281 of the documentation previously stated: "**Mappings:** This represents mapping and transformation logic between the *source data models and organization-specific LIF model*<u>**, and vice versa where the transformation is not inherently reversible**</u>."

## Decision
We are deciding not to implement this feature at this time.

### Main Reasons
1. This goes significantly beyond parity with the previous iteration of the translator.
2. More research will need to be done to determine the level of effort for this with the JSONata based translator.
3. The use cases around this functionality are not clear at this time.

## Alternatives
None at this time

## Consequences
If someone had the use case of wanting to translate from LIF back to a source schema, this is not currently supported.

## References
N/A
