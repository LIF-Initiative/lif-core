"""Tests for the agent's pre_model_hook.

The regression these guard is Issue #1162: the hook returned the whole `ChatState`,
so LangGraph merged `messages` through the `add_messages` reducer (an APPEND), and the
summary was added to the history every turn instead of replacing it. Context grew
monotonically until OpenAI rejected the request at ~3.5M tokens against a 2M ceiling.
"""

import logging
from typing import Any
from unittest import mock

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.message import add_messages

from lif.langchain_agent.memory import make_pre_model_hook

MAX_MESSAGES = 4
logger = logging.getLogger(__name__)


def _fake_summarizer(summary_text: str = "summary") -> mock.Mock:
    """A summarizer whose invoke() returns a state update, like SummarizationNode does."""
    node = mock.Mock()
    node.invoke.side_effect = lambda state: {
        "summary_output_messages": [AIMessage(content=summary_text)],
        "context": {"running_summary": summary_text},
    }
    return node


def _apply_update(state: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Merge a hook's state update the way LangGraph would.

    `AgentState.messages` is Annotated[..., add_messages], so a `messages` key in the
    update is appended, not replaced. Every other key here is last-write-wins.
    """
    merged = dict(state)
    for key, value in update.items():
        if key == "messages":
            merged["messages"] = add_messages(state.get("messages", []), value)
        else:
            merged[key] = value
    return merged


def _llm_input(merged: dict[str, Any]) -> list[Any]:
    """What create_react_agent sends to the model.

    Mirrors chat_agent_executor.call_model: prefer `llm_input_messages`, else `messages`.
    """
    return merged.get("llm_input_messages") or merged["messages"]


def test_hook_returns_only_safe_keys():
    """The hook must not write `messages` (append reducer) or `remaining_steps` (managed)."""
    hook = make_pre_model_hook(_fake_summarizer(), MAX_MESSAGES, logger)
    state = {"messages": [HumanMessage(content=f"m{i}") for i in range(10)], "remaining_steps": 25}

    update = hook(state)

    assert set(update) <= {"llm_input_messages", "context"}
    assert "messages" not in update
    assert "remaining_steps" not in update


def test_llm_input_stays_bounded_across_many_turns():
    """The regression: LLM input must not grow without bound as the conversation runs."""
    hook = make_pre_model_hook(_fake_summarizer(), MAX_MESSAGES, logger)
    state: dict[str, Any] = {"messages": [], "context": {}, "remaining_steps": 25}

    sizes = []
    for turn in range(30):
        # The agent appends a user turn and a model reply, as it would in a real loop.
        state["messages"] = add_messages(
            state["messages"], [HumanMessage(content=f"q{turn}"), AIMessage(content=f"a{turn}")]
        )
        merged = _apply_update(state, hook(state))
        sizes.append(len(_llm_input(merged)))
        state = merged

    # Summary messages plus the retained tail -- a fixed ceiling, independent of turn count.
    assert max(sizes) <= MAX_MESSAGES + 1
    # And the last turn is no larger than the first few: no monotonic growth.
    assert sizes[-1] <= sizes[3]


def test_summary_replaces_history_rather_than_extending_it():
    hook = make_pre_model_hook(_fake_summarizer(), MAX_MESSAGES, logger)
    messages = [HumanMessage(content=f"m{i}") for i in range(20)]

    update = hook({"messages": messages, "context": {}})
    llm_input = update["llm_input_messages"]

    assert len(llm_input) == MAX_MESSAGES + 1
    assert llm_input[0].content == "summary"
    assert [m.content for m in llm_input[1:]] == [m.content for m in messages[-MAX_MESSAGES:]]


def test_context_is_propagated_so_summarization_is_not_repeated():
    """`context` must persist, or the summarizer re-summarizes on every single call."""
    hook = make_pre_model_hook(_fake_summarizer(), MAX_MESSAGES, logger)

    update = hook({"messages": [HumanMessage(content=f"m{i}") for i in range(10)], "context": {}})

    assert update["context"] == {"running_summary": "summary"}


def test_short_conversation_passes_through_untouched():
    summarizer = _fake_summarizer()
    hook = make_pre_model_hook(summarizer, MAX_MESSAGES, logger)
    messages = [HumanMessage(content="a"), AIMessage(content="b")]

    update = hook({"messages": messages, "context": {}})

    summarizer.invoke.assert_not_called()
    assert update["llm_input_messages"] == messages


def test_empty_state_still_supplies_llm_input_key():
    """create_react_agent errors unless the hook supplies messages or llm_input_messages."""
    hook = make_pre_model_hook(_fake_summarizer(), MAX_MESSAGES, logger)

    update = hook({"messages": [], "context": {}})

    assert update["llm_input_messages"] == []
