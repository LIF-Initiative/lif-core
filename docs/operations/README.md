# `operations/` — Operations Layer

**What goes here:** runbooks, deployment guides, in-flight proposals, lessons learned. Anything about *running* the system day-to-day or *planning* near-term work.

**What does *not* go here:** architectural decisions (those become ADRs in `design/adr/`), service design (`design/components/`), data contracts (`specs/`), or finished external artifacts (`external/`).

**Layer rule:** Operations docs reflect *reality, not intent*. A runbook describes what works today; a future plan is a proposal until accepted, then it becomes an ADR and the proposal can be retired.

## Subdirectories

- [`guides/`](guides/) — How-to runbooks: deploys, environment setup, data source adapters, incident response.
- [`proposals/`](proposals/) — Proposed work, not yet accepted. Promoted to an ADR (and possibly a guide) on acceptance, or marked Withdrawn and kept for context.

## Conventions

- A guide that drifts from reality is worse than no guide. Mark it `Deprecated: YYYY-MM-DD` with a pointer to the current source of truth, or delete it.
- A proposal that's been accepted should reference the resulting ADR. The proposal itself can be retired.
- A proposal that's been rejected should be marked Withdrawn with a one-line reason — useful context for future authors who consider the same direction.
- LIF roadmap and status live in GitHub Issues, not in this folder. This folder is for prose: how-to runbooks and proposed designs.
