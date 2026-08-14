import logging
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately

from lif.langchain_agent.memory import _safe_trim_messages, make_pre_model_hook


def make_summarizer(summary_messages, context=None):
    """Build a fake SummarizationNode whose invoke() emits the given summary."""

    def invoke(state):
        new_state = dict(state)
        new_state["summary_output_messages"] = summary_messages
        new_state["context"] = context if context is not None else {"summarized": True}
        return new_state

    node = MagicMock()
    node.invoke.side_effect = invoke
    return node


def long_conversation():
    messages = []
    for i in range(4):
        messages.append(
            HumanMessage(
                f"User question {i}: how can I advance in my career path? "
                "Tell me what courses I should take next semester to build the skills I need."
            )
        )
        messages.append(
            AIMessage(
                f"Assistant answer {i}: based on your profile you have strengths in several areas. "
                "I recommend focusing on coursework and practical experience that builds on those."
            )
        )
    messages.append(HumanMessage("User question 4: what is the next step to keep building on what we have discussed?"))
    return messages


def test_trims_messages_to_fit_within_token_budget():
    conversation = long_conversation()
    summary = [SystemMessage("Running summary of the entire conversation that captures the key points so far.")]
    node = make_summarizer(summary)
    hook = make_pre_model_hook(node, max_messages=2, max_tokens=100, logger=logging.getLogger("test"))

    result = hook({"messages": conversation, "context": {}})

    assert count_tokens_approximately(result["messages"]) <= 100
    assert isinstance(result["messages"][0], SystemMessage)
    assert result["messages"][-1] is conversation[-1]


def test_leaves_messages_untouched_when_within_token_budget():
    conversation = long_conversation()
    summary = [SystemMessage("Running summary of the entire conversation that captures the key points so far.")]
    node = make_summarizer(summary)
    hook = make_pre_model_hook(node, max_messages=2, max_tokens=500, logger=logging.getLogger("test"))

    result = hook({"messages": conversation, "context": {}})

    assert count_tokens_approximately(result["messages"]) <= 500
    assert result["messages"] == summary + conversation[-2:]


def test_short_conversation_is_not_summarized():
    conversation = [HumanMessage("Hi there"), AIMessage("Hello!")]
    node = make_summarizer([SystemMessage("irrelevant")])
    hook = make_pre_model_hook(node, max_messages=5, max_tokens=50, logger=logging.getLogger("test"))

    result = hook({"messages": list(conversation), "context": {}})

    assert result is not None
    assert result["messages"] == conversation


def test_falls_back_to_untrimmed_list_when_trim_is_empty(caplog):
    conversation = long_conversation()
    summary = [HumanMessage("Summary of the conversation.")]
    node = make_summarizer(summary)
    logger = logging.getLogger("test_trim_fallback")
    hook = make_pre_model_hook(node, max_messages=2, max_tokens=1, logger=logger)

    with caplog.at_level(logging.WARNING, logger="test_trim_fallback"):
        result = hook({"messages": conversation, "context": {}})

    assert result["messages"] == summary + conversation[-2:]
    assert "empty message list" in caplog.text


def test_safe_trim_preserves_system_message_and_latest_human_message():
    messages = [SystemMessage("You are a helpful advisor.")]
    messages.extend(long_conversation())

    trimmed = _safe_trim_messages(messages, max_tokens=100, logger=logging.getLogger("test"))

    assert count_tokens_approximately(trimmed) <= 100
    assert isinstance(trimmed[0], SystemMessage)
    assert messages[-1] in trimmed


def test_safe_trim_keeps_tool_call_tail_within_budget():
    """A mid-tool-loop message list (no trailing human) must keep its tool results
    when within budget, so the agent can continue instead of re-planning."""
    from langchain_core.messages import ToolMessage

    tool_call_ai = AIMessage(content="", tool_calls=[{"name": "lif_query", "args": {}, "id": "call_1"}])
    tool_result = ToolMessage(content="Found 3 courses.", tool_call_id="call_1")
    messages = [SystemMessage("Running summary of the conversation."), tool_call_ai, tool_result]

    trimmed = _safe_trim_messages(messages, max_tokens=200, logger=logging.getLogger("test"))

    assert trimmed == messages
    assert tool_result in trimmed
