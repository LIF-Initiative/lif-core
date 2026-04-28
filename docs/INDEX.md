# Documentation Index

*Curated entry-point for every doc in this repo. One line per file, terse and information-dense — readable as a reference table, not as prose.*

> **Looking for the structural guide?** See [`README.md`](README.md) for the layer model, decision tree, and naming conventions. This file (`INDEX.md`) lists what's there now.
>
> **Maintained by the [`docs-index`](../.claude/skills/docs-index/SKILL.md) Claude skill.** When a doc is added, removed, or significantly rewritten, update its line here. Skill is the conventional path; manual updates are also fine.

---

## `docs/overview/` — Overview (orientation)

*Currently no docs in this layer. The first overview docs are scheduled to land as part of the documentation cleanup; see proposed list below.*

Planned: `vision.md`, `audiences.md`, `services-overview.md` (renamed from current `lif_services_overview.md`), `glossary.md`.

---

## `docs/specs/` — Specs (contracts)

*Currently no docs in this layer.*

Planned: `data-model-rules.md` (renamed from current `LIF_Data_Model_Rules.md`), `integration/` for adapter/MCP integration contracts.

---

## `docs/design/` — Design (how)

### `docs/design/adr/` — Architectural Decision Records

*Currently held in `docs/adr/` pending the directory move; see entries there for now.*

### `docs/design/components/` — Per-service design

*Currently held as top-level `LIF_Component_Design_Document-*.md` files pending rename; see top-level for now.*

### `docs/design/cross-cutting/` — Topics spanning services

*Currently no docs in this layer; planned topics include `auth.md`, `schema-loading.md`, `polylith-conventions.md`.*

---

## `docs/operations/` — Operations (runbooks + proposals)

### `docs/operations/guides/` — Runbooks

*Currently held in `docs/guides/` pending move.*

### `docs/operations/proposals/` — Proposed work

*Currently held in `docs/proposals/` pending move.*

---

## `docs/agents/` — Agent / MCP / LLM integration

*Currently no docs in this layer; the existing `buildathon-mcp-briefing.md` and `mcp-server-optimization-analysis.md` are candidates for relocation here.*

---

## `docs/external/` — Non-technical artifact archive

*Empty until external one-pagers and briefings are imported by the docs-team partner.*

---

## `docs/external_refs/` — Outside-LIF reference material

- *To be populated when the existing folder content is enumerated. The folder exists today.*

---

## Existing locations (to be relocated)

The following docs and folders exist in their original locations. They will be moved into the new structure in a follow-up commit (or follow-up PR) as part of this cleanup. Until then, this section is the authoritative pointer.

### Top-level (will move to `design/components/` with rename)

- [`LIF_Component_Design_Document-Adapters.md`](LIF_Component_Design_Document-Adapters.md) — Adapters component design.
- [`LIF_Component_Design_Document-Composer.md`](LIF_Component_Design_Document-Composer.md) — Composer component design.
- [`LIF_Component_Design_Document-Identity_Mapper.md`](LIF_Component_Design_Document-Identity_Mapper.md) — Identity Mapper component design.
- [`LIF_Component_Design_Document-LIF_API.md`](LIF_Component_Design_Document-LIF_API.md) — LIF API service design.
- [`LIF_Component_Design_Document-LIF_Orchestrator.md`](LIF_Component_Design_Document-LIF_Orchestrator.md) — LIF Orchestrator service design.
- [`LIF_Component_Design_Document-LIF_Query_Cache.md`](LIF_Component_Design_Document-LIF_Query_Cache.md) — LIF Query Cache service design.
- [`LIF_Component_Design_Document-LIF_Query_Planner.md`](LIF_Component_Design_Document-LIF_Query_Planner.md) — LIF Query Planner service design.
- [`LIF_Component_Design_Document-MDR.md`](LIF_Component_Design_Document-MDR.md) — MDR service design.
- [`LIF_Component_Design_Document-Translator.md`](LIF_Component_Design_Document-Translator.md) — Translator service design.

### Top-level files (will move into appropriate layer)

- [`COMMITTERS.md`](COMMITTERS.md) — Project committers and governance roles. (Stays at `docs/` top level — meta, not categorical.)
- [`LIF_Data_Model_Rules.md`](LIF_Data_Model_Rules.md) — LIF data model rules and capitalization conventions. → `specs/data-model-rules.md`
- [`LIF_Load_Testing.md`](LIF_Load_Testing.md) — Load testing notes for LIF services. → `operations/guides/load-testing.md`
- [`LIF_TShirt_Sizing.md`](LIF_TShirt_Sizing.md) — T-shirt sizing conventions for issues and proposals. → `operations/t-shirt-sizing.md`
- [`lif_services_overview.md`](lif_services_overview.md) — High-level catalog of LIF services. → `overview/services-overview.md`
- [`mdr-overview.md`](mdr-overview.md) — MDR overview for external evaluators. → `overview/mdr-overview.md`

### `docs/adr/` (will move to `design/adr/`)

- [`adr/README.md`](adr/README.md) — Index and conventions for the ADR collection.
- [`adr/_template.md`](adr/_template.md) — Top-level ADR template.
- [`adr/ai_architecture/0001-ai-architecture-overview.md`](adr/ai_architecture/0001-ai-architecture-overview.md) — AI architecture overview.
- [`adr/composer/0001-implement-as-module-component.md`](adr/composer/0001-implement-as-module-component.md) — Composer: implement as module component.
- [`adr/composer/0002-use-hierarchical-dot-path-for-fragment-paths.md`](adr/composer/0002-use-hierarchical-dot-path-for-fragment-paths.md) — Composer: hierarchical dot-path for fragment paths.
- [`adr/general/auth.md`](adr/general/auth.md) — ADR 0001: API and User Auth (Proposed).
- [`adr/metadata_repository/0001-base-lif-automation.md`](adr/metadata_repository/0001-base-lif-automation.md) — MDR: base LIF automation.
- [`adr/metadata_repository/0002-no-partner-management.md`](adr/metadata_repository/0002-no-partner-management.md) — MDR: no partner management in scope.
- [`adr/metadata_repository/0003-not-required-deprecation-advance-notice.md`](adr/metadata_repository/0003-not-required-deprecation-advance-notice.md) — MDR: deprecation advance-notice not required.
- [`adr/metadata_repository/0004-value-set-and-value-inclusions.md`](adr/metadata_repository/0004-value-set-and-value-inclusions.md) — MDR: value set and value inclusions.
- [`adr/metadata_repository/0005-unsupported-schema-formats.md`](adr/metadata_repository/0005-unsupported-schema-formats.md) — MDR: unsupported schema formats.
- [`adr/metadata_repository/0006-reverse-translation.md`](adr/metadata_repository/0006-reverse-translation.md) — MDR: reverse translation.
- [`adr/metadata_repository/0007-query-planner-integration.md`](adr/metadata_repository/0007-query-planner-integration.md) — MDR: query planner integration.
- [`adr/metadata_repository/0008-data-model-use-cases.md`](adr/metadata_repository/0008-data-model-use-cases.md) — MDR: data model use cases.
- [`adr/orchestrator/0001-orchestrator-for-demo.md`](adr/orchestrator/0001-orchestrator-for-demo.md) — Orchestrator: design for demo deployment.
- [`adr/translator/0001-initialization-vs-mdr-dependency.md`](adr/translator/0001-initialization-vs-mdr-dependency.md) — Translator: initialization vs MDR dependency.
- [`adr/translator/0002-query-translation.md`](adr/translator/0002-query-translation.md) — Translator: query translation approach.
- *Subdirectories `api/`, `data_model/`, `query_cache/`, `query_mapper/` currently hold only `_template.md` placeholders.*

### `docs/guides/` (will move to `operations/guides/`)

- [`guides/creating_a_data_source_adapter.md`](guides/creating_a_data_source_adapter.md) — How to write a LIF data source adapter.
- [`guides/demo_environment_update.md`](guides/demo_environment_update.md) — End-to-end runbook for promoting dev images to demo.
- [`guides/LIF_Add_Data_Source.md`](guides/LIF_Add_Data_Source.md) — Adding a new data source to a LIF deployment.

### `docs/media/`

- *Asset folder for diagrams and images. Not enumerated; referenced by other docs via relative links.*

---

## Not indexed

- `*/_template.md` — empty templates for new docs (referenced from layer READMEs).
- `*/README.md` — directory guides (entry points, not content). Top-level `docs/README.md` is the structural overview.
- `docs/external_refs/` — outside-LIF reference material (third-party standards, vendor docs); separate from curated content.
- `docs/media/` — image and diagram assets; referenced from other docs by relative link.
- `docs/external/` — non-technical artifacts in mixed formats (`.docx`, `.pdf`, `.pptx`); not enumerated entry-by-entry.
