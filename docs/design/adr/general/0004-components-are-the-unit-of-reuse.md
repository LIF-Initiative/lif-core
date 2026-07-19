# ADR 0004: Components are the unit of reuse — a bare, composable core; deployment and demo concerns decorate at the edges

Date: 2026-07-16

## Status

Proposed

## Context

LIF's goal is a set of **functional, independently useful components** that adopters can combine into different workflows — an LLM Advisor, populating a learner wallet, a data-export integration — while running only the pieces they need alongside their own infrastructure.

Our own demos need more than the bare capability: Cognito for interactive auth, a curated set of demo learners, seed data, a warm cache. The risk is that this demo/deployment scaffolding creeps *into* the reusable units, so that a would-be adopter who wants only (say) the Learner Data Export service is forced to stand up Cognito, MDR, and demo fixtures just to run it. That would defeat the independence goal and make LIF hard to explain to external stakeholders evaluating "which parts can I actually use?"

We already have the machinery to avoid this — the [Polylith](https://polylith.gitbook.io/) layering and pluggable auth bricks (`mdr_auth`, `api_key_auth`) — but the *principle* has been implicit. This ADR makes it explicit, both as a discipline we hold while building and as a statement of how LIF is meant to be consumed. It generalizes the specific decisions in [ADR 0002](0002-lif-control-plane-vs-mdr-host.md) (don't make MDR a fleet-wide auth dependency) and [ADR 0003](0003-advisor-queries-query-planner-directly.md) (consumers talk to the service whose contract fits them).

## Decision

**The component is the unit of reuse; the base/project is the unit of deployment; deployment- and demo-specific concerns are composed at the edges, never baked into the reusable core.**

1. **Components are bare capability.** A component (`components/lif/*`) is pure logic with a public Python API — no I/O wiring, no auth, no environment assumptions, no demo data. It does one thing and can be adopted on its own.
2. **Bases/projects assemble workflows.** A base composes components into a runnable shape; a project ships it. "LLM Advisor" and "wallet population" are different bases composing overlapping components. Assembly — not the component — is where a workflow is defined.
3. **Decorate at the edges.** Cross-cutting and environment concerns are added by composition at the base/project layer:
   - **Auth** is pluggable middleware bricks (`api_key_auth`, `mdr_auth`, and the forthcoming `cognito_auth`, #1034) that a base layers on; a service is bare by default and gains an auth flavor by composition.
   - **Demo data** lives in clearly demo-scoped bricks (`demo_personas`, #1055) consumed only by demo-facing bases.
   - **Infrastructure** (Cognito, cache warming, seed data) lives in deployment/orchestration (`cloudformation/`, Dagster fixtures, `sample_data/`), not in components.
4. **Dependency direction is the enforceable rule.** Decoration/demo bricks may depend on core components; **core components must never depend on demo/deployment bricks.** This is what keeps every capability deployable standalone. Keep demo-only bricks clearly identifiable so this can be checked (`poly` dependency checks; a `demo_`-style naming/segregation convention).
5. **Config over forks.** The same artifact runs bare or enhanced based on composition + runtime configuration — not a forked codebase and not build-time-baked environment config (see the advisor-app baked-URL regression, #1047). One image, behavior chosen at deploy time.

## Alternatives

- **Monolithic services with built-in auth/demo.** Rejected: not adoptable piecemeal; forces adopters to take infrastructure they don't want; the exact coupling ADR 0002 pushed back on.
- **A dedicated "demo framework" / wrapper layer.** Rejected as overkill: composition at the base/project layer already provides decoration; a bespoke framework adds ceremony without capability. The discipline (rules 1 + 4) is enough.
- **Remote/S3-hosted config or fixtures for portability.** Rejected as the default: it reintroduces an external runtime dependency and breaks self-contained Docker/portable deployment. Compiled-in bricks are preferred for small, stable, demo-scoped data; remote config is reserved for large or frequently-changing operational config.

## Consequences

- Adopters can select components and run them against their own infrastructure; the answer to "which parts can I use?" is "any component, composed into a base you assemble."
- There is a clear, non-contaminating home for demo scaffolding, so demos can be rich without compromising the reusable core.
- Enforcement is mostly discipline + tooling: keep components free of auth/env/demo assumptions, segregate demo bricks by name, and let `poly` catch a core→demo dependency.
- Nuance: a browser client can't import a Python brick, so a base exposes brick data via a small endpoint (e.g. the demo-persona list for the LDE playground). The brick remains the single source; the base decorates with an HTTP surface — consistent with this ADR.
- Instances of this ADR in practice: `demo_personas` (#1055), the `cognito_auth` decoration + composite LDE middleware (#1034, LDE bare on `api_key_auth`, enhanced with Cognito by composition), and the control-plane extraction (ADR 0002 / #1041).

## References

- [ADR 0002 — LIF control plane vs MDR host](0002-lif-control-plane-vs-mdr-host.md)
- [ADR 0003 — Advisor queries the Query Planner directly](0003-advisor-queries-query-planner-directly.md)
- [`ARCHITECTURE.md`](../../../../ARCHITECTURE.md) and the Polylith layering (`components/` / `bases/` / `projects/`)
- Instances: `components/lif/demo_personas` (#1055), `cognito_auth` + composite LDE middleware (#1034), advisor-app build-time-config regression (#1047)
