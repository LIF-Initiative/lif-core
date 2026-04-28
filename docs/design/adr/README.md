
# `adr/` Directory

# Architecture Decision Records (ADRs)

This directory captures Architecture Decision Records (ADRs) for the LIF system. ADRs document significant architectural choices made throughout the development of this codebase, along with their context and consequences.

ADRs are designed to provide a clear, chronological log of technical decisions — helping current and future developers understand why things are the way they are.

## What is an ADR?

An Architecture Decision Record is a short document that explains:
- What decision was made
- Why it was made at the time
- What options were considered
- What trade-offs were accepted
- What the impact of the decision is

They follow the convention popularized by [Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions), often written in a simple Markdown format.

## Why Use ADRs?

-   Capture institutional knowledge
-   Aid onboarding and future audits
-   Improve transparency and accountability
-   Avoid repeated debates

## Example Structure

ADRs may be grouped by scope:

<pre lang="markdown"> <code> 
adrs/  
├── 0001-general-foundation.md # Broad decisions across the LIF system  
├── query_cache/  
│ └── 0002-query-cache-design.md # Decisions for LIF Query Cache  
├── query_mapper/  
│ └── 0003-query-mapper-interface.md # Decisions for LIF Query Mapper  
└── ...
</code> </pre>

- Top-level ADRs represent cross-cutting or foundational decisions.
- Subdirectories hold ADRs for individual LIF components or services, such as Query Mapper, Query Cache, or Planner.

Each ADR filename is prefixed with a sequential number for easy tracking.

## Writing an ADR

The following format is recommended:

    # ADR 000X: Title of the Decision
    
    Date: YYYY-MM-DD
    
    ## Status
    Proposed | Accepted | Superseded | Deprecated
    
    ## Context
    What is the background or the problem that this decision aims to address?
    
    ## Decision
    What is the architectural decision being made?
    
    ## Alternatives
    What other options were considered, and why were they rejected?
    
    ## Consequences
    What are the implications, trade-offs, or side effects of this decision?
    
    ## References
    (Optional) Link to related issues, discussions, or documents.

## Best Practices

-   Keep ADRs short, focused, and consistent.
-   Write them as decisions are made, not retroactively.
-   Do not rewrite history. Supersede previous ADRs if decisions change.
-   Favor clarity over completeness.

## Related Links
-   [ADR GitHub Template (by joelparkerhenderson)](https://github.com/joelparkerhenderson/architecture_decision_record)
