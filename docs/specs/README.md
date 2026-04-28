# `specs/` — Specs Layer

**What goes here:** contracts that external code (or external teams) can rely on. Data model rules, integration interfaces, schema conventions, behavior guarantees that are part of LIF's public surface.

**What does *not* go here:** implementation details (those go in `design/`), runbooks (`operations/`), or service-specific design choices (`design/components/`).

**Layer rule:** Specs describe *contracts, not implementation*. A spec answers "what can I depend on?" — not "how is it built?"

## Typical contents

- `data-model-rules.md` — capitalization conventions, identifier patterns, reserved fields, validation rules
- `integration/` — how external systems integrate with LIF (data adapters, MCP tool contracts, GraphQL schema rules)
- `lif-schema.json` references — pointers to the source-of-truth schema and what guarantees it carries

## Conventions

- Be precise about what's *guaranteed* vs. *currently true*. A spec that says "MDR returns JSON" without saying "this is part of the public contract" is just a description.
- Version specs explicitly when they change in breaking ways. Use ADRs in `design/adr/` to record the decision; specs reflect the resulting contract.
- Examples are part of the spec — include valid and invalid input/output samples.
