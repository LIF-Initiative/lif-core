---
name: docs-index
description: Use this skill when a PR adds, removes, renames, or significantly rewrites a Markdown doc anywhere under `docs/`. The skill keeps `docs/INDEX.md` in sync with the actual file tree and the conventions in `docs/README.md`. Trigger phrases include: "update INDEX.md", "add to docs index", "the docs index needs updating", "this doc needs an INDEX entry", and any case where a doc-touching PR closes without an INDEX update.
---

# `docs-index` skill

Maintains `docs/INDEX.md` — the curated, one-line-per-doc table of contents for the repository — in sync with reality. Runs on PRs that add, remove, or significantly rewrite a Markdown doc.

`INDEX.md` is **not** auto-generated from a filesystem walk. Each entry is a curated one-liner (~150 chars, information-dense) that helps a reader (human or agent) decide whether to open the file. Auto-generation produces noise; this skill produces signal.

---

## When to fire

Run this skill when a PR diff shows any of:

- A new `*.md` file added under `docs/`
- An existing `*.md` file moved or renamed under `docs/`
- An existing `*.md` file deleted under `docs/`
- An existing `*.md` file rewritten in a way that materially changes its purpose or summary line (not for typos, formatting, or small additions)

Don't fire for:

- Changes to `docs/README.md` itself (the structural guide — its purpose doesn't shift entry-by-entry)
- Changes to per-layer `README.md` files (directory guides, not content)
- Changes inside `docs/external/` to binary files (`.docx`, `.pdf`, `.pptx`) — those don't get one-line-summary frontmatter
- Changes to `docs/external_refs/` (outside-LIF reference material; not curated)
- Changes to `docs/media/` (assets)
- Changes to `_template.md` files

---

## What the skill does

1. **Locate the changed docs.** Use the PR diff (or the staged change set) to identify added, removed, renamed, or rewritten Markdown files under `docs/`.
2. **For each added or rewritten doc:** read the file, extract a one-line summary. Prefer the doc's own first-line summary if it has one (the conventions in `docs/README.md` ask for this). Otherwise compose a ≤150-char summary from the doc's purpose section.
3. **For each removed or renamed doc:** find its current entry in `INDEX.md` and remove or update it.
4. **Place each entry under the correct section.** `INDEX.md` is organized by layer (`overview/`, `specs/`, `design/`, `operations/`, `agents/`, `external/`). Use the path of the file to determine its section.
5. **Preserve the existing structure of `INDEX.md`.** Don't reorder or restructure unless instructed. Append within the appropriate section, in alphabetical order by filename.
6. **Skip non-content files.** Per-layer `README.md`s, `_template.md`s, and binary external artifacts are listed in the "Not indexed" section, not enumerated entry-by-entry.
7. **Surface uncertainty.** If a doc's purpose is unclear or the right section is ambiguous, ask the user rather than guess. A wrong INDEX entry is worse than a missing one.

---

## Style for entries

- One line per file. Soft cap ~150 characters total (filename link + summary).
- Format: `- [\`filename.md\`](relative/path/filename.md) — one-line summary.`
- Summary is a *description of the doc's content*, not its purpose ("ADR 0017: Consumer SaaS isolation model — pooled isolation with user-level partitioning" rather than "Documents the isolation decision").
- Use the present tense and active voice.
- No marketing language. No hedging. No "this document discusses…".

Example:

```
- [`adapters.md`](design/components/adapters.md) — Adapters component design: pluggable input layer, contract for new source-system integrations, sample adapter walkthrough.
```

---

## What the skill does *not* do

- It does not validate filename conventions (kebab-case, no `LIF_` prefix, etc.). That's the doc author's responsibility, with `docs/README.md` as the reference.
- It does not approve or block PRs. It edits `INDEX.md` and surfaces unanswered questions; humans review.
- It does not modify any other doc. INDEX.md only.
- It does not regenerate INDEX.md from scratch. It updates the existing file in place to preserve manual entries and section ordering.

---

## Related conventions

- `docs/README.md` — the structural guide. Source of truth for layers, naming, and lifecycle rules.
- `AGENTS.md` (root) — pointer doc for AI tools, references this skill.
- `CLAUDE.md` (root) — repo-wide guidance.
