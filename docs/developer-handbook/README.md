# `docs/developer-handbook/` — Developer handbook

A guided reading path for developers starting feature work on LIF: how the parts fit, how to run them, and how to change them.

## Who it's for

A developer who knows Python and web APIs but is new to LIF, Polylith, the MDR and Dagster, and has no AWS access.

## Contents

**Backend** ([start here](backend/00-start-here.md)):

| Chapter | |
|---|---|
| [0. Start here](backend/00-start-here.md) | What LIF is, reading order, glossary |
| [1. Your development environment](backend/01-dev-environment.md) | Tools, checks, the local stack, resetting data |
| [2. The codebase map](backend/02-codebase-map.md) | Polylith, bricks, bases and projects, blast radius |
| [3. The data model and the MDR](backend/03-data-model-and-mdr.md) | Models, mappings, tenants, migrations |
| [4. Follow the data](backend/04-follow-the-data.md) | One query traced through every service |
| [5. Cross-cutting concerns](backend/05-cross-cutting.md) | Auth, configuration, schema loading, timeouts, logging |
| [6. How we work](backend/06-how-we-work.md) | Issues, commits, PRs, CI, ADRs |
| [7. Recipes](backend/07-recipes.md) | Add a field, a mapping, a data source, a service, a migration |
| [8. Debugging and traps](backend/08-debugging-and-traps.md) | Where to look first; mistakes we keep relearning |
| [9. Environments and deployment](backend/09-environments-and-deploys.md) | dev and demo, what a merge deploys |
| [10. Extending LIF](backend/10-extending-lif.md) | Which parts run on their own; where a new feature plugs in |

## How it relates to the rest of `docs/`

The handbook is an onboarding path *over* the other layers, not a seventh layer of content. It explains
how things fit together and links to the overview, specs, design and operations docs for the detail. When
a topic already has a good doc, the handbook links to it rather than repeating it.

## Keeping it true

Each chapter says which commit it was checked against. When you change something a chapter describes
(a port, a command, a workflow, the request path), update the chapter in the same PR. Notes tied to an
open issue (for example, a workaround) name the issue, so remove them when it closes.
