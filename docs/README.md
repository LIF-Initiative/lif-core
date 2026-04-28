# `docs/` — Documentation Guide

This directory holds documentation for the LIF (Learner Information Framework) repository. It is organized so that any reader — human or agent — can place a new doc, find an existing one, or recognize a stale one in under a minute.

If you arrived here looking for a specific file, start at [`INDEX.md`](INDEX.md). This README explains the *shape* of the docs; INDEX is the curated table of contents.

---

## Mental model

LIF is an open-source ecosystem of microservices for aggregating learner data across SIS, LMS, HR, and other source systems. The docs follow that posture: practical, oriented to integrators and contributors, no commercial-product surface.

Every doc answers one of these questions:

| Layer | Question | Audience |
|---|---|---|
| **Overview** | Why does LIF exist? What does the system look like at a glance? | Developers and devops orienting themselves to the project |
| **Specs** | What's the contract? What rules govern the data model and integration boundaries? | Anyone implementing against LIF or extending the data model |
| **Design** | How is it built? Why these architectural choices? | Engineers contributing to or operating the codebase |
| **Operations** | What's running, what's planned, how do we deploy and recover? | Engineers and devops on the day-to-day |
| **Agents** | How do MCP servers and LLM-facing surfaces work? What conventions apply to AI tooling? | Agent developers and integrators |
| **External** | What do we hand to non-engineering audiences (partners, evaluators, the curious)? | External readers (and us, when we need to stop hunting through email for that one-pager) |

If a doc doesn't fit one of these, the structure is wrong — open an issue rather than inventing a seventh category.

---

## Directory layout

```
docs/
  README.md           — this file (the structural guide)
  INDEX.md            — curated entry-point listing every doc with a one-line summary
  overview/           — Overview layer: what LIF is, why it exists, services-at-a-glance
  specs/              — Specs layer: data model rules, integration contracts
  design/             — Design layer: ADRs + component design docs
    adr/              — Architectural Decision Records (numbered, with status)
    components/       — Per-service design docs (one file per microservice)
    cross-cutting/    — Topics that span services (auth, schema loading, polylith)
  operations/         — Operations layer: runbooks, deployment guides, in-flight proposals
    guides/           — How-to runbooks (deploys, data source adapters)
    proposals/        — Proposed work, not yet committed; promote to ADR or guide on acceptance
  agents/             — MCP servers, AGENTS.md companion guidance, agent-context for this repo
  external/           — Non-technical artifact archive: one-pagers, briefings, decks (mixed formats)
  external_refs/      — Reference material from outside LIF (CEDS standards, etc.)
  media/              — Images, diagrams, supporting assets
```

Each layer's directory has its own `README.md` describing what belongs there and naming conventions specific to that layer.

---

## How to decide where a doc goes

Walk this decision tree top-to-bottom and stop at the first match:

1. **Is it a one-pager, briefing, slide deck, or other artifact aimed at a non-engineering audience?** → `external/`
2. **Is it reference material from outside LIF (a published standard, a third-party schema, etc.)?** → `external_refs/`
3. **Is it explaining what LIF is, why it exists, or what the system looks like at a glance?** → `overview/`
4. **Is it defining a contract — data model rules, integration interface, behavior guarantee?** → `specs/`
5. **Is it an architectural decision (status, alternatives, consequences)?** → `design/adr/`
6. **Is it the design of one specific service or component?** → `design/components/`
7. **Is it a cross-cutting design topic (auth, schema loading, observability)?** → `design/cross-cutting/`
8. **Is it a runbook or how-to for deploying, operating, or extending the system?** → `operations/guides/`
9. **Is it a proposal that hasn't been accepted yet?** → `operations/proposals/`
10. **Is it about MCP, agent integration, or AI-facing surfaces?** → `agents/`
11. **None of the above?** Open an issue describing the doc; the structure may be missing a category.

---

## Layer rules

Each layer has one rule that constrains its scope. Keeping these rules in mind prevents docs from sprawling.

- **Overview** → orientation, not implementation. If you're explaining method calls, you're in the wrong layer.
- **Specs** → contracts, not implementation. Specs describe behavior an external party can rely on; design docs describe how that behavior is achieved.
- **Design** → how, not what. ADRs are immutable once Accepted (write a new ADR to supersede). Component and cross-cutting docs are living and may evolve.
- **Operations** → reality, not intent. A runbook describes what *works today*; if it describes a future plan, it's a proposal.
- **Agents** → conventions for the agent surface, not the LIF data model itself. Tools, prompts, capability boundaries.
- **External** → finished artifacts for outside audiences. Mixed formats (`.md`, `.docx`, `.pdf`, `.pptx`). Not technical reference.

---

## Filename and structure conventions

- **Kebab-case** for all new filenames: lowercase, hyphen-separated. Acronyms are lowercased as single words (`mdr`, `lif-api`, `mcp-server`).
- **Drop the `LIF_` prefix** unless "LIF" is part of the proper name of the subject (e.g., `lif-api.md`, `lif-orchestrator.md`). For components whose name doesn't include "LIF" (Translator, Composer, MDR, Adapters), drop the prefix entirely.
- **No `Component_Design_Document-` boilerplate** in filenames. The directory location and content describe the role.
- **Date-suffix point-in-time artifacts** (`partner-deck-2026.pdf`, not `partner-deck.pdf`). Markdown design docs that supersede each other use ADR numbering instead.
- **Frontmatter for ADRs** (status, date, alternatives, consequences) — see `design/adr/_template.md`.
- **One-line summary at the top of every markdown doc** — used as the entry in `INDEX.md`. Keep it under ~150 characters.

Existing files that don't follow these conventions are legacy and may be renamed in a separate cleanup pass. New docs follow the conventions immediately.

---

## Important distinctions

A handful of distinctions come up often enough to be worth pinning down.

| Distinction | Where each lives |
|---|---|
| **Spec vs. Design** | Specs (`specs/`) are contracts external code can rely on. Design (`design/`) is how we implement them. The data model rules are a spec; the schema loader's caching strategy is a design topic. |
| **Proposal vs. ADR** | A proposal (`operations/proposals/`) is exploratory; it's not yet a commitment. Once accepted, the relevant decision is captured as an ADR (`design/adr/`) and the proposal can be retired or kept as historical context. |
| **Overview vs. Specs** | Overview is for orientation ("here's what MDR does at a glance"). Specs describe enforceable contracts ("MDR rejects identifiers that don't match this regex"). |
| **External docs vs. external_refs** | `external/` is *our* artifacts aimed at outside audiences. `external_refs/` is *outside* artifacts (third-party standards, vendor specs) we reference. |
| **CLAUDE.md vs. AGENTS.md vs. agents/** | `CLAUDE.md` (root) and `AGENTS.md` (root) are pointer docs read by AI tools at the start of a session. `docs/agents/` holds the actual content those pointers reference (MCP tool docs, prompt patterns). Don't duplicate content; cross-link. |

---

## Lifecycle

- **A proposal becomes an ADR** when the team accepts the direction. Promote by writing the ADR; mark the proposal Superseded with a link to the ADR, or delete it.
- **An ADR becomes Superseded** by writing a *new* ADR that supersedes it. Don't edit accepted ADRs except for typos and clarifications. Add a `Status: Superseded by ADR-NNNN` line.
- **A guide goes stale** when reality drifts from it. Mark it deprecated with a date and a pointer to the current source of truth, or delete it. A wrong runbook is worse than no runbook.
- **An overview doc gets reviewed quarterly** (or whenever the system changes substantially). Catch silent staleness before someone onboards from it.

---

## Maintaining `INDEX.md`

`INDEX.md` is a curated table of contents — terse, one line per doc, ~150 chars. It is **not** auto-generated from filesystem listing. New docs need a hand-written entry; rewritten docs need their entry refreshed.

Maintenance is owned by the [`docs-index`](../.claude/skills/docs-index/) Claude skill, which fires on PRs that add, remove, or significantly rewrite a doc. The skill is the conventional path; manual updates are also fine.

---

## Cross-references to other top-level files

- [`CLAUDE.md`](../CLAUDE.md) — agent-facing repo instructions: project structure, build/test commands, schema conventions, deployment notes. Read by agents starting a session in this repo.
- [`AGENTS.md`](../AGENTS.md) — short pointer doc for non-Claude agents. Cross-links to CLAUDE.md, this README, and INDEX.md.
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — code-contribution rules: commits, PRs, code style. Cross-references this README for documentation contributions.

---

## Evolution

This structure will change as the project does. Two rules govern how:

1. **Don't add a new top-level layer without retiring or merging an existing one.** Six layers is already a lot.
2. **Refactor in batches, not piecemeal.** Mass-renaming half the docs over a week is worse than a single coherent rename PR.

If the structure becomes confusing, return to the mental model: **WHY → WHAT → HOW → RUN**, plus the agent surface and external archive.
