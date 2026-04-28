# `operations/proposals/` — Proposed Work

Proposed designs and changes that haven't been accepted yet. A proposal is a place to think out loud, evaluate alternatives, and reach alignment before committing to an ADR or implementation.

## Lifecycle

1. **Draft** — author opens a proposal as a markdown file. Status header reads `Status: Proposed`.
2. **Discussion** — review happens via PR comments or referenced issues.
3. **Accepted → ADR** — when the team accepts the direction, the relevant decision is captured as an ADR in [`../../design/adr/`](../../design/adr/). The proposal itself can be retired (marked `Status: Accepted, see ADR-NNNN`) or deleted.
4. **Withdrawn** — if rejected or no longer relevant, mark `Status: Withdrawn — <reason>` and keep for historical context. Future authors considering the same direction benefit from the prior thinking.

## Frontmatter

Every proposal includes a header:

```markdown
# Title

**Status:** Proposed | Accepted (see ADR-NNNN) | Withdrawn
**Date:** YYYY-MM-DD
**Author:** name or handle
```

## What goes here vs. an ADR

- **Proposal** — exploratory, may have multiple alternatives, may end up rejected
- **ADR** — accepted, immutable once Accepted, captures the decision and its consequences

Proposals are often longer than ADRs (more discussion, more context). The resulting ADR is short and focused on the decision itself.
