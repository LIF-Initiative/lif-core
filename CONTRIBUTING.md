# Contributing to `LIF-CORE`

Thanks for your interest in contributing! We welcome pull requests, ideas, and
feedback to help improve this project.

This guide outlines how to get set up, our coding standards, and how to propose
changes.

---

## Getting Started

1. **Fork** the repository and clone your fork:

   ```bash
   git clone https://github.com/your-username/lif-main.git
   cd lif-main
   ```

2. **Install dependencies and create virtual environment**:

   ```bash
   uv sync
   ```

---

## How to Contribute

- **Report bugs** or **suggest features** by opening an issue.
- **Fix bugs**, **add features**, or **improve documentation**
  via pull requests (PRs).
- Contributions should generally **start with an open issue or a well-defined task**.

---

## Pull Request Guidelines

We aim to keep our codebase clean, reviewable, and maintainable.
Please follow these guidelines:

- **Small and focused**: PRs should address **one issue or task**.
  Avoid combining multiple unrelated changes
  (e.g., don’t fix bugs and add new features in the same PR).
- **Descriptive**: Provide a clear summary of what the PR does and why,
  referencing the related issue number (e.g., `Closes #42`).
- **Review protocol**:
  - PR authors **should not approve their own pull requests**, except for:
    - Trivial changes (e.g., typo fixes)
    - Documentation-only updates
  - All other PRs require review and approval from another contributor.
- **Tests**: Include or update tests as appropriate.
- Make sure the code:
  - Passes linting and formatting checks (`ruff`)
  - Passes type checking (`ty`)
  - Passes all tests (`pytest`)

---

## 🧹 Code Style & Tooling

We enforce consistent code style using:

- [`ruff`](https://github.com/astral-sh/ruff) – code formatter / fast linter
- [`ty`](https://github.com/astral-sh/ty) - static type checker
- [`pre-commit`](https://pre-commit.com/) – automates checks

### Before You Commit

Make sure code passes formatting and linting:

```bash
uv run ruff check
uv run ruff format
uv run ty check
```

Or alternatively:

```bash
source .venv/bin/activate
ruff check
ruff format
ty check
```

Or run all checks at once with:

```bash
uv run pre-commit run --all-files
```
Or if the virtual environment has been activated with `source .venv/bin/activate`:

```bash
pre-commit run --all-files
```

---

## Testing

Tests are required for new features and bug fixes.

### Running Tests

```bash
uv run pytest                                    # Run all tests
uv run pytest test/components/lif/<module>/      # Run tests for a specific component
uv run pytest test/path/to/test_file.py -v       # Run a specific test file
```

### What Makes a Good Unit Test

Write tests that earn their keep. Every test should verify something non-obvious about the code's behavior.

**Do test:**
- **Non-trivial transformations** — regex logic, recursion, type dispatch, multi-step pipelines where inputs interact in unexpected ways
- **Boundary conditions** — empty inputs, None values, edge cases where behavior changes (e.g., leading digits in identifiers, CamelCase splitting combined with special characters)
- **Bug regressions** — every bug fix should include a test that fails without the fix and passes with it
- **End-to-end behavior** — testing a function with real inputs is more valuable than mocking every internal call. For example, test `generate_graphql_schema()` with an actual OpenAPI schema rather than mocking sub-functions.

**Don't test:**
- **Trivial wrappers** — if a function is a one-liner delegating to another tested function, testing it adds noise, not confidence
- **Framework behavior** — don't test that Pydantic validates types or that `re.sub` works; test *your* logic that uses them
- **Obvious guard clauses** — `if not s: return s` doesn't need its own test case unless the empty-input behavior is a documented contract
- **Coverage for coverage's sake** — a placeholder test like `assert module is not None` has no value. Either write a real test or leave the file empty.

**Guidelines:**
- Mirror the source structure in `test/` (`test/components/lif/<module>/test_core.py`)
- Group related tests into classes for organization
- Prefer real objects over mocks when practical — mocks can mask bugs in the interaction between components
- Use `pytest.raises()` with `match=` to verify specific error messages, not just error types

---

## Commit Guidelines

Use clear, descriptive commit messages. Conventional commit style is encouraged:

- `feat:` for new features
- `fix:` for bug fixes
- `docs:` for documentation changes
- `refactor:` for internal changes that don't affect behavior

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

If you're not sure where to start, check out [open issues](https://github.com/your-org/your-project/issues),
especially those labeled `good first issue` or `help wanted`.
