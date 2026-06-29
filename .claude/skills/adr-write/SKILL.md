---
name: adr-write
description: Draft a new LIF Core ADR. Picks the right domain folder, fills that folder's _template.md, assigns the next per-folder number, and commits. Knows the per-domain-folder, per-folder-numbered ADR layout under docs/design/adr/.
argument-hint: <short-title-kebab-case>
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

Draft an Architecture Decision Record for LIF Core. ADRs live under [`docs/design/adr/`](../../../docs/design/adr/), **grouped by domain folder** (`general/`, `api/`, `composer/`, `data_model/`, `metadata_repository/`, `orchestrator/`, `query_cache/`, `query_mapper/`, `translator/`, `ai_architecture/`). Each folder numbers its own ADRs sequentially (`0001-…md`, `0002-…md`) and ships its own `_template.md`.

See [`docs/design/adr/README.md`](../../../docs/design/adr/README.md) for the house style (Michael Nygard format).

## Arguments

- `<short-title-kebab-case>` — the filename suffix, e.g. `tenant-search-path-routing`, `advisor-token-streaming`. Becomes `NNNN-<short-title>.md` once numbered.

## Phase 1 — Should this be a new ADR, and in which folder?

1. **Pick the domain folder.** Cross-cutting / foundational decisions go in `general/`. A decision scoped to one service or component goes in that domain's folder. If unsure which folder, ask the user.
2. **Scan that folder's existing ADRs** (read the closest 1-2 in full). If the decision merely *reverses or supersedes* an existing one, you'll still write a **new** ADR — but plan to mark the old one `Status: Superseded` (with a `References` link) rather than rewriting history. LIF ADRs are a chronological log, not mutable.
3. **Stop and ask the user** if it's genuinely a refinement that belongs as a small edit to an existing ADR, or if the folder choice is ambiguous: *"This looks like it supersedes `<domain>/NNNN`. New ADR marking that one Superseded, or edit in place? Reasoning: <one line>."* Don't draft until confirmed.

## Phase 2 — Gather decision context

You need four things (from the user or obvious session context). If any is vague, ask before drafting — a vague ADR is worse than none:

1. **Context** — the problem / constraint that prompted the decision. One paragraph.
2. **Decision** — what was decided. Be specific: name the pattern, data shape, or approach.
3. **Alternatives** — what else was considered, and why rejected.
4. **Consequences** — implications and trade-offs, both good and bad. If you can't name a downside, you haven't thought hard enough.

## Phase 3 — Pick the next number (per folder)

Numbering is **per folder**, not global:
```bash
ls docs/design/adr/<domain>/ | grep -E "^[0-9]{4}-" | sort -r | head -1
```
Next number = highest in that folder + 1 (zero-padded to 4 digits). If the folder has no numbered ADRs yet, start at `0001`. Surface the proposed `<domain>/NNNN` to the user before creating the file.

## Phase 4 — Draft

Copy that folder's template (each domain folder has its own `_template.md`):
```bash
cp docs/design/adr/<domain>/_template.md docs/design/adr/<domain>/NNNN-<short-title>.md
```
Fill the sections (the LIF template is **Date / Status / Context / Decision / Alternatives / Consequences / References**):

- **Date** — today (`YYYY-MM-DD`).
- **Status** — `Accepted` if locked; `Proposed` if you want review before it's binding.
- **Context / Decision** — from Phase 2; specific, not generic.
- **Alternatives** — at least one real alternative with a one-line "why rejected." Even "do nothing" counts.
- **Consequences** — at least one positive and one trade-off/risk.
- **References** — link the related issue(s)/PR(s) and any ADR this supersedes or builds on. If this supersedes another ADR, also edit that ADR's **Status** to `Superseded` and add a back-reference.

## Phase 5 — Index & cross-reference

- If [`docs/INDEX.md`](../../../docs/INDEX.md) inventories ADRs, add the entry (or invoke the `docs-index` skill to keep INDEX in sync).
- If the decision is load-bearing enough that implementers need it, add a `(see ADR <domain>/NNNN)` reference at the implementing spot in the relevant `docs/design/` or guide doc.

## Phase 6 — Commit

```bash
git add docs/design/adr/<domain>/NNNN-<short-title>.md
# plus any superseded ADR + INDEX/cross-ref edits
git commit -m "docs(adr): add <domain> ADR NNNN — <short title>"
```
Surface the file path and commit hash to the user.

## Rules

- **New decisions get new ADRs; supersede, don't rewrite.** Mark the old one `Superseded` and link it.
- **Numbering is per folder.** `translator/0002` and `composer/0002` coexist — don't globally renumber.
- **No empty Alternatives / Consequences.** One real row each, minimum.
- **Write the file before any index/catalog edit** — avoids dangling links if interrupted.

## When NOT to use this skill

- **A pattern already in use** → that's a `docs/design/` architecture doc, not an ADR. ADRs record *decisions*; arch docs describe *current state*.
- **A design exploration not yet decided** → that's a proposal under [`docs/operations/proposals/`](../../../docs/operations/proposals/) or `docs/proposals/`, not an ADR.
