import logging

from langchain_openai import ChatOpenAI
from langmem.short_term import SummarizationNode
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from langgraph.prebuilt.chat_agent_executor import AgentState
from typing import Any, Callable, NotRequired


def make_pre_model_hook(
    summarizer_node: SummarizationNode, max_messages: int, max_tokens: int, logger: logging.Logger
) -> Callable[..., Any]:
    """
    This function creates the pre_model_hook used by the agent
    Args:
         summarizer_node: node for summarization
         max_messages: number of messages from last to keep out of summarization.
         max_tokens: max token budget for the messages after the summary sent to the LLM.
         logger: logger to log
    Returns:
        Callable: the pre_model_hook callable function .
    """

    # This function will be called every time before the node that calls LLM
    def pre_model_hook(state: ChatState) -> dict[str, Any]:
        """Prepares the input for the LLM call by summarizing the messages
        to fit within the token limits of the LLM.  This is useful to keep the context
        within the token limits of the LLM.

        The return value is a *state update*, not a replacement state. `create_react_agent`
        merges it into the graph state, and `AgentState.messages` carries an `add_messages`
        reducer that APPENDS rather than replaces. Returning `messages` here would therefore
        grow the history on every turn instead of trimming it, so the trimmed list is handed
        to the model via `llm_input_messages`, which feeds the LLM without mutating `messages`.
        Only keys that genuinely need to persist are returned -- `context` must, so the
        summarizer can tell it already summarized. `remaining_steps` is a managed value and
        must never be written back.

        Args:
            state: The current state of the agent.
        Returns:
            dict: State update carrying the messages to send to the LLM.
        """
        messages = list(state.get("messages") or [])
        context: dict[str, Any] = dict(state.get("context") or {})

        if not messages:
            return {"llm_input_messages": messages, "context": context}

        llm_input_messages = messages

        if len(messages) > max_messages:
            messages_to_retain = messages[-max_messages:]
            before_context = dict(context)

            summarizer_state: dict[str, Any] = {**state}
            summarizer_state["summary_input_messages"] = messages
            summarizer_result = summarizer_node.invoke(summarizer_state)

            context = dict(summarizer_result.get("context") or context)
            summarized_messages = list(summarizer_result.get("summary_output_messages") or [])

            if before_context != context:
                logger.info("Summarized %d messages into %d summary messages.", len(messages), len(summarized_messages))

            # NOTE: _safe_trim_messages runs only on this post-summarization path - a
            # conversation at or below max_messages goes to the LLM untrimmed regardless
            # of its token count.  Enforcing the budget before summarization is tracked
            # as issue #718.
            if summarized_messages:
                llm_input_messages = _safe_trim_messages(
                    [*summarized_messages, *messages_to_retain], max_tokens, logger
                )

        return {"llm_input_messages": llm_input_messages, "context": context}

    return pre_model_hook


def _safe_trim_messages(messages: list[Any], max_tokens: int, logger: logging.Logger) -> list[Any]:
    """
    Trim a message list so the messages after a leading SystemMessage summary fit within
    max_tokens, preserving the summary and the most recent messages.  Falls back to the
    untrimmed list if the trim would leave no HumanMessage, since the current question
    must reach the model.
    Args:
        messages: The message list to trim.
        max_tokens: Max token count of the messages after the summary.  The summary is
            always kept and its size is added on top, so a long summary cannot use up
            the budget meant for the current turn.
        logger: logger to log.
    Returns:
        list: the trimmed message list, or the original list if no HumanMessage survives.
    """
    summary_tokens = (
        count_tokens_approximately(messages[:1]) if messages and isinstance(messages[0], SystemMessage) else 0
    )
    # Only cut when over budget.  start_on applies even when everything fits, and would
    # then drop a leading AIMessage from the retained window for no reason.
    if count_tokens_approximately(messages) <= max_tokens + summary_tokens:
        return messages
    # strategy="last" keeps the most recent messages and trims the oldest first.
    # include_system=True protects the SystemMessage summary at index 0.
    # start_on="human" makes the kept history (after the summary) start on a
    # HumanMessage, so a cut can never keep a ToolMessage without the AIMessage carrying
    # its tool_calls, which OpenAI rejects.  It constrains only the start: trailing AI
    # and tool messages that fit are still kept.
    trimmed = trim_messages(
        messages,
        token_counter=count_tokens_approximately,
        max_tokens=max_tokens + summary_tokens,
        strategy="last",
        include_system=True,
        start_on="human",
    )
    if not any(isinstance(m, HumanMessage) for m in trimmed):
        logger.warning(
            f"Trimming left no HumanMessage (the current turn does not fit the {max_tokens}-token budget) "
            f"- falling back to the untrimmed {len(messages)} messages."
        )
        return messages
    return trimmed


def create_summarization_node(
    model: ChatOpenAI, max_conversation_size: int = 384, max_summary_size: int = 128
) -> SummarizationNode:
    """
    Creates a SummarizationNode that summarizes the conversation history
    before sending it to the LLM.  This is useful to keep the context
    within the token limits of the LLM.
    Args:
        model: The LLM model to use for summarization.
        max_conversation_size: The maximum limit of the conversation history when summarization triggers.
        max_summary_size: The maximum size of the summary to be generated.
    Returns:
        SummarizationNode: A node that summarizes the conversation history.
    """
    return SummarizationNode(
        token_counter=count_tokens_approximately,
        model=model.bind(max_tokens=max_summary_size),
        max_tokens=max_conversation_size,
        max_summary_tokens=max_summary_size,
        input_messages_key="summary_input_messages",
        output_messages_key="summary_output_messages",
    )


class ChatState(AgentState):
    """A custom state class that extends AgentState to include
    a context dictionary for tracking previous summary information
    """

    # NOTE: we're adding this key to keep track of previous summary information
    # to make sure we're not summarizing on every LLM call
    context: dict[str, Any]
    summary_input_messages: list[Any]
    use_summary_prompt: NotRequired[bool]
