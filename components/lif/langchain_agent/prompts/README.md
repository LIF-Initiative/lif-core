# `prompts/` — LangChain prompt templates

Text-file prompt templates loaded by [`langchain_agent`](../) at runtime. Kept as plain text so wording can be tuned without code changes or commits to Python files.

## Files

| File | Used when |
|---|---|
| `load_profile.txt` | Advisor's initial profile load — fires on `/start-conversation` |
| `continue_conversation.txt` | Each subsequent turn — fires on `/continue-conversation` |
| `summarize_interaction.txt` | Mid-conversation summary the agent uses to keep context bounded |
| `save_interaction_summary.txt` | Final summary written on `/logout` for future-session memory |
| `prompt_template_query.txt` | Base scaffold the other prompts inherit from |

Refer to `components/lif/langchain_agent/core.py` for the `task` → prompt mapping.
