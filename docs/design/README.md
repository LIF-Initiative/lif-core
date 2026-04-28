# `design/` — Design Layer

**What goes here:** how LIF is built and why. Architectural decisions, per-service design, cross-cutting topics that don't belong to one service.

**What does *not* go here:** orientation (`overview/`), contracts (`specs/`), runbooks (`operations/`), or in-flight proposals (`operations/proposals/`).

**Layer rule:** Design explains *how, not what*. ADRs are immutable once Accepted; component and cross-cutting docs are living and may evolve with the codebase.

## Subdirectories

- [`adr/`](adr/) — Architectural Decision Records, numbered, with status. New decisions get a new ADR; superseding requires a new ADR rather than editing the old one.
- [`components/`](components/) — Per-service design docs. One file per microservice (`mdr.md`, `lif-api.md`, `translator.md`, etc.).
- [`cross-cutting/`](cross-cutting/) — Topics that span services: auth, schema loading, polylith conventions, observability.

## Conventions

- ADRs follow the template at [`adr/general/_template.md`](adr/general/_template.md).
- Component docs follow the kebab-case naming convention from the parent README — see [`components/README.md`](components/README.md) for the per-service file map.
- Cross-cutting docs are named for their topic, not for the services they touch (`auth.md`, not `mdr-graphql-auth.md`).
- Keep ADRs short (≤2 pages typically). If you need more space, the discussion belongs in a proposal first.
