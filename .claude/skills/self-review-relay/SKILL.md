---
name: self-review-relay
description: Run the 4-pass self-review relay over a diff before opening or finalizing a PR — three independent lenses (correctness/security, robustness/ops, tests/conventions/scope) in parallel, then a synthesis pass that dedupes and sorts into blockers vs. nits. Catches issues before a reviewer does.
argument-hint: [diff range, default main...HEAD]
allowed-tools: Read, Glob, Grep, Bash, Agent, Workflow
---

Run the **self-review relay**: a structured multi-lens pass over your own change before a human reviewer sees it. Three independent lenses run in parallel, then a synthesis pass merges and prioritizes. This is the rigor step that earns the "no blockers" verdict (it's what produced the relay note on PR #978). It complements — does not replace — the built-in `/code-review`: the relay is broader (security + ops + scope, not just correctness) and ends in a ship/hold verdict.

Invoking this skill is explicit opt-in to the Workflow tool. If Workflow is unavailable, spawn the three lens agents directly with the Agent tool (one message, parallel) and synthesize their results yourself.

## Arguments

- `[diff range]` — what to review. Default `main...HEAD` (the PR diff). Accepts any git range, `--staged`, or a path scope.

## Pre-flight

1. **Capture the diff and context** so the agents review facts, not guesses:
   ```bash
   git diff main...HEAD --stat
   git diff main...HEAD
   git log main...HEAD --oneline
   ```
   Note the touched layers (`bases/`, `components/`, `projects/`, `frontends/`, `cloudformation/`, migrations) — the lenses key off them.
2. **State the intent in one line** (what issue this closes, what it's supposed to do) — the scope lens needs it to judge over/under-reach.

## The relay (Workflow)

Run a Workflow: lenses 1–3 in parallel (a barrier — synthesis needs all three), then the synthesis pass. Pass the diff + intent into each agent's prompt. Lenses inherit the main-loop model (strong); don't downgrade them.

```javascript
export const meta = {
  name: 'self-review-relay',
  description: 'Three parallel review lenses over a diff, then a synthesis/verdict pass',
  phases: [{ title: 'Lenses' }, { title: 'Synthesis' }],
}

const DIFF = args.diff       // the unified diff text
const INTENT = args.intent   // one-line statement of what the change should do
const RANGE = args.range || 'main...HEAD'

const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          severity: { type: 'string', enum: ['blocker', 'should-fix', 'nit'] },
          file: { type: 'string' },
          line: { type: 'string' },
          issue: { type: 'string' },
          suggestion: { type: 'string' },
        },
        required: ['severity', 'file', 'issue', 'suggestion'],
      },
    },
  },
  required: ['findings'],
}

const lens = (name, focus) => agent(
  `You are one lens of a self-review relay on a LIF Core change. Review ONLY through this lens: ${name}.

**Intent of the change:** ${INTENT}
**Diff (${RANGE}):**
\`\`\`diff
${DIFF}
\`\`\`

**Your focus:**
${focus}

You may read surrounding files (Read/Grep) for context the diff doesn't show. Report concrete findings with file:line, severity (blocker / should-fix / nit), and a specific suggestion. If the lens finds nothing real, return an empty findings array — do NOT invent issues.`,
  { label: name, phase: 'Lenses', schema: FINDINGS }
)

const lenses = await parallel([
  () => lens('correctness & security', `
- Logic bugs, off-by-one, wrong conditionals, unhandled None/empty, race conditions.
- Async correctness: no blocking/sync IO on the event loop (advisor API is a SINGLE uvicorn worker — a blocking call stalls all concurrent requests).
- Tenant isolation: get_session search_path routing; fail CLOSED on missing/unknown tenant schema (never fall through to public).
- Auth: username/identity from the JWT 'sub', never from user input; AuthMiddleware not bypassed; secrets not logged.
- Injection / unchecked input at the boundary; pydantic validation present.`),
  () => lens('robustness & ops', `
- Error surface: correct HTTP codes; in-band errors once a StreamingResponse has started; no silent fallbacks (e.g. schema-from-MDR must fail loud, not fall back to file in prod).
- Resource hygiene: connections/readers closed, no leaks; timeouts.
- Deployment impact: docker-compose / cloudformation / {env}.aws / SSM params consistent; dev :latest vs demo pinned; new env vars documented.
- Polylith: brick deps wired in [tool.polylith.bricks] (incl. the 3 Dagster pyproject.toml files if Dagster uses it); deps in the project's pyproject for Docker, not just root.
- Migrations idempotent (V1.2+ re-runnable via psql locally).`),
  () => lens('tests, conventions & scope', `
- Tests: regression test for any bug fixed; boundary cases; no importlib.reload(); meaningful (not coverage-for-its-sake).
- Conventions: PascalCase entities / camelCase scalars in data shapes; lif.logging logger; file layout (pydantic models / helpers / handlers grouped); commit messages 'Issue #XXX:'.
- Scope: does the diff do exactly what the intent says — nothing extra (sneaked-in refactor/feature), nothing missing (a layer the change implies but skipped)? One-issue-per-PR.
- Docs: INDEX.md / README / CHANGELOG / MIGRATION.md updated if the change requires it.`),
])

const all = lenses.filter(Boolean).flatMap(r => r.findings)

const synthesis = await agent(
  `Synthesize a self-review verdict for a LIF Core change from these lens findings. Intent: ${INTENT}

Findings (JSON):
${JSON.stringify(all, null, 2)}

Deduplicate overlapping findings, drop any that are wrong or not supported by the diff, and sort by severity. Then give:
1. A blockers list (must fix before requesting review) — empty is a valid, good answer.
2. A should-fix list.
3. A nits list.
4. A one-line verdict: "ready to request review" or "hold — N blocker(s)".
Be a skeptic: if a finding looks plausible but you can't tie it to a real line in the diff, cut it.`,
  { label: 'synthesis', phase: 'Synthesis' }
)

return { findingCount: all.length, synthesis }
```

## After the relay

- **Present the synthesis verdict** (blockers / should-fix / nits / ready-or-hold) to the user.
- **Offer to fix the blockers + should-fix** in the working tree, then re-run the relevant lens or `uv run pytest` to confirm.
- This pairs with **`open-pr`** — run the relay, clear blockers, then scaffold the PR. The relay's synthesis is good raw material for the PR description's "how to test" / "limitations" sections.

## Rules

- **Blockers gate the PR.** Don't hand off to a human reviewer with known blockers — that's what this pass is for.
- **Empty findings is a real result.** The lenses must not manufacture issues to look thorough; the synthesis must cut unsupported ones.
- **The relay reviews; it doesn't ship.** It never pushes or opens a PR — that's `open-pr`.
