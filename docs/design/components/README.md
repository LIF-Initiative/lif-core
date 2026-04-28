# `design/components/` — Per-Service Design Docs

One file per microservice. Each file describes the service's responsibilities, internal architecture, key interfaces, and notable design decisions. Cross-references to ADRs and specs are encouraged; duplicating content is not.

## Naming convention

Filenames are kebab-case. The `LIF_` prefix is preserved when "LIF" is part of the service's proper name (e.g., the service literally branded "LIF API"); otherwise dropped. The `Component_Design_Document-` boilerplate is dropped — the directory location and content describe the role.

| Service | Filename |
|---|---|
| Adapters | `adapters.md` |
| Composer | `composer.md` |
| Identity Mapper | `identity-mapper.md` |
| LIF API | `lif-api.md` |
| LIF Orchestrator | `lif-orchestrator.md` |
| LIF Query Cache | `lif-query-cache.md` |
| LIF Query Planner | `lif-query-planner.md` |
| MDR | `mdr.md` |
| Translator | `translator.md` |

## Contents per file

A component design doc typically contains:

1. **Purpose** — what this service does and why it exists
2. **Interfaces** — inbound (REST, GraphQL, MCP) and outbound (DBs, other services)
3. **Internal structure** — major modules, key classes, where to start reading the code
4. **Notable decisions** — design choices that surprise newcomers or have ADR links
5. **Operational notes** — things specific to this service that don't fit a general runbook

Keep each doc focused on its service. Multi-service topics (e.g., how all services authenticate to MDR) live in `design/cross-cutting/`.
