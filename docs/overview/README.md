# `overview/` — Overview Layer

**What goes here:** orientation material for developers and devops joining LIF. Vision, research framing, audiences, services-at-a-glance, and other "you-are-here" content.

**What does *not* go here:** implementation details (those go in `design/`), data model rules (those are `specs/`), or external-audience artifacts (`external/`).

**Layer rule:** Overview is for *orientation, not implementation*. If you're explaining method calls or schema fields, you're in the wrong layer.

## Typical contents

- `vision.md` — what LIF is, why it exists, the research question that started the project
- `audiences.md` — who LIF serves (integrators, contributors, evaluators)
- `services-overview.md` — high-level catalog of microservices with one-paragraph summaries
- `personas.md` (or per-service personas) — user archetypes, where they're useful for orientation
- `glossary.md` — domain terms specific to LIF (LIF data model, OrgLIF, BaseLIF, etc.)

## Conventions

- Keep each doc readable in under 5 minutes. If it's longer, it's probably a design or specs doc.
- Cross-link to `design/` and `specs/` for depth, don't duplicate content.
- Diagrams welcome — store assets in `docs/media/` and reference them with relative links.
- Review at least quarterly. An out-of-date overview misleads new contributors silently.
