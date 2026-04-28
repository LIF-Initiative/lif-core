# ADR 0001: Implement as Module Component

Date: 2025-07-25

## Status
Accepted

## Context
The original design document called for the Composer to be implemented as a standalone service that could be used by multiple LIF components.  Currently, the Composer is only used by the Query Cache.

## Decision
We are deciding to implement the Composer as a polylith component and using it as a shared module, instead of implementing it as a separately deployed service.

## Alternatives
The alternative would be to implement the Composer as a separately deployed standalone service.  This was rejected because of the associated overhead, especially since there is currently only a single user (Query Cache).

## Consequences
The Query Cache can simply import the Composer module and use it directly, rather than having to call out to a separate service.  The Composer will not need to be deployed as a separate service, with the associated overhead.

## References
N/A
