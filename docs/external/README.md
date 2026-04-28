# `external/` — Non-Technical Artifact Archive

**What goes here:** finished one-pagers, briefings, slide decks, and other artifacts intended for non-engineering audiences — partners, prospective adopters, evaluators, the curious public. Stored in-repo so they don't scatter across drives, inboxes, and SharePoint.

**What does *not* go here:**

- Technical reference docs aimed at integrators (those are `specs/` and `design/`)
- Reference material from outside LIF (third-party standards live in `external_refs/`)
- Internal team status, planning, or runbooks (`operations/`)

**Layer rule:** Finished artifacts for outside audiences. If you're still drafting it for review, do that in a proposal or wherever the source-of-truth editor is.

## Mixed formats by design

This is the one folder in `docs/` that intentionally contains non-Markdown files. Markdown is preferred when:

- The content is short and benefits from PR review
- Multiple people may iterate on the wording
- The audience is "curious readers in the repo"

Binary formats (`.docx`, `.pdf`, `.pptx`) are appropriate when:

- The artifact is finalized and shared as-is
- Layout, branding, or interactivity matters
- The master version lives elsewhere (SharePoint, Google Drive) and the repo holds a snapshot

## Provenance

If a file is a snapshot of a master version edited elsewhere, note that. For markdown, an italic line at the top:

> *Master version: <link>. This is a snapshot for in-repo reference; refresh when the master changes.*

For binary files, capture the source in the commit message and (optionally) a sibling `<filename>.SOURCE.md` with provenance details.

## Versioning expectations

Git diffs binary files poorly or not at all. The pattern is "commit a replacement," not "incremental edits." If the artifact is point-in-time, suffix the filename with the date or version (`partner-deck-2026-04.pdf`, not `partner-deck.pdf`).

## Naming

Kebab-case for all filenames, including binaries (`lif-overview-one-pager.docx`, not `LIF Overview One Pager.docx`). Even though binaries can't be diffed, consistent naming keeps the directory scannable.

## Repo size

Binaries grow repo size monotonically. If this folder gets past ~20MB cumulative, evaluate Git LFS. Don't preemptively wire LFS — wait until volume justifies it.
