# Contributing to `LIF-CORE`

Thanks for your interest in contributing! We welcome pull requests, ideas, and
feedback to help improve this project.

> **Command reference lives in [`CLAUDE.md`](CLAUDE.md).** That file is the
> canonical, up-to-date reference for setup, linting, type checking, testing,
> schema conventions, and architecture. This guide focuses on the contributor
> *process* (how to propose changes, review etiquette, commit format) and links
> into `CLAUDE.md` for the mechanics rather than duplicating them.

---

## Getting Started

1. **Fork** the repository and clone your fork:

   ```bash
   git clone https://github.com/your-username/lif-core.git
   cd lif-core
   ```

2. Set up the dev environment per [CLAUDE.md → Setup](CLAUDE.md#setup)
   (`uv sync` plus the two `pre-commit install` invocations).

---

## How to Contribute

- **Report bugs** or **suggest features** by opening an issue.
- **Fix bugs**, **add features**, or **improve documentation** via pull
  requests (PRs).
- Contributions should generally **start with an open issue or a well-defined
  task**.

---

## Pull Request Guidelines

We aim to keep our codebase clean, reviewable, and maintainable.

- **Small and focused**: PRs should address **one issue or task**. Avoid
  combining unrelated changes (e.g., don't fix a bug and add a new feature in
  the same PR).
- **Descriptive**: Provide a clear summary of what the PR does and why,
  referencing the related issue number (e.g., `Closes #42`).
- **Review protocol**:
  - PR authors **should not approve their own pull requests**, except for:
    - Trivial changes (e.g., typo fixes)
    - Documentation-only updates
  - All other PRs require review and approval from another contributor.
- **Tests**: Include or update tests as appropriate.
- **Checks must pass**: linting (`ruff`), type checking (`ty`), tests
  (`pytest`). Commands live in
  [CLAUDE.md → Development](CLAUDE.md#development).

---

## Code Style

Tooling — `ruff` (format + lint), `ty` (type check), `pre-commit` (automation)
— and the commands to run them are documented in
[CLAUDE.md → Development](CLAUDE.md#development).

### File layout (Python)

In modules that combine Pydantic models, helper functions, and FastAPI
endpoint handlers (the typical shape of a `bases/lif/*_restapi/core.py` or
router module), group each category contiguously:

1. **Pydantic request/response models** at the top
2. **Helper functions** in the middle
3. **Endpoint handlers** at the bottom

Don't interleave the three. A reader scanning the file should be able to find
all the data shapes in one block and all the routes in another, without
scrolling past helpers wedged between two endpoints. Small modules with one
model and one endpoint don't need to enforce this, but the convention scales
with file size.

### Schema conventions

The LIF data model uses PascalCase for entities and camelCase for scalars
(`Name`, `Identifier` vs. `firstName`, `informationSourceId`). Full rules:
[CLAUDE.md → Capitalization Convention](CLAUDE.md#capitalization-convention-important)
and [`docs/specs/data-model-rules.md`](docs/specs/data-model-rules.md).

---

## Testing

Tests are required for new features and bug fixes. See
[CLAUDE.md → Testing](CLAUDE.md#testing) for:

- What makes a good unit test (and what not to test)
- How to run the suite (unit + integration)
- Integration-test conventions and sample-data layout

---

## Commit Guidelines

Commit messages must reference a tracking issue and follow the format enforced
by `commitlint.config.mjs`:

```
Issue #XXX: Brief description
```

For changes touching multiple issues, list them comma-separated:

```
Issue #123, Issue #456: Brief description
```

Type prefixes are encouraged in the description for readability (not required
by commitlint):

- `feat:` for new features
- `fix:` for bug fixes
- `docs:` for documentation changes
- `refactor:` for internal changes that don't affect behavior

Example: `Issue #884: feat: Add invite-link endpoints`

See [CLAUDE.md → Commit Convention](CLAUDE.md#commit-convention) for the
canonical statement of this rule.

---

## Additional Considerations

When contributing, please ensure:

- Breaking changes are documented in both CHANGELOG.md and MIGRATION.md
- Database schema changes include migration files and changelog entries
- API changes update both the base Python documentation and project READMEs
- Configuration changes update relevant folder READMEs

---

## Thanks

We appreciate your contributions and interest in the project!

If you're not sure where to start, check out
[open issues](https://github.com/LIF-Initiative/lif-core/issues),
especially those labeled `good first issue` or `help wanted`.
