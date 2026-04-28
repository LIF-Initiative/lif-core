# ADR 0001: Initialization vs MDR Dependency

Date: 2025-11-18

## Status
Accepted

## Context
The original design document for the updated translator states that the Translator would be initialized with the source and target data model schemas and that it would not be dependent on any other components.

In the Workflow Model section first paragraph, it said, "The **Translator** component is initialized with a corresponding source data model, target data model, and mapping document."

## Decision
It was decided that the translator would retrieve the source and target data model schemas along with the transformation mappings (aka translation instructions) when it is called by the orchestration pipeline.

## Alternatives
Alternatively, the translator could have been pre-initialized with this data, but that would not prove a live integration with the MDR for constantly changing data model schemas and mappings.

## Consequences
The consequence is that this may slow the performance of the translator if this data is not cached.

## References
N/A