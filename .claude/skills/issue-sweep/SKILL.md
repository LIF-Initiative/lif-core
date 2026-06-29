---
name: issue-sweep
description: Multi-agent staleness sweep of open GitHub issues — fan out cheap agents to check which open issues are already resolved by merged PRs / shipped code, arbitrate the uncertain ones, and surface a close-list with evidence. Closing is gated on user confirmation.
argument-hint: [label or search filter]
allowed-tools: Bash, Read, Glob, Grep, Agent, Workflow
---

Find open issues that are **already done**. Shipping velocity outruns issue hygiene, so `lif-core` accumulates open issues that merged PRs or shipped code have quietly resolved. This skill fans out cheap agents to check each open issue against the actual codebase + merged PRs, arbitrates disagreements, and hands you a close-list with evidence. **It never closes an issue without your say-so** — closing/commenting on GitHub is outward-facing.

This is the GitHub-issue analogue of a backlog-drift sweep. Run it after a multi-week arc closes, when catching up on admin, or every ~10 substantive PRs.

## Arguments

- `[filter]` — optional. A label (`"LIF Advisor API"`, `bug`) or `gh issue list --search` query to scope the sweep. Default: all open issues.

## Phase 1 — Survey (inline)

Pull the open issues and recent merged work for context:
```bash
gh issue list --state open --limit 200 --json number,title,labels,updatedAt \
  ${FILTER:+--label "$FILTER"}        # or --search "$FILTER"
gh pr list --state merged --limit 60 --json number,title,mergedAt,closingIssuesReferences
```
Surface the count and the **stalest** issues (oldest `updatedAt`) — those are the richest closure source. Note this repo's convention: merged PRs and `Tracker:`-prefixed commits often reference the resolving issue (`#NNN → PR #MMM`), so resolution evidence usually lives in a merged PR body, a commit `--grep`, or the presence of the named code.

> **Scope deliberately — this sweep is expensive.** Each issue costs ~75K tokens (two judges, each running ~30 `gh`/`git`/`grep` calls). A full open-issue sweep of a large repo (lif-core has 300+ open) is ~20M+ tokens. **Default to a label filter or the stalest ~10–20 issues**, not all-open, unless the user explicitly asks for the whole backlog. Always report the scope you swept (Phase 3) so "nothing else to close" isn't read as "swept everything."

## Phase 2 — Fan out + arbitrate (Workflow)

Run a Workflow that judges each open issue independently and arbitrates only where the cheap judges disagree. **Inline the Phase-1 issue list directly into the script** as a `const` (see below) — do *not* pass it through the Workflow `args` field; that path has proven unreliable here (the array arrives undefined and `pipeline()` throws). (Invoking this skill is explicit opt-in to the Workflow tool; if Workflow is unavailable, fall back to spawning the Phase-2 agents directly with the Agent tool.)

```javascript
export const meta = {
  name: 'issue-sweep',
  description: 'Judge whether each open GitHub issue is already resolved by merged code',
  phases: [{ title: 'Judge' }, { title: 'Arbitrate' }],
}

// Inline the Phase-1 issue list here (do NOT use args.issues — see note above).
const issues = [
  // { number: 75, title: "Add Async support to Advisor API", labels: ["LIF Advisor API"] },
  // …one entry per issue in scope…
]

const VERDICT = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['resolved', 'open', 'uncertain'] },
    evidence: { type: 'string', description: 'merged PR #, commit SHA, file/symbol, or why still open' },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
  },
  required: ['status', 'evidence', 'confidence'],
}

const judgePrompt = (issue) => `Decide whether this OPEN GitHub issue is already RESOLVED by code/PRs that have shipped to LIF Core.

Issue #${issue.number}: ${issue.title}
Labels: ${(issue.labels || []).join(', ')}

Investigate with:
- gh issue view ${issue.number}  (read the body + comments + any linked PRs)
- gh pr list --state merged --search "${issue.number}"  (a PR that closed/referenced it)
- git log --oneline --grep "#${issue.number}"  and  git log -S "<headline symbol>"  (commit evidence)
- grep/Glob for the feature's headline keywords / named files/functions to confirm the code exists

Return status=resolved ONLY with concrete evidence (a merged PR #, a commit SHA, or a named shipped file/symbol). status=open if it's clearly not done. status=uncertain if the evidence is ambiguous. Put the evidence (or the reason it's still open) in the evidence field.`

const results = await pipeline(
  issues,
  // Stage 1: two independent cheap judges per issue
  (issue) => parallel([
    () => agent(judgePrompt(issue), { label: `judge:#${issue.number}:a`, phase: 'Judge', schema: VERDICT, model: 'haiku' }),
    () => agent(judgePrompt(issue), { label: `judge:#${issue.number}:b`, phase: 'Judge', schema: VERDICT, model: 'haiku' }),
  ]).then(vs => ({ issue, votes: vs.filter(Boolean) })),
  // Stage 2: arbitrate only when the two judges disagree on status
  ({ issue, votes }) => {
    const statuses = new Set(votes.map(v => v.status))
    if (statuses.size <= 1) return { issue, verdict: votes[0], votes }
    return agent(
      `Two judges disagreed on whether issue #${issue.number} ("${issue.title}") is resolved.\n` +
      votes.map((v, i) => `Judge ${i + 1}: ${v.status} — ${v.evidence} (${v.confidence})`).join('\n') +
      `\nInvestigate the same way (gh issue view, merged PRs, git log, code presence) and return the final verdict.`,
      { label: `arbiter:#${issue.number}`, phase: 'Arbitrate', schema: VERDICT, model: 'sonnet' }
    ).then(verdict => ({ issue, verdict, votes }))
  }
)

return results.filter(Boolean)
```

## Phase 3 — Report & (only on confirmation) close

Build a table from the Workflow result:

| Issue | Title | Verdict | Confidence | Evidence |
|-------|-------|---------|-----------|----------|
| #NNN | … | resolved | high | merged PR #MMM |

- Group **resolved/high-confidence** (the close-list) separately from **uncertain** (needs a human look) and **open** (left alone).
- **Do not close anything yet.** Present the close-list and ask the user which to act on. For each they approve, offer to:
  ```bash
  gh issue close <n> --comment "Resolved by <PR/commit>. Closed via issue-sweep."
  ```
  Cite the specific evidence in the closing comment. Closing + commenting are outward-facing — one confirmation covers the approved batch, not future runs.
- **Report what was skipped** — if the sweep was scoped by a filter or capped at a `--limit`, say so, so "nothing else to close" isn't read as "swept everything."

## Rules

- **Evidence or it didn't resolve.** `resolved` requires a concrete merged PR #, commit SHA, or named shipped symbol — never a vibe.
- **Stale ≠ resolved.** An old `updatedAt` flags an issue *to check*, not to close.
- **Never auto-close.** The close-list is a proposal; the user decides.
