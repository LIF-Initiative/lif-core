Behavioral rules for AI agents working in this repo — scope discipline, verification, and stop-and-ask boundaries.

## Behavioral rules

These rules override any instinct to "be helpful by doing more."

### 1. Stop and ask when uncertain

- If a task has multiple valid interpretations, present them — do NOT pick one silently.
- If you are unsure how existing code works, read it first. If still unsure, stop and ask.
- If you cannot find a test to verify your change, say so before proceeding.
- Never invent requirements. Do exactly what was asked, nothing more.

### 2. Simplicity first

- Write the minimum code that solves the stated problem.
- No speculative features, no "just in case" abstractions, no premature generalization.
- No error handling for impossible scenarios.
- If your solution is 200 lines and could be 50, rewrite it.
- Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical changes

- Touch only what the task requires. Do not "improve" adjacent code, comments, or formatting.
- Do not refactor things that are not broken.
- Match the existing style of the file you are editing, even if you would write it differently.
- If your change creates unused imports or variables, remove those. Do not remove pre-existing dead code.
- **Every changed line must trace directly back to the task at hand.**

This matters more here than in a typical repo. In a Polylith monorepo a single
edit under `components/lif/` is compiled into every service that packages that
brick, so an unscoped change has a blast radius far wider than its diff
suggests — and per #1171 most deploy workflows won't even rebuild the affected
images. A wide diff is not just harder to review; it can ship silently.

### 4. Test-driven execution

Every code change must have a corresponding test, or you must explain why a test is not feasible.

Transform tasks into verifiable goals before writing code:

- "Add validation" → write tests for invalid inputs, then make them pass.
- "Fix the bug" → write a test that reproduces it, then fix and verify the test passes.
- "Refactor X" → verify tests pass before AND after.

For multi-step tasks, state a brief plan with verification:

```
1. [Step] → verify: [how you will check it]
2. [Step] → verify: [how you will check it]
3. [Step] → verify: [how you will check it]
```

Run the relevant test command to confirm — `uv run pytest test/`, or narrowed to
the brick you touched, e.g. `uv run pytest test/components/lif/composer/`. Do not
claim "done" without running the tests.

### 5. Verify claims by measuring, not by reasoning

A plausible root cause is not a root cause. Before reporting one, measure it.

- Reproduce first. If you cannot reproduce it, say that instead of naming a cause.
- A search narrower than the claim it supports produces confident false negatives.
  Before acting on an *absence*, re-run the search one scope wider.
- Never `| head` a completeness check — a count-capped search answers "are there
  any?", never "are these all?"
- Sanity-check your tooling before trusting a clean result. A probe that fails
  for an unrelated reason can look exactly like a pass.

## Documentation conventions

- **Keep agent-facing docs under ~200 lines.** `CLAUDE.md`, `AGENTS.md`, and similar guidance files must stay under 200 lines. If one grows past that, split topics into linked docs rather than letting it sprawl. (This file is imported by `CLAUDE.md` for exactly that reason.)
- **Ground every technical claim in the source; never fabricate.** Before documenting a config value, version, path, or behavior, verify it against the actual code/build files and prefer citing the file you found it in. Do not guess at version-specific or config details — read them, or mark them explicitly as unverified/TODO. A wrong-but-confident doc is worse than an honest gap.
- Full documentation layer rules, filename conventions, and the `docs/INDEX.md` requirement live in [`AGENTS.md`](AGENTS.md) and [`docs/README.md`](docs/README.md).

## Boundaries

- ✅ **Always do:** State your plan before coding. Run tests after every change. Match existing style.
- ✅ **Always do:** Write a failing test first for bug fixes. Verify it passes after the fix.
- ✅ **Always do:** Read the code around your change before editing it.
- 🛑 **Always stop and ask if:**
  - The task is ambiguous or has multiple interpretations.
  - You are unsure how existing code works after reading it.
  - You cannot write a test to verify your change.
  - You're about to add or edit a **Flyway migration** in `projects/lif_mdr_database/`. V1.2+ migrations must be idempotent (`CREATE OR REPLACE`, `CREATE TABLE IF NOT EXISTS`) because local docker-compose applies them via `psql`, not real Flyway — so a migration can pass locally and still fail or be skipped in a real environment. A missing migration took API-key creation down on both envs (#1123).
  - You're about to change a **shared brick under `components/lif/`** that more than one service packages. The change compiles into every consumer, and most deploy workflows won't rebuild them (#1171). Name the affected services before editing.
  - You're about to touch a **live-environment or promotion path** — `cloudformation/*.params`, `.github/workflows/lif_*.yml`, or the promote-to-demo flow. These reach dev/demo directly rather than through a test.
  - You're about to edit **`reference_data/transformations/`**. These files mirror transformation definitions that live in MDR; editing them without going through `scripts/import-transformations.sh` silently diverges the repo from what is actually running (#1127/#1128).
- 🚫 **Never do:** Guess at requirements. Add features that weren't asked for. "Improve" code adjacent to your change. Commit secrets. Force-push a PR that is under review.

## Checklist — run before declaring any task complete

```
[ ] Every changed line traces to the stated task
[ ] Tests exist for the change (or I've explained why not)
[ ] Tests pass (uv run pytest test/, or the narrowed path)
[ ] Lint passes (uv run ruff check)
[ ] Formatting passes (uv run ruff format --check)
[ ] Type check passes (uv run ty check)
[ ] pre-commit passes on the changed files
      (uv run pre-commit run --files <changed files>)
[ ] Files staged explicitly by path — never `git add -A`
[ ] Commit message follows `Issue #XXX: Brief description` (commitlint-enforced)
[ ] No secrets, credentials, or hardcoded hostnames
[ ] If a shared brick changed: the consuming services are named, and their
      deploy workflow `paths:` filters actually cover the brick (see #1171)
```
