---
name: test
description: Run the full LIF Core check suite — ruff, ty, pytest unit, Polylith check, integration, and the advisor-app frontend tests — and report a summary table.
allowed-tools: Bash
---

Run the LIF Core quality gate. These are the same checks `pre-commit` runs (ruff, ty, pytest) plus the integration suite, the Polylith workspace check, and the one frontend with a test runner.

## Steps

Run from the repo root. The backend checks are independent — run them, then the frontend.

1. **Lint** — `uv run ruff check`
2. **Format check** — `uv run ruff format --check` (use `uv run ruff format` to actually fix)
3. **Type check** — `uv run ty check`
4. **Polylith workspace check** — `uv run poly check` (catches missing brick deps / broken `[tool.polylith.bricks]` wiring)
5. **Unit tests** — `uv run pytest test/` (mirrors source: `test/components/`, `test/bases/`; `asyncio_mode = auto`)
6. **Integration tests** — `uv run pytest integration_tests/ --skip-unavailable`
7. **Advisor-app frontend** — `cd frontends/lif_advisor_app && npm test` (vitest)

Notes:
- **Integration tests hit a live stack** and load sample data from `projects/mongodb/sample_data/{org-key}/`. `--skip-unavailable` skips a test when its backing service is unreachable rather than failing — keep it on for local runs. Full reference: [`docs/operations/guides/testing.md`](../../../docs/operations/guides/testing.md).
- **`mdr-frontend` has no test runner** (its `package.json` scripts are dev/build/lint/preview only). Don't try `npm test` there — for it, fall back to `cd frontends/mdr-frontend && npm run build` (runs `tsc -b`) as the type/build gate. (A vitest harness for it is tracked separately.)
- **Don't use `importlib.reload()`** to re-run a module under test — it breaks `isinstance()`/`pytest.raises()`. Use `mock.patch.object(module, "VAR", value)`.
- To scope unit tests to one component: `uv run pytest test/components/lif/<component>/`.
- The one-shot equivalent of steps 1-3+5 is `uv run pre-commit run --all-files`.

## Reporting

Report a summary table:

| Check | Result | Details |
|-------|--------|---------|
| ruff check | pass/fail | lint findings |
| ruff format | pass/fail | files needing format |
| ty check | pass/fail | type errors |
| poly check | pass/fail | brick/dep issues |
| Unit (pytest test/) | pass/fail | N passed / N failed |
| Integration | pass/fail | N passed / N skipped (service unavailable) |
| Advisor-app (vitest) | pass/fail | N tests |

If any check fails, show the relevant error output below the table.
