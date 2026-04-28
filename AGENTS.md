# AGENTS.md

Pointer doc for AI agents working in this repository. Read this first; then follow the links to the authoritative material.

---

## What this repo is

LIF (Learner Information Framework) — an open-source ecosystem of microservices for aggregating learner information from SIS, LMS, HR, and other source systems into a standardized data record. Polylith monorepo, Python services, AWS deployment.

For a full overview of architecture, build commands, schema conventions, and deployment, see [`CLAUDE.md`](CLAUDE.md). It's the authoritative repo guide for AI tools.

---

## Where to start

| If you need… | Go to |
|---|---|
| Repo-wide guidance (build, test, schema, deployment) | [`CLAUDE.md`](CLAUDE.md) |
| Documentation structure, layer rules, where docs go | [`docs/README.md`](docs/README.md) |
| Curated list of every doc in the repo | [`docs/INDEX.md`](docs/INDEX.md) |
| Code-contribution rules (commits, PRs, style) | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| MCP servers, LLM integration patterns, agent conventions | [`docs/agents/`](docs/agents/) |
| Design decisions and rationale | [`docs/design/adr/`](docs/design/adr/) (currently at `docs/adr/` pending move) |

---

## Conventions for agents writing or editing docs

1. **Classify before you write.** Use the decision tree in [`docs/README.md`](docs/README.md) to pick the right layer. If nothing fits, that's a signal — open an issue rather than inventing a category.
2. **Filenames are kebab-case.** Acronyms lowercased as single words (`mdr`, `mcp-server`). Drop the `LIF_` prefix unless it's part of the proper name. See `docs/README.md` for the full convention.
3. **One-line summary at the top of every markdown doc.** That summary becomes the entry in [`docs/INDEX.md`](docs/INDEX.md).
4. **Update INDEX.md when you add, remove, or significantly rewrite a doc.** The [`docs-index`](.claude/skills/docs-index/SKILL.md) skill automates this; manual updates are also fine.
5. **Don't duplicate.** Cross-link between `CLAUDE.md`, `docs/README.md`, and per-layer READMEs rather than copying content. If you find yourself wanting to duplicate, the structure is wrong.
6. **ADRs are immutable once Accepted.** To revise an accepted ADR, write a new ADR that supersedes the old one.
7. **Match the layer rule.** Each layer's README states its rule (e.g., "Operations docs reflect reality, not intent"). If your doc violates the rule of its layer, it's in the wrong layer.

---

## Conventions for agents writing code

These are summarized from `CLAUDE.md`; see that file for the authoritative version.

- **Commit messages** follow `Issue #XXX: Brief description`. Multi-issue: `Issue #123, Issue #456: Description`.
- **PR commits append, don't force-push** on PRs under review. Force-pushes invalidate reviewer "viewed" state and break inline-comment threading. See [`feedback_pr_commit_style`](https://docs.anthropic.com/en/docs/claude-code/memory) memory for the rule and rationale.
- **Idempotent migrations.** V1.2+ Flyway migrations must be safely re-runnable (`CREATE OR REPLACE`, `CREATE TABLE IF NOT EXISTS`) because local docker-compose loads them via `psql` not real Flyway. See `CLAUDE.md` § "MDR Schema Migrations".
- **Pre-commit must pass.** `uv run pre-commit run --files <changed files>` before committing. ruff, cspell, ty, pytest.

---

## What's *not* in this file

- Detailed repo architecture, build instructions, deployment specifics, schema conventions — those are in [`CLAUDE.md`](CLAUDE.md).
- Specific service designs — those are in [`docs/design/components/`](docs/design/components/).
- Data model rules — those are in [`docs/specs/`](docs/specs/).

This file is intentionally short. If it grows past ~80 lines, content has leaked from somewhere else and should move.
