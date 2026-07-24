# ADR 0005: Product surfaces and component tiers — UIs by audience; product-tier vs demo-tier components

Date: 2026-07-16

## Status

Proposed

## Context

LIF now has multiple frontends and services and a recurring question: **where does a given page or service live, and is it a product or a demo scaffold?** Concretely — the API-keys page (#1035/#1039) and LDE test/export playground (#1036) were built into the **MDR UI** for expedience, but they are showcase features, not schema-management. And the Advisor: the chatbot is a compelling demo but not, on its own, a product — whereas the semantic-search **MCP server** it calls *is* something a customer would embed in their own assistant.

This ADR extends [ADR 0004](0004-components-are-the-unit-of-reuse.md) (components are the unit of reuse) with two orthogonal distinctions: **who a UI is for** (audience) and **whether a component is product or demo** (tier). It generalizes [ADR 0002](0002-lif-control-plane-vs-mdr-host.md) (control plane) and [ADR 0003](0003-advisor-queries-query-planner-directly.md).

## Decision

### Three product surfaces, by audience

| UI | Audience | Tier | Notes |
|---|---|---|---|
| **MDR UI** | External customers | Product (SaaS) | Schema explorer + cross-schema mapper. High standalone value. **Kept clean** — no demo/showcase features. |
| **Demo app** | External evaluators (credentialed, but public-facing) | Showcase | Advisor + API-key management + LDE tester + future demo screens. **Grows out of the existing `advisor-app`**, not greenfield. |
| **Control plane** | Internal ops / dev | Internal | Monitoring + key/identity admin for the demo fleet. Its own UI, built **when the control-plane service (ADR 0002 / #1041) exists** — not before. |

The demo app is **external-facing** (evaluators request credentials), so it is *not* merged with the internal control plane.

### Two component tiers

- **Product / reusable tier** — MDR, the **MCP server**, the Query Planner, LIF datatypes, the auth bricks. A customer runs these against their own infrastructure.
- **Demo tier** — the **`advisor-api`**, the demo frontend, `demo_personas` (#1055), the `/demo/personas` endpoint. These exist to *showcase* the product tier; a customer never deploys them.

**Dependency rule (sharpens ADR 0004):** demo-tier may depend on product-tier; **product-tier must never depend on demo-tier.** This is what keeps the MCP server, MDR, and the Query Planner shippable without any demo scaffolding.

### The Advisor, specifically

The **MCP server is the product** — the reusable AI surface a customer embeds in their own assistant. The **Advisor chatbot and `advisor-api` are demo-tier** — the showcase and its backend. We do **not** invest in the chatbot as a standalone product; we invest in the MCP server, and the Advisor demonstrates it.

### Shared frontend foundation

Extract a shared frontend foundation — design system, Cognito auth, api-client patterns, and reusable service clients (e.g. demo-persona / LDE) — so the surfaces **compose rather than duplicate**. This is the frontend analog of ADR 0004 and is what makes "grow the demo app from `advisor-app`" cheap.

## Alternatives

- **Three separate greenfield SPAs.** Rejected as the *starting* point: building three shells before the control-plane service exists is premature, and greenfielding the demo app ignores that `advisor-app` already is one.
- **One shell with role-gated modules.** Rejected: an external MDR-SaaS customer's bundle would carry ops/demo code — violates "run only what you need" at the UI layer.
- **Merge demo + ops into one internal console.** Rejected: the demo app is **external**-facing (credentialed evaluators), the control plane is **internal** — different audiences and exposure.
- **Thin demo app that deep-links/embeds MDR.** Viable as a tactic within the demo app; not a replacement for the decomposition.

## Consequences

- Every page/service has a clear home. The keys page (#1035/#1039) and LDE playground (#1036) are **demo-app** features currently sitting in the MDR UI; they migrate out so MDR stays the clean SaaS surface. **Near-term they stay in mdr-frontend, tagged for migration**, so the LDE work isn't blocked on the reorg.
- The MCP server is the AI **product** surface; effort goes there, not into the chatbot as a product.
- Realizing this cheaply **requires** the shared frontend foundation — otherwise `advisor-app` and `mdr-frontend` keep duplicating auth/design/routing.
- The control-plane UI is deferred until its service (#1041) lands.

Sequencing: (1) leave keys/LDE in mdr-frontend, tagged; (2) extract the shared frontend foundation; (3) evolve `advisor-app` → demo frontend and migrate keys/LDE, MDR sheds them; (4) control-plane UI with #1041.

## References

- [ADR 0004 — Components are the unit of reuse](0004-components-are-the-unit-of-reuse.md)
- [ADR 0002 — LIF control plane vs MDR host](0002-lif-control-plane-vs-mdr-host.md) (#1041)
- [ADR 0003 — Advisor queries the Query Planner directly](0003-advisor-queries-query-planner-directly.md)
- Pages currently mis-homed in the MDR UI: API keys (#1035/#1039), LDE playground (#1036/#1060). Demo-tier bits: `advisor-api`, `demo_personas` (#1055), `/demo/personas`. Product AI surface: `bases/lif/semantic_search_mcp_server`.
