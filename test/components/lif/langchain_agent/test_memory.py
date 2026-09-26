"""Tests for the agent's pre_model_hook.

Two regressions are guarded here.

Issue #1162: the hook returned the whole `ChatState`, so LangGraph merged `messages`
through the `add_messages` reducer (an APPEND), and the summary was added to the history
every turn instead of replacing it. Context grew monotonically until OpenAI rejected the
request at ~3.5M tokens against a 2M ceiling.

Issue #212: summarizing bounds the message *count* but not the token *size* -- the list
handed to the model was `summary + retained tail` at whatever token cost that came to.
`_safe_trim_messages` caps it, and the tests at the end of this module cover that cap.
"""

import logging
from typing import Any
from unittest import mock

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.graph.message import add_messages

from lif.langchain_agent.memory import _safe_trim_messages, create_summarization_node, make_pre_model_hook

MAX_MESSAGES = 4
# Effectively "never trims". The #1162 and #1160 tests below predate the #212 token cap
# and assert on the summarize-and-retain behavior alone; giving them a budget nothing can
# exceed keeps them testing exactly what they were written to test.
NO_TRIM_BUDGET = 1_000_000
logger = logging.getLogger(__name__)


def _fake_summarizer(summary_text: str = "summary") -> mock.Mock:
    """A summarizer whose invoke() returns a state update, like SummarizationNode does."""
    node = mock.Mock()
    node.invoke.side_effect = lambda state: {
        "summary_output_messages": [AIMessage(content=summary_text)],
        "context": {"running_summary": summary_text},
    }
    return node


def _summarizer_returning(summary_messages: list[Any]) -> mock.Mock:
    """A summarizer emitting a specific message list, for the token-budget tests."""
    node = mock.Mock()
    node.invoke.side_effect = lambda state: {
        "summary_output_messages": summary_messages,
        "context": {"summarized": True},
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


def long_conversation() -> list[Any]:
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


def test_hook_returns_only_safe_keys():
    """The hook must not write `messages` (append reducer) or `remaining_steps` (managed)."""
    hook = make_pre_model_hook(_fake_summarizer(), MAX_MESSAGES, NO_TRIM_BUDGET, logger)
    state = {"messages": [HumanMessage(content=f"m{i}") for i in range(10)], "remaining_steps": 25}

    update = hook(state)

    assert set(update) <= {"llm_input_messages", "context"}
    assert "messages" not in update
    assert "remaining_steps" not in update


def test_llm_input_stays_bounded_across_many_turns():
    """The regression: LLM input must not grow without bound as the conversation runs."""
    hook = make_pre_model_hook(_fake_summarizer(), MAX_MESSAGES, NO_TRIM_BUDGET, logger)
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
    hook = make_pre_model_hook(_fake_summarizer(), MAX_MESSAGES, NO_TRIM_BUDGET, logger)
    messages = [HumanMessage(content=f"m{i}") for i in range(20)]

    update = hook({"messages": messages, "context": {}})
    llm_input = update["llm_input_messages"]

    assert len(llm_input) == MAX_MESSAGES + 1
    assert llm_input[0].content == "summary"
    assert [m.content for m in llm_input[1:]] == [m.content for m in messages[-MAX_MESSAGES:]]


def test_context_is_propagated_so_summarization_is_not_repeated():
    """`context` must persist, or the summarizer re-summarizes on every single call."""
    hook = make_pre_model_hook(_fake_summarizer(), MAX_MESSAGES, NO_TRIM_BUDGET, logger)

    update = hook({"messages": [HumanMessage(content=f"m{i}") for i in range(10)], "context": {}})

    assert update["context"] == {"running_summary": "summary"}


def test_short_conversation_passes_through_untouched():
    summarizer = _fake_summarizer()
    hook = make_pre_model_hook(summarizer, MAX_MESSAGES, NO_TRIM_BUDGET, logger)
    messages = [HumanMessage(content="a"), AIMessage(content="b")]

    update = hook({"messages": messages, "context": {}})

    summarizer.invoke.assert_not_called()
    assert update["llm_input_messages"] == messages


def test_empty_state_still_supplies_llm_input_key():
    """create_react_agent errors unless the hook supplies messages or llm_input_messages."""
    hook = make_pre_model_hook(_fake_summarizer(), MAX_MESSAGES, NO_TRIM_BUDGET, logger)

    update = hook({"messages": [], "context": {}})

    assert update["llm_input_messages"] == []


def test_summarizer_enforces_summary_token_cap():
    """Issue #1160: langmem treats max_summary_tokens as budget estimation only --
    the real cap must be bound onto the model or summaries can exceed the budget
    stack without limit.
    """
    model = mock.Mock()
    max_conversation_size = 2048
    max_summary_size = 512

    node = create_summarization_node(model, max_conversation_size, max_summary_size)

    model.bind.assert_called_once_with(max_tokens=max_summary_size)
    assert node.model is model.bind.return_value
    assert node.max_summary_tokens == max_summary_size


def test_oversized_summary_cannot_crowd_out_retained_messages():
    """Issue #1160: a summary far larger than any budget must not silently reduce
    the model input to the summary alone -- the retained tail always survives.
    """
    hook = make_pre_model_hook(_fake_summarizer(summary_text="x" * 200_000), MAX_MESSAGES, NO_TRIM_BUDGET, logger)
    messages = [HumanMessage(content=f"m{i}") for i in range(20)]

    llm_input = hook({"messages": messages, "context": {}})["llm_input_messages"]

    assert len(llm_input) == MAX_MESSAGES + 1
    assert [m.content for m in llm_input[1:]] == [m.content for m in messages[-MAX_MESSAGES:]]


# --- Issue #212: token budget on the list handed to the model -------------------------


def test_trims_llm_input_to_fit_within_token_budget():
    conversation = long_conversation()
    summary = [SystemMessage("Running summary of the entire conversation that captures the key points so far.")]
    budget = 60
    untrimmed = summary + conversation[-2:]
    # Guard the guard: the untrimmed list has to genuinely exceed the budget, or this
    # test would pass just as well with the trim removed. It sat at 96 tokens against a
    # budget of 100 when first written, and so proved nothing. The budget covers what
    # follows the summary, and the summary's own size is added on top.
    assert count_tokens_approximately(untrimmed) > budget + count_tokens_approximately(summary)

    hook = make_pre_model_hook(_summarizer_returning(summary), 2, budget, logging.getLogger("test"))

    llm_input = hook({"messages": conversation, "context": {}})["llm_input_messages"]

    assert count_tokens_approximately(llm_input[1:]) <= budget
    assert llm_input != untrimmed, "expected the list to be trimmed, not passed through"
    assert isinstance(llm_input[0], SystemMessage)
    assert llm_input[-1] is conversation[-1]


def test_leaves_llm_input_untouched_when_within_token_budget():
    conversation = long_conversation()
    summary = [SystemMessage("Running summary of the entire conversation that captures the key points so far.")]
    hook = make_pre_model_hook(_summarizer_returning(summary), 2, 500, logging.getLogger("test"))

    llm_input = hook({"messages": conversation, "context": {}})["llm_input_messages"]

    assert count_tokens_approximately(llm_input) <= 500
    assert llm_input == summary + conversation[-2:]


def test_falls_back_to_untrimmed_list_when_trim_is_empty(caplog):
    conversation = long_conversation()
    summary = [HumanMessage("Summary of the conversation.")]
    trim_logger = logging.getLogger("test_trim_fallback")
    hook = make_pre_model_hook(_summarizer_returning(summary), 2, 1, trim_logger)

    with caplog.at_level(logging.WARNING, logger="test_trim_fallback"):
        llm_input = hook({"messages": conversation, "context": {}})["llm_input_messages"]

    assert llm_input == summary + conversation[-2:]
    assert "no HumanMessage" in caplog.text


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
    tool_call_ai = AIMessage(content="", tool_calls=[{"name": "lif_query", "args": {}, "id": "call_1"}])
    tool_result = ToolMessage(content="Found 3 courses.", tool_call_id="call_1")
    messages = [SystemMessage("Running summary of the conversation."), tool_call_ai, tool_result]

    trimmed = _safe_trim_messages(messages, max_tokens=200, logger=logging.getLogger("test"))

    assert trimmed == messages
    assert tool_result in trimmed


# --- Review of #1148: the deployed budgets, and where a cut may start -----------------
#
# Every deployment sets LIF_ADVISOR_TRIMMED_MESSAGES_SIZE=384 and MAX_SUMMARY_SIZE=1024.
# With the budget covering the whole list, a summary over ~380 tokens left only the
# summary: non-empty, so no fallback, and the model never saw the user's question.


def _summary_of(tokens: int) -> SystemMessage:
    message = SystemMessage("word " * tokens)
    assert count_tokens_approximately([message]) >= tokens
    return message


def test_summary_larger_than_the_budget_still_keeps_the_latest_question():
    turn = [HumanMessage("What courses did I take?"), AIMessage("You took Algebra."), HumanMessage("And my grades?")]
    messages = [_summary_of(880), *turn]

    trimmed = _safe_trim_messages(messages, max_tokens=384, logger=logging.getLogger("test"))

    assert trimmed[-1] is turn[-1], "the current question must reach the model"
    assert trimmed == messages


def test_an_oversized_tool_result_does_not_reduce_the_input_to_the_summary():
    """A normal GraphQL result (~1,600 tokens) is larger than the whole budget. Sending
    too much beats sending the model a summary with no question to answer."""
    tool_call_ai = AIMessage(content="", tool_calls=[{"name": "lif_query", "args": {}, "id": "call_1"}])
    tool_result = ToolMessage(content="x" * 6_400, tool_call_id="call_1")
    messages = [_summary_of(100), HumanMessage("List my courses."), tool_call_ai, tool_result]

    trimmed = _safe_trim_messages(messages, max_tokens=384, logger=logging.getLogger("test"))

    assert any(isinstance(m, HumanMessage) for m in trimmed)
    assert trimmed != messages[:1]


def test_a_cut_never_starts_the_kept_history_on_an_orphan_tool_message():
    """OpenAI rejects a `tool` message that does not follow the assistant message carrying
    its `tool_calls`. Every budget, including the ones that cut between the two, must keep
    each ToolMessage's AIMessage with it."""
    tool_call_ai = AIMessage(content="", tool_calls=[{"name": "lif_query", "args": {"q": "x"}, "id": "call_9"}])
    messages = [
        SystemMessage("summary " * 30),
        HumanMessage("q1 " * 40),
        tool_call_ai,
        ToolMessage("r " * 120, tool_call_id="call_9"),
        AIMessage("answer " * 20),
        HumanMessage("q2"),
    ]

    for budget in range(1, count_tokens_approximately(messages) + 1):
        trimmed = _safe_trim_messages(messages, max_tokens=budget, logger=logging.getLogger("test"))
        for i, message in enumerate(trimmed):
            if isinstance(message, ToolMessage):
                assert tool_call_ai in trimmed[:i], f"orphan ToolMessage at budget {budget}: {trimmed}"


def test_a_long_summary_does_not_use_up_the_budget_for_the_current_turn():
    """The budget covers what follows the summary. Counting the summary against it would
    leave nothing for the turn, and the list would fall back untrimmed instead of shedding
    the older exchange."""
    older = [HumanMessage("older question " * 60), AIMessage("older answer " * 60)]
    latest = HumanMessage("And my grades?")
    messages = [_summary_of(880), *older, latest]

    trimmed = _safe_trim_messages(messages, max_tokens=100, logger=logging.getLogger("test"))

    assert trimmed == [messages[0], latest]
