# `langchain_agent` — Component

Wraps LangChain/LangGraph into a `LIFAIAgent` purpose-built for the Advisor's chat experience: per-conversation memory, structured prompt templates, and an `ask_agent(task, query)` interface that maps high-level tasks ("load_profile", "continue_conversation", "save_interaction_summary") to the right prompt + tool chain.

## Layout

| File | Contents |
|---|---|
| `core.py` | `LIFAIAgent` — top-level interface (`setup`, `ask_agent`) |
| `helpers.py` | Prompt + chain construction helpers |
| `memory.py` | LangGraph memory wiring (`langmem`-backed) |
| [`prompts/`](prompts/) | Text-file prompt templates loaded at runtime |

Keeping prompts as plain text in `prompts/` (rather than f-strings in code) lets non-engineers tune wording without touching Python.

## Public surface

```python
from lif.langchain_agent import LIFAIAgent

agent = await LIFAIAgent.setup(config)
response = await agent.ask_agent("continue_conversation", user_message)
```

## Used by
- `bases/lif/advisor_restapi` — single consumer; this component exists to keep that base small.
