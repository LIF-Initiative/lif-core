# ADR 0002: Query Translation

Date: 2025-11-18

## Status
Accepted

## Context
The original design document states that the translator should convert a LIF data query into a source system data query.

In the Pipeline Tasks table, this task was initially assigned to the Translator, "Translate a LIF data query to a source data query".

It also said, "It translates the LIF query to a structure that matches the source system."

Under Functional Requirements, this used to be the first item in the list, "1. Translate LIF query to source system query".


## Decision
It is the Query Planner's responsibility to determine when a LIF data query corresponds to a non-LIF source system and plan for the Orchestrator to call the translator to retreive this data.

## Alternatives
Alternatively, the translator could convert LIF queries into source system queries, but we did not choose this because then the translator would be duplicating the efforts of the Query Planner and Orchestrator.

## Consequences
The consequence is that the Translator requires query planning and orchestration as supporting components.

## References
N/A