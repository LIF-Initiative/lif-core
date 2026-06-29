---
name: refactor
description: Safe, behavior-preserving refactoring for LIF Core — split bricks, extract helpers, converge patterns — with a verify gate (ruff/ty/pytest/poly) after every atomic change.
argument-hint: [target file, brick, or description]
allowed-tools: Read, Edit, Write, Bash, Glob, Grep, Agent
---

Refactor LIF Core code safely. The core discipline: **one atomic change → verify → repeat**, and **stop and re-plan** the moment a fix feels hacky. Refactors are behavior-preserving and get their own commit(s).

## Arguments

- `<target>` — a file path, brick name, or description (e.g. `components/lif/translator/core.py`, `extract shared search_path helper`, `split advisor_restapi handlers`).

## Pre-Flight

1. **Read the target code** and enough of its callers to understand the full scope before touching anything.
2. **Anchor on the conventions.** LIF Core has no single `coding-standards.md`; the shape lives in [`CLAUDE.md`](../../../CLAUDE.md) (Development / Polylith / Data conventions), [`ARCHITECTURE.md`](../../../ARCHITECTURE.md) (brick layout + service map), and [`docs/operations/guides/testing.md`](../../../docs/operations/guides/testing.md). The load-bearing rules:
   - **Polylith boundaries.** `components/lif/*` are pure, testable-in-isolation modules with a `core.py` entrypoint — **no I/O, no deployment code**. `bases/lif/*` wire HTTP/deployment. Keep IO at the base edge; keep transformation pure in components.
   - **PascalCase entity props / camelCase scalars** in any data shape, seed, `.graphql`, or fixture.
3. **Name the goal** — what specific problem does this solve? (brick too large, duplicated logic across handlers, IO tangled with logic, competing patterns.)
4. **Clean working tree** — `git status`. Refactors are their own commit(s), not mixed with feature work.
5. **Establish the green baseline** before changing anything:
   ```bash
   uv run pytest test/ && uv run poly check
   ```
   If a frontend is in scope: `cd frontends/lif_advisor_app && npm test` (or `cd frontends/mdr-frontend && npm run build` — mdr has no test runner).

## Refactoring Loop

### Step 1 — Plan
- List every file/brick created, modified, or deleted.
- For brick moves/splits: identify the logical groupings and new module names.
- **Confirm the plan with the user before proceeding.**

### Step 2 — One atomic change
Do ONE logical change (extract one helper, move one group of functions, rename one brick). Then immediately verify:
```bash
uv run ruff check && uv run ty check
uv run pytest test/components/lif/<brick>/   # or the relevant scope
uv run poly check                            # if brick structure/deps changed
```
- If tests fail, **fix before the next change**.
- If the fix feels hacky: stop, re-plan — *"knowing everything I know now, what's the clean design?"*

### Step 3 — Repeat
One change → verify → next change → verify. Never batch multiple steps between verifications.

### Step 4 — Final verification
```bash
uv run ruff check && uv run ruff format && uv run ty check
uv run pytest test/
uv run poly check
uv run pytest integration_tests/ --skip-unavailable   # if behavior near a service boundary moved
```

## Rules

- **Never refactor and add a feature in the same commit.** Behavior-preserving only.
- **Test count must not drop.** If you delete a test file, its tests move somewhere.
- **Update every import after a move.** `grep`/`Grep` for the old module path; `uv run poly check` catches most broken brick wiring but not all.
- **Moving a brick = update `[tool.polylith.bricks]`.** And per [`CLAUDE.md`](../../../CLAUDE.md), bricks used by Dagster must be added to **all three** Dagster `pyproject.toml` files, not just the orchestrator.
- **One commit per logical step.** Don't squash a multi-step refactor — reviewability matters.
- **Update docs if structure changed** — [`ARCHITECTURE.md`](../../../ARCHITECTURE.md) for brick/service changes; run the `docs-index` skill if a `docs/` file was added/moved.

## Common patterns

### Split a large brick `core.py`
1. Identify logical groups (by responsibility / domain).
2. Create sibling modules within the component; keep `core.py` as the public entrypoint re-exporting them.
3. Move one group at a time; verify after each.
4. Update `:require`-equivalent imports and `[tool.polylith.bricks]`.

### Extract a shared helper
1. Find logic duplicated across 2+ bricks/handlers.
2. Create or extend the shared component.
3. Replace one call site at a time; verify after each.

### Pull IO out of a component
- A `components/lif/*` module doing HTTP/DB/file IO is a boundary violation. Move the IO to the calling `bases/lif/*` layer and leave a pure transform behind. Add a unit test for the now-pure function.

### Converge competing patterns
- Same work done two ways (e.g. one handler hand-rolls a dict, another uses a pydantic model) → pick the better one and converge. In LIF, prefer pydantic models for data-only shapes; keep dicts only where a value is a live handle that can't be validated (e.g. a held agent instance).

## What NOT to refactor

- **Working code nobody touches.** If it's not broken and not read, leave it.
- **Code about to be rewritten for a feature.** Do the feature first.
- **Framework boilerplate** (FastAPI route decorators, pydantic field declarations, Polylith `pyproject` stanzas) — inherently repetitive.
