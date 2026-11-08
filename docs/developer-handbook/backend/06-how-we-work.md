# 6. How we work

From an issue to merged code — branches, commit messages, PRs, CI, review, and where decisions and docs go.

*Checked against main `2967cb9`, November 2026.* Branch protection and merge settings were read from GitHub; the rest comes from
[`CONTRIBUTING.md`](../../../CONTRIBUTING.md), `commitlint.config.mjs`, [`.github/pull_request_template.md`](../../../.github/pull_request_template.md) and `pr-ci.yml`.

---

## The loop

1. **Start from an issue.** Every change traces to a GitHub issue (templates: bug report, feature request,
   other). If there isn't one, open it first: the commit format requires an issue number.
2. **Branch from `main`.** Name it after the issue (`issue-1472-association-name-array` is typical).
3. **Commit** with the required message format (below). Pre-commit checks run on every commit ([chapter 1](01-dev-environment.md)).
4. **Open a PR against `main`.** Not against another feature branch: CI and the required checks only run
   for PRs into `main`.
5. **CI runs** (`.github/workflows/pr-ci.yml`), a **reviewer reviews**, and the PR is **merged**.
6. **Deploys to dev happen after merge**, per service, through path-filtered workflows ([chapter 9](09-environments-and-deploys.md)).

## Commit messages

Enforced by commitlint (`commitlint.config.mjs`), locally by the `commit-msg` hook and again in CI:

```
Issue #123: feat: short description of the change

Optional body, after a blank line.
```

- The header **must** start with `Issue #<number>:`. Several issues: `Issue #123, Issue #456: …`.
- `feat:`, `fix:`, `docs:`, `refactor:` after it are encouraged, not enforced.
- A blank line before the body is enforced.

## Pull requests

Use the template ([`.github/pull_request_template.md`](../../../.github/pull_request_template.md)): description, related issues, type of change.

**Linking issues matters**, because GitHub acts on the words:

- `Closes #123`: this PR **fully** resolves #123. Merging closes it and moves its project card to Done.
- `Refs #123`: related but not finished, **or an epic**. Never `Closes` an epic: its sub-issues track it.
- The number goes right after `#`. GitHub also acts on "close #N" written in ordinary prose in the body,
  so don't write that unless you mean it.

Keep PRs to **one issue or task** ([`CONTRIBUTING.md`](../../../CONTRIBUTING.md)). Mark a PR **draft** while it isn't ready: a note in
the body saying "don't merge yet" is not a gate.

## CI and merging

`main` is protected (read from the API, November 2026):

- **Required checks:** `Python (ruff / ty / pytest)`, `Frontend build (mdr-frontend)`,
  `Frontend build (lif_advisor_app)`, `Commit messages (commitlint)`.
- **Strict:** the branch must be up to date with `main` before it can merge. If `main` moves, update your
  branch: **merge `main` into it** rather than rebasing once it's under review, so reviewers' context
  isn't lost. Don't force-push a PR under review.
- **No required approvals** in the branch rules. The review rule is social ([`CONTRIBUTING.md`](../../../CONTRIBUTING.md)): don't
  approve your own PR except for trivial or docs-only changes. Request a reviewer explicitly: there's no
  CODEOWNERS file to do it for you. The people who can merge are listed in [`docs/COMMITTERS.md`](../../COMMITTERS.md).
- PRs are normally **squash-merged** (the commit on `main` is the PR title plus `(#PR)`; all 150 commits on `main` since September are squash commits).

What CI does *not* run: the integration tests (`integration_tests/`), `poly check`, and anything
that needs the team's AWS-hosted environments. Your local runs are the only check on those ([chapter 1](01-dev-environment.md)).

## Decisions: ADRs

An architectural decision is recorded as an **ADR** under `docs/design/adr/<area>/NNNN-title.md`,
numbered per folder, from that folder's `_template.md`. Status moves Proposed → Accepted; an accepted ADR
isn't edited (beyond typos): a new ADR supersedes it. Write one when you choose between real
alternatives that others will live with. Index and conventions: [`docs/design/adr/README.md`](../../design/adr/README.md).

## Where docs go

[`docs/README.md`](../../README.md) sorts every doc into a layer: overview, specs, design (ADRs, components, cross-cutting),
operations (guides, proposals), agents, external. Every new or renamed doc needs an entry in
[`docs/INDEX.md`](../../INDEX.md). Filenames are kebab-case. A brick's own README lives in the brick.

Some rules from [`CONTRIBUTING.md`](../../../CONTRIBUTING.md): a breaking change is noted in [`CHANGELOG.md`](../../../CHANGELOG.md) and [`MIGRATION.md`](../../../MIGRATION.md); an API
change updates the brick and project READMEs; a configuration change updates the relevant README.

## Code layout conventions

- In a module that mixes Pydantic models, helpers and FastAPI endpoints (typical of `bases/lif/*/core.py`),
  group them: **models first, then helpers, then endpoints**. Don't interleave.
- The PascalCase/camelCase rule ([chapter 3](03-data-model-and-mdr.md)) applies to seed data, `.graphql` files, config fragment paths
  and test fixtures too.
- Tests mirror the source tree under `test/`. What's worth testing: [`docs/operations/guides/testing.md`](../../operations/guides/testing.md).

## Working with AI agents

The repo is set up for coding agents. [`CLAUDE.md`](../../../CLAUDE.md) and [`AGENTS.md`](../../../AGENTS.md) are read automatically at the start of
a session; [`agent-behavioral-guidelines.md`](../../../agent-behavioral-guidelines.md) sets the rules an agent must follow here: stay in scope,
verify by measuring, write a failing test first for a bug, and **stop and ask** before touching a shared
brick, a Flyway migration, `reference_data/transformations/`, or a deploy path. Those stop-and-ask
boundaries are good rules for people too.

Project skills live in `.claude/skills/` (for example `open-pr`, `new-microservice`, `adr-write`,
`docs-index`, `test`).
