import logging

from langchain_openai import ChatOpenAI
from langmem.short_term import SummarizationNode
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.prebuilt.chat_agent_executor import AgentState
from typing import Any, Callable, NotRequired


def make_pre_model_hook(
    summarizer_node: SummarizationNode, max_messages: int, logger: logging.Logger
) -> Callable[..., Any]:
    """
    This function creates the pre_model_hook used by the agent
    Args:
         summarizer_node: node for summarization
         max_messages: number of messages from last to keep out of summarization.
         logger: logger to log
    Returns:
        Callable: the pre_model_hook callable function .
    """

    # This function will be called every time before the node that calls LLM
    def pre_model_hook(state: ChatState) -> ChatState:
        """Prepares the state for the LLM call by summarizing the messages
        to fit within the token limits of the LLM.  This is useful to keep the context
        within the token limits of the LLM.
        Args:
            state: The current state of the agent.
        Returns:
            state: Updated state with summarized and last max_messages messages.
        """
        if state.get("messages"):
            # If the state already has messages
            # Step 1: Summarize the messages
            summarized_messages = None
            if len(state.get("messages")) > max_messages:
                messages_to_retain = state["messages"][-max_messages:]
                summary_input_messages = state["messages"]
                # ty-ignore: langgraph's AgentState is a loosely-typed TypedDict.
                state["summary_input_messages"] = summary_input_messages  # ty: ignore[invalid-assignment]
                before_context = state.get("context", {}).copy()
                state = summarizer_node.invoke(state)
                after_context = state.get("context", {})

                if before_context != after_context:
                    logger.info(
                        f"Summarized {len(summary_input_messages)} messages into {len(state['summary_output_messages'])} summary messages."
                    )

                summarized_messages = state["summary_output_messages"]

            # TODO Add safe trim_messages here
            # Step 2: Prepare new messages list with summarized messages
            messages = []
            if summarized_messages:
                messages.extend(summarized_messages)
                messages.extend(messages_to_retain)
                state["messages"] = messages

        return state

    return pre_model_hook


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
        model=model,
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
