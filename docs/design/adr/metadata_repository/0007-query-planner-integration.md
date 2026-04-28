# ADR 0007: Query Planner Integration

Date: 2025-11-18

## Status
Accepted

## Context
There was a proposal in the initial draft of the MDR Design Document for the MDR to provide information on data models and translation instructions to the **Query Planner** upon request.

In the Design Proposal section under the heading "At a high level, the MDR will support the following flow of data and relevant interactions with other LIF components." it previously stated, "Upon request by the **Query Planner**, the **MDR** will provide information on data models and translation instructions".

## Decision
We are deciding not to implement this feature at this time.

### Main Reasons
1. The Query Planner does not need the Open API schema from the MDR because the GraphQL API is requesting it directly.
2. The Query Planner does not need the translation instructions (aka transformation mappings) from the MDR because the Translator is requesting them directly.

## Alternatives
The GraphQL API directly calls the MDR for the OpenAPI schema, and the Translator directly calls the MDR for the transformation mappings (aka translation instructions).

## Consequences
There are no extraneous or inefficient integrations with the MDR requiring the data fetched from the MDR to be passed around.

## References
N/A
