---
name: open-pr
description: Open a convention-compliant LIF Core PR — reads AGENTS.md + CONTRIBUTING.md + the PR template (which do NOT auto-load), verifies branch/commits/pre-commit, fills the template (Closes #, type, areas, checklist), and creates the PR. Honors the one-issue-per-PR and no-self-approve rules.
argument-hint: [issue number]
allowed-tools: Read, Bash, Glob, Grep
---

Open a pull request that passes review on the first read. The whole point of this skill: **only `CLAUDE.md` auto-loads** — `AGENTS.md`, `CONTRIBUTING.md`, and `.github/pull_request_template.md` carry binding PR rules that you must read explicitly each time, or the PR will miss conventions.

## Arguments

- `[issue number]` — the issue this PR closes (becomes `Closes #N`). If omitted, infer from the branch name / commits and confirm with the user.

## Step 1 — Read the conventions (do not skip)

Read all three now:
- [`AGENTS.md`](../../../AGENTS.md) — commit format, the append-don't-force-push rule, pre-commit requirement.
- [`CONTRIBUTING.md`](../../../CONTRIBUTING.md) § Pull Request Guidelines — one-issue-per-PR, descriptive, review protocol.
- [`.github/pull_request_template.md`](../../../.github/pull_request_template.md) — the body structure you must fill.

## Step 2 — Pre-flight checks

1. **On a feature branch, not `main`:** `git branch --show-current`. If on `main`, create a branch first (`git checkout -b <issue-NNN-short-desc>`).
2. **One issue, one PR.** Confirm the diff addresses a single issue/task. If it bundles unrelated changes (a fix *and* a feature), stop and tell the user — split it. (CONTRIBUTING is explicit about this.)
3. **Commits follow `Issue #XXX: Brief description`** (multi-issue: `Issue #123, Issue #456: …`). The commit-msg hook enforces `commitlint.config.mjs`. Check `git log main..HEAD --oneline`.
4. **Pushed?** `git log origin/<branch>..HEAD --oneline` — push the branch if needed (`git push -u origin <branch>`).
5. **Checks green:** run the `test` skill, or at minimum:
   ```bash
   uv run pre-commit run --files $(git diff main...HEAD --name-only)
   ```
   ruff, cspell, ty, pytest must pass. Don't open a PR on a red build.

## Step 3 — Fill the PR body

Compose the body from the template — fill every section, **remove checklist items that don't apply** (the template says so):

- **Description of Change** — what problem it solves, the solution, side effects/limitations, and **how reviewers should test it**. (The relay synthesis from `self-review-relay`, if you ran it, is good source material.)
- **Related Issues** — `Closes #<n>` (this is what auto-closes the issue on merge).
- **Type of Change** — check the one(s) that apply (bug fix / feature / breaking / docs / infra / perf / refactor).
- **Project Area(s) Affected** — check by the actual diff (`git diff main...HEAD --name-only` → map to `bases/`, `components/`, `frontends/`, `cloudformation/`, migrations, etc.).
- **Checklist** — check the items truly done (lint/format/type/pre-commit; tests included; docs updated; migration + CHANGELOG if schema changed; MIGRATION.md if breaking). Remove the rest.
- **Testing** — what you actually ran.
- **Additional Notes** — merge-order coordination if this shares files with other in-flight PRs; rollout/risk notes.

Write the body to a temp file and create the PR:
```bash
gh pr create --base main --title "Issue #<n>: <short description>" --body-file /tmp/pr-body.md
```

## Step 4 — After creating

- **Do NOT approve your own PR** (CONTRIBUTING review protocol) — except trivial typo / docs-only changes, the only self-approve carve-outs. Normal PRs need another contributor.
- Surface the PR URL to the user.
- If the change touches the same files as other open PRs, add a **merge-order note** comment so whoever merges second knows what to keep.

## Rules

- **Read AGENTS.md + CONTRIBUTING.md + the template every time** — they don't auto-load, and that's the #1 source of convention misses.
- **One issue per PR.** Split bundled changes.
- **Never force-push to set up the PR** — and once it's under review, append commits only (see `address-pr-feedback`); force-pushes break reviewers' "viewed" state and inline threads.
- **Green before open.** pre-commit (ruff/cspell/ty/pytest) must pass.
