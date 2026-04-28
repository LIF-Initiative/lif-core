# `operations/guides/` — Runbooks

How-to runbooks for deploying, operating, extending, or recovering LIF. Each guide is a recipe: a reader follows the steps and gets a known outcome.

## What goes here

- Deployment guides (`demo-environment-update.md`, `dev-environment-bootstrap.md`)
- Adapter authoring guides (`creating-a-data-source-adapter.md`)
- Incident response runbooks (`mdr-database-recovery.md`)
- Extension recipes ("how to add a new LIF data source")

## What does *not* go here

- **Design rationale** — runbooks are about doing, not deciding. Why a step exists belongs in an ADR.
- **Reference material** — schema specs, API references. Those go in `specs/` or service docs.
- **Status / progress tracking** — that's GitHub Issues territory.

## Conventions

- Lead with prerequisites. A reader should know in 30 seconds whether they have what the guide needs.
- Keep steps numbered and unambiguous. "Run X" is a step; "configure Y appropriately" is not.
- Date the last verified run at the bottom (`Last verified: YYYY-MM-DD against env=dev`). When that date drifts, someone should re-verify or mark deprecated.
- If a guide grows past ~3 pages, consider splitting it into linked sub-guides.
