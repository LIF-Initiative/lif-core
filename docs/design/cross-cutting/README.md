# `design/cross-cutting/` — Cross-Cutting Design Topics

Design topics that span multiple services or aren't owned by a single component. Auth, schema loading, observability, polylith conventions, deployment topology.

## What goes here

A topic belongs in `cross-cutting/` if either:

- Two or more services share the same approach and the doc would otherwise be duplicated, or
- The topic is repository-wide (build system, testing strategy, dependency policy) rather than service-specific.

If the topic is a single service's internal concern, it belongs in [`components/`](../components/) instead.

## Naming convention

Files are named for the topic, not for the services involved. Examples:

- `auth.md` — how all services authenticate (API keys, Cognito, legacy JWT)
- `schema-loading.md` — how services load the OpenAPI schema from MDR
- `polylith-conventions.md` — brick boundaries, naming, when to extract a component
- `observability.md` — logging, metrics, tracing conventions

Avoid filenames that lock to specific services (`mdr-graphql-auth.md`); those should be split into a service-specific design doc and a cross-cutting one if there's shared content.
