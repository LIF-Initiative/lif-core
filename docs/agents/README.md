# `agents/` — Agent and AI-Facing Docs

**What goes here:** conventions, references, and design notes specific to LIF's agent surface — MCP servers, AI-facing tooling, LLM integration patterns, prompt conventions.

**What does *not* go here:** the LIF data model itself (that's `specs/`), service design (`design/components/`), or general repo instructions for AI tools (those live in [`CLAUDE.md`](../../CLAUDE.md) and [`AGENTS.md`](../../AGENTS.md) at repo root).

**Layer rule:** Conventions for the agent surface, not for the rest of the system. If a doc would be equally true for a non-agent integrator, it doesn't belong here.

## Typical contents

- `mcp-tools.md` — MCP tool definitions exposed by the semantic search server, contracts each tool guarantees
- `llm-integration-guide.md` — how to invoke LIF from an LLM, authentication, expected response shapes
- `prompts/` — reusable prompt patterns for agent tasks against LIF data
- `agent-context.md` — what agents working in this repo should know that isn't in CLAUDE.md

## Relationship to root-level files

| File | Purpose |
|---|---|
| [`CLAUDE.md`](../../CLAUDE.md) (root) | Repo-wide guidance Claude reads at session start: project structure, build/test commands, schema conventions, deployment notes. |
| [`AGENTS.md`](../../AGENTS.md) (root) | Short pointer doc for non-Claude agents. Cross-links to CLAUDE.md, `docs/README.md`, `docs/INDEX.md`, and this folder. |
| `docs/agents/` (here) | The actual content the pointer docs reference. MCP tool docs, prompt patterns, LLM integration guides. |

Don't duplicate between root pointer files and content files here. Cross-link.
