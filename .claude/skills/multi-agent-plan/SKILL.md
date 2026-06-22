---
name: multi-agent-plan
description: Iteratively design a multi-layer LIF Core feature via a Workflow that runs sequential Opus Plan agents, each refining the prior version through one lens (FP/Polylith → backend correctness → frontend/holistic). Writes v1–v4 plan files to .claude/plans/<feature>-vN.md.
argument-hint: <feature-name-kebab-case>
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Workflow, Agent
---

Design a multi-layer feature by running a **Workflow** that pipelines sequential Opus `Plan` agents. Each agent reads the prior version and refines it through **one lens**. The output is an implementation-ready v4 plan. Invoking this skill is explicit opt-in to the Workflow tool.

## Arguments

- `<feature-name>` — kebab-case (e.g. `advisor-token-streaming`, `mdr-output-validation`, `tenant-search-path-routing`).

## When to use

Use when ALL of these hold:
- The feature spans **2+ layers** (component logic + a base/API + a frontend + migrations/seed).
- The **data shape is novel** (not a mechanical extension of an existing one).
- The pattern will be **adopted in more than one place** (multiple services, both frontends, multiple orgs).

Skip when:
- Single-layer change (one handler, one component function).
- Bug fix where the shape is already known.
- Small UX/copy polish.

## Pre-flight (do this inline, before the Workflow)

1. **Confirm scope with the user.** This writes ~4 plan files (~2000 lines total). Don't kick off if scope is fuzzy.
2. **Assemble the "read first" list** the agents will need. Always include [`CLAUDE.md`](../../../CLAUDE.md) and [`ARCHITECTURE.md`](../../../ARCHITECTURE.md). Then add the closest analogues:
   - The nearest existing proposal under [`docs/operations/proposals/`](../../../docs/operations/proposals/) — these are the canonical multi-layer plan format for LIF.
   - The relevant component `core.py`, the base/API handler it flows through, and the frontend file (`frontends/lif_advisor_app/` or `frontends/mdr-frontend/`).
   - [`docs/operations/guides/testing.md`](../../../docs/operations/guides/testing.md) for test conventions.
3. **Identify the shipped sibling flow** the feature extends (most features extend an existing flow to a new org/service/shape). Knowing it tells the v1 agent what to reuse vs. fork.

## Run the Workflow

Author and run a Workflow with the script below — fill the `<…>` placeholders from pre-flight and pass the feature name + read-list via `args`. The agents are **sequential** (each depends on the prior), so this is a `pipeline` of one item through four stages. `Plan` agents are read-only and return text; the script returns the four bodies, and **you** (the main loop) write the files after it completes.

```javascript
export const meta = {
  name: 'multi-agent-plan',
  description: 'Iteratively refine a LIF Core feature plan through 4 sequential Plan-agent lenses',
  phases: [
    { title: 'v1 draft', model: 'opus' },
    { title: 'v2 FP/Polylith', model: 'opus' },
    { title: 'v3 backend correctness', model: 'opus' },
    { title: 'v4 frontend/holistic', model: 'opus' },
  ],
}

const F = args.feature          // kebab feature name
const READ = args.readFirst     // string: bullet list of files to read first
const DESC = args.description   // one-paragraph feature description
const SIBLING = args.sibling    // the shipped sibling flow to anchor on

const plan = (lens, prior, extra) => `You are refining a LIF Core implementation plan.

**Feature:** ${F}
**Description:** ${DESC}
**Shipped sibling to anchor on:** ${SIBLING}

**Read first (do this before planning):**
${READ}
${prior ? `\n**Prior version to refine (treat its settled parts as done — do not redo them):**\n${prior}\n` : ''}
${extra}

Return ONLY the plan body (markdown). ${prior ? 'Start with a "Refinements vs. prior version" table.' : ''}`

const v1 = await agent(
  plan('initial draft', null, `
**Your job — v1, the initial draft.** Mirror the structure of LIF proposals under docs/operations/proposals/:
1. Scope — in scope / out of scope.
2. Data model changes — pydantic shapes, DB/schema additions (mind PascalCase entity props / camelCase scalars).
3. Backend slices — components/lif/* (pure logic) + bases/lif/* (API/IO) + pydantic schemas + any migrations.
4. Frontend slices — which frontend (lif_advisor_app vs mdr-frontend), components/hooks/util, routing.
5. Seed / sample-data / config changes (projects/mongodb/sample_data/{org}).
6. Implementation order — small, independently testable slices.
7. Open questions for the implementer.
Keep it ~250–400 lines.`),
  { label: 'v1', phase: 'v1 draft', agentType: 'Plan', model: 'opus' })

const v2 = await agent(
  plan('FP + Polylith boundaries', v1, `
**Your lens — v2 ONLY: functional / data-driven design + Polylith boundaries.** Do NOT do v3 (backend correctness) or v4 (frontend).
1. Push IO to the base edge; keep components/lif/* pure and testable in isolation.
2. Replace if/elif dispatch chains with data-driven lookup maps / strategy tables.
3. pydantic models for data-only shapes; keep dicts only for live handles that can't be validated.
4. Pure helpers in the right brick — not buried in a handler.
5. Brick dependency direction: bases depend on components, never the reverse; flag any new brick + its [tool.polylith.bricks] wiring (incl. the 3 Dagster pyproject.toml files if Dagster uses it).
6. Declarative over imperative; composable over feature-specific.
End with: "v2 — FP/Polylith pass. [list of changes]".`),
  { label: 'v2', phase: 'v2 FP/Polylith', agentType: 'Plan', model: 'opus' })

const v3 = await agent(
  plan('backend correctness', v2, `
**Your lens — v3 ONLY: backend correctness & rigor.** Do NOT do v4 (frontend).
1. async correctness — no blocking llm.invoke / sync IO on the event loop (the advisor API runs a SINGLE uvicorn worker; a blocking call stalls every concurrent request). Use async or run_in_threadpool.
2. Tenant isolation — get_session search_path routing; fail CLOSED on a missing/unknown tenant schema (never silently fall through to public).
3. pydantic validation at the API boundary; explicit error surface (correct HTTP codes; in-band errors for already-started streaming responses).
4. DB migration ordering and multi-org behavior (dev = single-org :latest tags; demo = multi-org pinned tags).
5. Polylith brick registration — every new brick wired in [tool.polylith.bricks] everywhere it's consumed.
6. Surface 5–8 non-obvious unit/integration test cases v2 missed (test/ mirrors source; integration_tests/ with --skip-unavailable).
7. Verify assumed helpers actually exist (grep before assuming).
End with: "v3 — backend correctness pass. [list]".`),
  { label: 'v3', phase: 'v3 backend correctness', agentType: 'Plan', model: 'opus' })

const v4 = await agent(
  plan('frontend + holistic', v3, `
**Your lens — v4: frontend React/TS + final holistic review.**
1. Auth — fetch bypasses the axios interceptor; share the 401→refresh→retry logic (frontends/lif_advisor_app/src/utils/axios.ts). Use real localStorage keys + VITE_* env (build-time only — coordinated must-match flags hurt; prefer runtime/content-negotiation).
2. Frontend tests — lif_advisor_app has vitest (npm test); mdr-frontend has NO runner (gate via npm run build / tsc). Name the test cases.
3. Routing / session restore / lazy rehydration; empty + error states.
4. Deploy ordering — backend vs frontend first; ECS task-def vs image rebuild; dev :latest → demo pinned promotion.
5. Integration test additions that catch the deployment-like failure class (e.g. ALB idle-timeout for long responses).
6. Sequencing / merge-order across any in-flight PRs touching the same files.
End with: "v4 is implementation-ready. Promote to docs/ after first ship." and "v4 — frontend/holistic pass. [list]".`),
  { label: 'v4', phase: 'v4 frontend/holistic', agentType: 'Plan', model: 'opus' })

return { v1, v2, v3, v4 }
```

## After the Workflow returns

1. **Write the four files** (the workflow can't write to disk — you do):
   ```
   .claude/plans/<feature-name>-v1.md  … -v4.md
   ```
   Create `.claude/plans/` if it doesn't exist.
2. **Report to the user:**
   - The v1 → v4 evolution, one line per version naming the key insight each lens added.
   - The critical path from v4's implementation order (the slice sequence).
   - Ask: *"Kick off implementation now, or `/clear` and start fresh with v4 as the source of truth?"* (Fresh context is usually better — v4 is self-contained and a long implementation benefits from a clean prompt cache.)
3. **Promote after ship, not before.** The plan stays in `.claude/plans/` until the feature is live on dev; then move v4 to a `docs/design/` or proposal doc with a Status header pinning the ship date.

## Lessons baked in

- **One lens per pass.** Asking a single agent for FP + correctness + frontend at once yields a long shallow plan; three focused deep passes yield a tight one.
- **Each agent reads the prior version** and treats its settled parts as done — v3 doesn't redo v2.
- **Plan agents are read-only.** They return content; the main loop writes files and commits.
- **The shipped sibling flow is the anchor.** Put it in every agent's read-list.
