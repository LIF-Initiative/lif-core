# Documentation Index

*Curated entry-point for every doc in this repo. One line per file, terse and information-dense — readable as a reference table, not as prose.*

> **Looking for the structural guide?** See [`README.md`](README.md) for the layer model, decision tree, and naming conventions. This file (`INDEX.md`) lists what's there now.
>
> **Maintained by the [`docs-index`](../.claude/skills/docs-index/SKILL.md) Claude skill.** When a doc is added, removed, or significantly rewritten, update its line here. Skill is the conventional path; manual updates are also fine.

---

## `docs/overview/` — Overview (orientation)

- [`mdr-overview.md`](overview/mdr-overview.md) — MDR overview for external evaluators: what the Metadata Repository does, how schemas flow, demo pointers.
- [`services-overview.md`](overview/services-overview.md) — High-level catalog of LIF microservices and how they fit together.

---

## `docs/specs/` — Specs (contracts)

- [`data-model-rules.md`](specs/data-model-rules.md) — LIF data model rules, capitalization conventions, reserved-word recognition by MDR.

---

## `docs/design/` — Design (how)

### `docs/design/components/` — Per-service design

- [`adapters.md`](design/components/adapters.md) — Adapters component: pluggable input layer, contract for source-system integrations.
- [`composer.md`](design/components/composer.md) — Composer component: data fragment assembly into LIF records.
- [`identity-mapper.md`](design/components/identity-mapper.md) — Identity Mapper component: cross-system identity resolution.
- [`lif-api.md`](design/components/lif-api.md) — LIF API service: outbound query interface for learner data.
- [`lif-orchestrator.md`](design/components/lif-orchestrator.md) — LIF Orchestrator service: pipeline coordination across data sources.
- [`lif-query-cache.md`](design/components/lif-query-cache.md) — LIF Query Cache service: caching layer for resolved queries.
- [`lif-query-planner.md`](design/components/lif-query-planner.md) — LIF Query Planner service: query routing and optimization.
- [`mdr.md`](design/components/mdr.md) — MDR (Metadata Repository) service: schema registry and contract authority.
- [`translator.md`](design/components/translator.md) — Translator service: source-data-to-LIF transformation engine.

### `docs/design/adr/` — Architectural Decision Records

- [`README.md`](design/adr/README.md) — Index and conventions for the ADR collection.
- [`_template.md`](design/adr/_template.md) — Top-level ADR template.
- [`ai_architecture/0001-ai-architecture-overview.md`](design/adr/ai_architecture/0001-ai-architecture-overview.md) — AI architecture overview.
- [`composer/0001-implement-as-module-component.md`](design/adr/composer/0001-implement-as-module-component.md) — Composer: implement as module component.
- [`composer/0002-use-hierarchical-dot-path-for-fragment-paths.md`](design/adr/composer/0002-use-hierarchical-dot-path-for-fragment-paths.md) — Composer: hierarchical dot-path for fragment paths.
- [`general/auth.md`](design/adr/general/auth.md) — ADR 0001: API and User Auth (Proposed).
- [`metadata_repository/0001-base-lif-automation.md`](design/adr/metadata_repository/0001-base-lif-automation.md) — MDR: base LIF automation.
- [`metadata_repository/0002-no-partner-management.md`](design/adr/metadata_repository/0002-no-partner-management.md) — MDR: no partner management in scope.
- [`metadata_repository/0003-not-required-deprecation-advance-notice.md`](design/adr/metadata_repository/0003-not-required-deprecation-advance-notice.md) — MDR: deprecation advance-notice not required.
- [`metadata_repository/0004-value-set-and-value-inclusions.md`](design/adr/metadata_repository/0004-value-set-and-value-inclusions.md) — MDR: value set and value inclusions.
- [`metadata_repository/0005-unsupported-schema-formats.md`](design/adr/metadata_repository/0005-unsupported-schema-formats.md) — MDR: unsupported schema formats.
- [`metadata_repository/0006-reverse-translation.md`](design/adr/metadata_repository/0006-reverse-translation.md) — MDR: reverse translation.
- [`metadata_repository/0007-query-planner-integration.md`](design/adr/metadata_repository/0007-query-planner-integration.md) — MDR: query planner integration.
- [`metadata_repository/0008-data-model-use-cases.md`](design/adr/metadata_repository/0008-data-model-use-cases.md) — MDR: data model use cases.
- [`orchestrator/0001-orchestrator-for-demo.md`](design/adr/orchestrator/0001-orchestrator-for-demo.md) — Orchestrator: design for demo deployment.
- [`translator/0001-initialization-vs-mdr-dependency.md`](design/adr/translator/0001-initialization-vs-mdr-dependency.md) — Translator: initialization vs MDR dependency.
- [`translator/0002-query-translation.md`](design/adr/translator/0002-query-translation.md) — Translator: query translation approach.
- *Subdirectories `api/`, `data_model/`, `query_cache/`, `query_mapper/` currently hold only `_template.md` placeholders.*

### `docs/design/cross-cutting/` — Topics spanning services

*Currently no docs in this layer; planned topics include `auth.md`, `schema-loading.md`, `polylith-conventions.md`.*

---

## `docs/operations/` — Operations (runbooks + proposals)

- [`t-shirt-sizing.md`](operations/t-shirt-sizing.md) — T-shirt sizing conventions for issues and proposals.

### `docs/operations/guides/` — Runbooks

- [`add-data-source.md`](operations/guides/add-data-source.md) — Adding a new data source to a LIF deployment: source schema, JSONata mappings, pipeline wiring.
- [`creating-a-data-source-adapter.md`](operations/guides/creating-a-data-source-adapter.md) — Reference for the data source adapter contract: what adapters are, what they receive, what they return.
- [`demo-environment-update.md`](operations/guides/demo-environment-update.md) — End-to-end runbook for promoting dev images to demo.
- [`load-testing.md`](operations/guides/load-testing.md) — Load testing notes for LIF services.

### `docs/operations/proposals/` — Proposed work

*Currently no committed proposals. Several proposal drafts exist in working trees and will land via separate PRs.*

---

## `docs/agents/` — Agent / MCP / LLM integration

*Currently no committed docs. Two candidate files exist in working trees and will land via separate PRs: `buildathon-mcp-briefing.md` and `mcp-server-optimization-analysis.md`.*

---

## `docs/external/` — Non-technical artifact archive

*Empty until external one-pagers and briefings are imported by the docs-team partner.*

---

## `docs/external_refs/` — Outside-LIF reference material

*Folder exists but its contents are currently untracked; will be enumerated when committed.*

---

## Top-level `docs/` (meta)

- [`COMMITTERS.md`](COMMITTERS.md) — Project committers and governance roles.

---

## Not indexed

- `*/_template.md` — empty templates for new docs (referenced from layer READMEs).
- `*/README.md` — directory guides (entry points, not content). Top-level `docs/README.md` is the structural overview.
- `docs/external_refs/` — outside-LIF reference material (third-party standards, vendor docs); separate from curated content.
- `docs/media/` — image and diagram assets; referenced from other docs by relative link.
- `docs/external/` — non-technical artifacts in mixed formats (`.docx`, `.pdf`, `.pptx`); not enumerated entry-by-entry.
