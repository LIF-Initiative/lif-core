---
name: multi-agent-plan
description: Iteratively design a multi-layer LIF Core feature via a Workflow that runs sequential Opus Plan agents, each refining the prior version through one lens (FP/Polylith → backend correctness → frontend/holistic), then converges on fresh-reviewer passes until two consecutive reviews find no blockers (capped, loop-until-dry). Writes v1–vN plan files to .claude/plans/<feature>-vN.md.
argument-hint: <feature-name-kebab-case>
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Workflow, Agent
---

Design a multi-layer feature by running a **Workflow** that pipelines sequential Opus `Plan` agents. Each agent reads the prior version and refines it through **one lens**. A fresh reviewer then checks the result against all three lens checklists, and the plan converges through targeted revisions until **two consecutive** reviewers find no blockers. Invoking this skill is explicit opt-in to the Workflow tool.

**Why four lenses then a loop, and not just "loop until clean":** the value of v1→v4 is *lens diversity*, not repetition — re-running the same lens adds nothing. The loop is bolted onto the **tail**, where the question changes from "what else should this plan cover?" to "is it done?". That second question needs an independent answer, which is why the reviewer is never the agent that wrote the revision.

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

1. **Confirm scope with the user.** This writes 4–7 plan files and runs 6–11 Opus agents — four lens passes, then up to four review passes and three revisions. The tail is capped but not cheap; don't kick off if scope is fuzzy.
2. **Assemble the "read first" list** the agents will need. Always include [`CLAUDE.md`](../../../CLAUDE.md) and [`ARCHITECTURE.md`](../../../ARCHITECTURE.md). Then add the closest analogues:
   - The nearest existing proposal under [`docs/operations/proposals/`](../../../docs/operations/proposals/) — these are the canonical multi-layer plan format for LIF.
   - The relevant component `core.py`, the base/API handler it flows through, and the frontend file (`frontends/lif_advisor_app/` or `frontends/mdr-frontend/`).
   - [`docs/operations/guides/testing.md`](../../../docs/operations/guides/testing.md) for test conventions.
3. **Identify the shipped sibling flow** the feature extends (most features extend an existing flow to a new org/service/shape). Knowing it tells the v1 agent what to reuse vs. fork.

## Run the Workflow

Author and run a Workflow with the script below — fill the `<…>` placeholders from pre-flight and pass the feature name + read-list via `args`. The agents are **sequential** (each depends on the prior), so the lens passes are a straight chain rather than a fan-out. `Plan` agents are read-only and return text; the script returns every version plus the convergence outcome, and **you** (the main loop) write the files after it completes.

```javascript
export const meta = {
  name: 'multi-agent-plan',
  description: 'Iteratively refine a LIF Core feature plan through 4 sequential Plan-agent lenses',
  phases: [
    { title: 'v1 draft', model: 'opus' },
    { title: 'v2 FP/Polylith', model: 'opus' },
    { title: 'v3 backend correctness', model: 'opus' },
    { title: 'v4 frontend/holistic', model: 'opus' },
    { title: 'Review', model: 'opus' },
    { title: 'Converge', model: 'opus' },
  ],
}

// Convergence control, ported from spec-forge (orchestration/process.md "Loop control").
// CLEAN_PASSES_REQUIRED = 2 is the loop-until-dry rule: a SINGLE clean pass isn't enough,
// because one reviewer returning nothing is one opinion, not evidence. MAX_REVIEWS caps the
// whole tail; hitting it is a REPORTED RESULT ('cap-reached'), never a silent stop.
const CLEAN_PASSES_REQUIRED = 2
const MAX_REVIEWS = 4

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
End with: "v4 — frontend/holistic pass. [list]".`),
  { label: 'v4', phase: 'v4 frontend/holistic', agentType: 'Plan', model: 'opus' })

// ---------------------------------------------------------------------------
// Convergence tail: review with a FRESH agent, revise only what blocks, repeat.
// ---------------------------------------------------------------------------

// Same severity vocabulary as the self-review-relay skill, so the two are comparable.
// `section` replaces `file`/`line` — a plan has sections, not lines.
const PLAN_FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          severity: { type: 'string', enum: ['blocker', 'should-fix', 'nit'] },
          lens: { type: 'string', enum: ['fp-polylith', 'backend-correctness', 'frontend-holistic', 'scope'] },
          section: { type: 'string', description: 'plan section the finding lands in' },
          issue: { type: 'string' },
          suggestion: { type: 'string' },
        },
        required: ['severity', 'lens', 'section', 'issue', 'suggestion'],
      },
    },
  },
  required: ['findings'],
}

const reviewPrompt = (candidate, round, streak) => `You are reviewing a LIF Core implementation plan you did NOT write. Judge whether it is implementation-ready. Do not rewrite it.

**Feature:** ${F}
**Description:** ${DESC}
**Shipped sibling to anchor on:** ${SIBLING}
**Read first:**
${READ}

**Plan under review (review pass ${round} of at most ${MAX_REVIEWS}${streak ? `; ${streak} prior pass(es) found no blockers — you are the independent second opinion, judge it yourself rather than deferring` : ''}):**
${candidate}

Check it against all three lenses the plan was built through, plus scope:
- **fp-polylith** — IO at the base edge, components pure; data-driven dispatch over if/elif; brick dependency direction; every new brick wired in [tool.polylith.bricks] (incl. the 3 Dagster pyproject.toml files if Dagster uses it).
- **backend-correctness** — async correctness (advisor API is a SINGLE uvicorn worker; a blocking call stalls every concurrent request); tenant isolation failing CLOSED; pydantic validation at the boundary; migration ordering; named test cases.
- **frontend-holistic** — 401→refresh→retry shared, not re-implemented on fetch; frontend test story (lif_advisor_app has vitest, mdr-frontend has NO runner); deploy ordering; merge-order against in-flight PRs.
- **scope** — does the plan do what the description says, no more and no less? A slice that is unimplementable as written is a blocker.

**A finding is a \`blocker\` only if an implementer would be unable to proceed, or would ship something wrong.** Missing polish is \`nit\`. Do not inflate severity to look thorough, and do not invent findings — an empty array is a valid answer.

**Verify before you claim absence.** If you assert the plan omits something, grep the plan for it first; "not mentioned" is a claim about the whole document, not the section you happened to read.`

const revisePrompt = (candidate, blockers, version) => `You are revising a LIF Core implementation plan to close SPECIFIC blocking findings from an independent reviewer.

**Feature:** ${F}
**Description:** ${DESC}
**Read first:**
${READ}

**Current plan:**
${candidate}

**Blocking findings to close — address every one, and change nothing else:**
${JSON.stringify(blockers, null, 2)}

Return ONLY the full revised plan body (markdown). Preserve everything the findings do not touch; this is a targeted revision, not a rewrite. Start with a "Round ${version - 4} — blockers closed" table listing each finding and how it was addressed. If you believe a finding is wrong, keep the plan as it is for that point and say so in the table with your reasoning — do not silently ignore it.`

let candidate = v4
let reviews = 0
let cleanStreak = 0     // consecutive reviews with zero blockers
let accepted = 0        // revisions actually taken -- drives the version number
let outcome = 'cap-reached'   // only a real exit condition overwrites this
const rounds = []

while (reviews < MAX_REVIEWS) {
  reviews++
  const version = 5 + accepted

  const review = await agent(reviewPrompt(candidate, reviews, cleanStreak), {
    label: `review-${reviews}`, phase: 'Review', schema: PLAN_FINDINGS, model: 'opus',
  })
  const findings = (review && review.findings) || []
  const blockers = findings.filter(f => f.severity === 'blocker')
  rounds.push({ review: reviews, total: findings.length, blockers: blockers.length, findings })

  if (blockers.length === 0) {
    cleanStreak++
    if (cleanStreak >= CLEAN_PASSES_REQUIRED) {
      outcome = 'converged'
      log(`Review ${reviews}: clean pass ${cleanStreak}/${CLEAN_PASSES_REQUIRED}. Converged.`)
      break
    }
    // Loop-until-dry: an unchanged plan gets a SECOND independent reviewer rather than
    // being declared done on one opinion. This is not a re-roll for a better answer --
    // we are requiring two reviewers to agree, not shopping until one says yes.
    log(`Review ${reviews}: clean pass ${cleanStreak}/${CLEAN_PASSES_REQUIRED} — re-reviewing the same plan with a fresh reviewer before declaring it done.`)
    continue
  }

  cleanStreak = 0
  log(`Review ${reviews}: ${blockers.length} blocker(s) of ${findings.length} finding(s) — revising to v${version}.`)
  const revised = await agent(revisePrompt(candidate, blockers, version), {
    label: `v${version}`, phase: 'Converge', agentType: 'Plan', model: 'opus',
  })

  // Guard: require a real delta. A round that reports blockers but changes nothing is a
  // stall, and looping again would just burn agents on the same disagreement.
  if (!revised || revised.trim() === candidate.trim()) {
    outcome = 'stalled'
    log(`Review ${reviews}: revision produced no change while blockers remain — stalling out.`)
    break
  }
  candidate = revised
  accepted++
}

// Guard: if NO reviewer ever found anything at all, the streak proves reviewer agreement,
// not plan quality. On a 250-400 line plan that is more likely two weak passes than
// perfection. Report it as unverified rather than banking it as success.
if (outcome === 'converged' && !rounds.some(r => r.total > 0)) {
  outcome = 'clean-but-unverified'
  log('Every review returned zero findings of any severity — suspicious for a plan this size. Flagging for human check.')
}

return { v1, v2, v3, v4, finalPlan: candidate, finalVersion: 4 + accepted, outcome, rounds }
```

## After the Workflow returns

1. **Write the plan files** (the workflow can't write to disk — you do):
   ```
   .claude/plans/<feature-name>-v1.md  …  -v4.md   (always)
   .claude/plans/<feature-name>-v5.md  …           (one per convergence round that revised)
   ```
   Create `.claude/plans/` if it doesn't exist. `finalPlan` is the source of truth; `finalVersion` tells you what to call it.

2. **Report the convergence outcome first — it changes what the plan is worth.** The workflow returns `outcome` and a per-round `rounds` array; do not bury either.

   | `outcome` | What to tell the user |
   |---|---|
   | `converged` | **Two consecutive** reviewers found no blockers. State how many review passes it took and how many non-blocking findings remain — those are still worth reading before implementing. |
   | `cap-reached` | **The plan never got two clean passes in a row before the cap.** Say so plainly, list the surviving blockers, and treat the plan as not ready. This is the case the cap exists to make visible — including the subtle one where a lone clean pass was followed by a reviewer that found more. |
   | `stalled` | A revision changed nothing while blockers stood. The reviewer and reviser genuinely disagree — surface both sides and let the user arbitrate. Don't re-run hoping for a different answer. |
   | `clean-but-unverified` | Two clean passes, but **no reviewer ever found anything at all**, at any severity. That measures reviewer agreement, not plan quality. Report it as unverified, not as success, and offer a human read before anyone implements. |

3. **Then the substance:**
   - The v1 → final evolution, one line per version naming the key insight each lens added.
   - Any non-blocking findings that survived — they're the reviewer's honest read, not noise.
   - The critical path from the final plan's implementation order (the slice sequence).
   - Ask: *"Kick off implementation now, or `/clear` and start fresh with the final plan as the source of truth?"* (Fresh context is usually better — the plan is self-contained and a long implementation benefits from a clean prompt cache.)
3. **Promote after ship, not before.** The plan stays in `.claude/plans/` until the feature is live on dev; then move v4 to a `docs/design/` or proposal doc with a Status header pinning the ship date.

## Lessons baked in

- **One lens per pass.** Asking a single agent for FP + correctness + frontend at once yields a long shallow plan; three focused deep passes yield a tight one.
- **Each agent reads the prior version** and treats its settled parts as done — v3 doesn't redo v2.
- **Plan agents are read-only.** They return content; the main loop writes files and commits.
- **The shipped sibling flow is the anchor.** Put it in every agent's read-list.

### On the convergence loop specifically

A loop that exits when a judge reports zero issues applies pressure in exactly one direction: **toward the judge reporting nothing.** That is not the same as the plan being good. These four guards are what separate a real convergence from a manufactured one, and none of them is optional:

- **The reviewer is never the reviser.** Separate agents, and the reviewer is told it did not write the plan. If the same pass finds and fixes, "zero findings" is self-issued.
- **The cap is reported, not silent.** `cap-reached` means the plan still had blockers — a *result*, and a more useful one than a forced zero. Silently stopping at N would state the opposite of the truth.
- **A round must produce a delta.** Blockers standing plus an unchanged plan is a stall, not progress. Looping again just re-litigates the same disagreement with the same two agents.
- **One clean pass is not convergence.** Exiting on the first zero-blocker review declares done on a single opinion. The loop requires **two consecutive** clean passes, re-reviewing the unchanged plan with a fresh reviewer — requiring two reviewers to agree, not shopping until one says yes. Ported from `spec-forge` (`orchestration/process.md`, "Loop control"), which has had this rule since June 2026: *"a single clean pass isn't enough."*
- **An all-zero run is suspicious, not excellent.** If no reviewer ever found anything at any severity, two clean passes measure agreement between two weak reviewers. On a 250–400 line plan that's the likelier reading, so the skill reports `clean-but-unverified` rather than banking it.

Prefer a deterministic gate to a judge wherever one exists — that's why `refactor` and `test` loop on `ruff`/`ty`/`pytest`/`poly check` instead of on an opinion. A plan has no such oracle, which is the only reason a judge loop is the right tool here.
