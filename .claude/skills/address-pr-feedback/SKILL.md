---
name: address-pr-feedback
description: Triage and respond to review feedback on your open LIF Core PRs — pull each PR's reviews + inline comments, apply fixes (or push back with reasoning), reply inline, and re-request review. Appends commits (never force-pushes) and gates outward-facing replies on your confirmation.
argument-hint: [PR number, or all your open PRs]
allowed-tools: Read, Edit, Write, Bash, Glob, Grep, Agent
---

Work the review queue on your open PRs. For each, pull the reviews and **inline** comments (the substance is usually inline, not in the review body), decide per comment whether to fix / clarify / push back, make the changes, reply on the threads, and re-request review.

## Arguments

- `[PR number]` — a single PR. If omitted, sweep **all** your open PRs (`gh pr list --author "@me" --state open`).

## The force-push rule (read first)

**Append commits to PRs under review — never force-push.** Force-pushing invalidates reviewers' "viewed" state and breaks inline-comment threading (AGENTS.md → `feedback_pr_commit_style`). Each round of feedback = one or more new commits, plainly messaged (`Issue #XXX: Address review — <what>`). No rebasing/squashing a PR mid-review unless the reviewer explicitly asks.

## Step 1 — Pull the feedback

```bash
gh pr list --author "@me" --state open
# per PR:
gh pr view <n> --json title,reviewDecision,reviews,comments
gh api repos/{owner}/{repo}/pulls/<n>/comments \
  --jq '.[] | {id, author:.user.login, path, line:(.line//.original_line), body, in_reply_to:.in_reply_to_id}'
```
The `pulls/<n>/comments` endpoint is the important one — it returns the **inline** review comments (with `suggestion` blocks). The review `body` is often empty; don't stop there. Skip threads where your own latest reply already resolved the point (`in_reply_to` chains).

## Step 2 — Triage each comment

Classify every open (unanswered) comment:
- **Apply** — a clear fix or an accepted `suggestion` block. Make the edit.
- **Clarify** — reviewer asked what something means → improve the code/doc *and* answer.
- **Push back** — the suggestion is wrong or worse. Verify your position in the code first (don't argue from memory), then reply with the reasoning. (Example from a past PR: a `suggestion` that renamed `aget_state`→`agent_state` was a non-existent method — kept the original and explained.)
- **Defer** — valid but out of scope → file a follow-up issue and reference it in the reply (`Filed #NNN`).

For multi-PR sweeps or large review sets, you can fan out an Agent per PR to draft the triage, but **you** make the edits and own the replies.

## Step 3 — Make the changes & verify

Apply the fixes, then verify before pushing — run the `test` skill or the scoped checks:
```bash
uv run pre-commit run --files $(git diff --name-only)
```
Commit (append) and push:
```bash
git commit -m "Issue #XXX: Address review — <summary>"
git push                       # plain push, NOT --force
```

## Step 4 — Reply on the threads  *(outward-facing — confirm first)*

Posting to GitHub is outward-facing. Draft all replies, show them to the user, and post the batch on one confirmation (covers this round, not future ones). Then:
- **Reply to each inline thread** (so reviewers see the resolution in context):
  ```bash
  gh api repos/{owner}/{repo}/pulls/<n>/comments/<comment_id>/replies \
    -f body="Done — <what changed>, in <commit sha>."
  ```
- For accepted `suggestion` blocks, a short "Applied in <sha>" closes the loop.
- **Re-request review** once the round is addressed:
  ```bash
  gh api repos/{owner}/{repo}/pulls/<n>/requested_reviewers -f "reviewers[]=<login>"
  ```
  (or `gh pr edit <n> --add-reviewer <login>`). Optionally a brief summary comment: `gh pr comment <n> --body "Addressed all feedback: <bullets>. Re-requesting review."`

## Step 5 — Report

Per PR, report: comments addressed (fixed / clarified / pushed-back / deferred), the commit(s) pushed, replies posted, and whether review was re-requested. Flag any PR still blocked on a decision only the user can make.

## Rules

- **Never force-push a PR under review.** Append commits.
- **Read the inline comments**, not just the review body — that's where the real feedback lives.
- **Verify before pushing back.** Check the actual code; don't refute from memory.
- **Replies/re-requests are outward-facing** — draft, confirm, then post the batch. One confirmation per round.
- **Don't self-approve** to clear `changes requested` — re-request from the reviewer (CONTRIBUTING review protocol).
