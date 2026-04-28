# ADR 0002: Use Hierarchical Dot Path for Fragment Paths

Date: 2025-07-25

## Status
Accepted

## Context
The original design document called for the fragment paths to be JSON Path expressions. However, the LIF record has a shallow hierarchy, and using JSON Path expressions would add unnecessary complication.

## Decision
We are deciding to use hierarchical dot path strings for fragment paths.

## Alternatives
The alternative would be to follow the original design and use JSON Path expressions for fragment paths.  This was rejected because of the unnecessary complication, especially given since the LIF hierarchy is very shallow (basically one level deep).

## Consequences
The fragment paths will be simpler to read and understand.  The implementation will not need to include a JSON Path library.

## References
N/A
