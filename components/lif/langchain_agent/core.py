"""
langchain_agent.py

This module defines the LIFAIAgent class for handling LangChain-based AI agent
interactions. It supports query reframing, follow-up question generation, and
profile summarization using prompt templates and MCP (multi-server) clients.

Functions:
    - LIFAIAgent: Class for setting up, invoking, and interacting with an LLM agent.

Environment Variables:
    - TOOL_URL: URL for MCP tools
    - LLM_MODEL_NAME: Name of the LLM model to use
"""

import logging
import os
import uuid
from datetime import datetime

from langchain.prompts import PromptTemplate
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent

from lif.langchain_agent.memory import ChatState, create_summarization_node, make_pre_model_hook


LIF_SEMANTIC_SEARCH_MCP_SERVER_URL = os.environ.get("LIF_SEMANTIC_SEARCH_MCP_SERVER_URL")
LLM_MODEL_NAME = os.environ.get("LIF_ADVISOR_LLM_MODEL_NAME")
LLM_TOKEN_COSTS = {
    "gpt-4o-mini": {"input": 1.1, "output": 4.4, "cached": 0.275},
    "gpt-4.1-mini": {"input": 0.4, "output": 1.6, "cached": 0.1},
    "gpt-4.1-nano": {"input": 0.1, "output": 0.4, "cached": 0.025},
    "gpt-4.1": {"input": 2.0, "output": 8.0, "cached": 0.5},
}
LLM_TOKEN_COST = LLM_TOKEN_COSTS.get(LLM_MODEL_NAME, {})
LLM_INPUT_TOKEN_COST = LLM_TOKEN_COST.get("input", 0)
LLM_OUTPUT_TOKEN_COST = LLM_TOKEN_COST.get("output", 0)
LLM_CACHED_TOKEN_COST = LLM_TOKEN_COST.get("cached", 0)
AGENT_TASKS = os.environ.get("LIF_ADVISOR_AGENT_TASKS", None)
MESSAGES_TO_KEEP = int(os.environ.get("LIF_ADVISOR_MESSAGES_TO_KEEP", "4"))
TRIMMED_MESSAGES_SIZE = int(os.environ.get("LIF_ADVISOR_TRIMMED_MESSAGES_SIZE", "384"))
MAX_CONVERSATION_SIZE = int(os.environ.get("LIF_ADVISOR_MAX_CONVERSATION_SIZE", "384"))
MAX_SUMMARY_SIZE = int(os.environ.get("LIF_ADVISOR_MAX_SUMMARY_SIZE", "128"))

## Agent configuration
CHANNEL = "AI_AGENT"
CHANNEL_IDENTIFIER = "12345"
CHANNEL_IDENTIFIER_TYPE = "ASSIGNED_SERVICE_NUMBER"
AGENT_INTERACTION_TYPE = "ADVISING"

logger = logging.getLogger(__name__)


class LIFAIAgent:
    """LangChain-based AI Agent for processing queries and generating responses."""

    def __init__(self, agents, tools, config):
        """Initializes the LIFAIAgent.

        Args:
            agent: The instantiated LangGraph react agent object.
            config: The user configuration parameters for this agent
        """

        self.agents = agents
        self.tools = tools

        self.start_time = datetime.now()
        self.messages = None

        self.user_identifier = config["user_identifier"]
        self.user_identifier_type = config["user_identifier_type"]
        self.user_identifier_type_enum = config["user_identifier_type_enum"]
        self.user_greeting = config["user_greeting"]
        self.memory_config = config["memory_config"]

    @classmethod
    async def setup(cls, config):
        """Initializes and returns a configured LIFAIAgent instance.

        Returns:
            LIFAIAgent: Configured agent instance.
        """
        if not AGENT_TASKS:
            raise ValueError("LIF_ADVISOR_AGENT_TASKS environment variable is not set.")

        # Get MCP tools
        cls.mcp_client = cls.create_mcp_client()
        tools = await cls.mcp_client.get_tools()

        # Initialize memory
        checkpointer = InMemorySaver()

        # Setup agents for each task types
        agents = {}
        for task in AGENT_TASKS.split(","):
            task = task.strip()
            logger.info(f"Loading agent for task {task}")

            agents[task] = cls.create_agent_with_memory(task, tools, checkpointer, config)

        return cls(agents, tools, config)

    @classmethod
    def create_mcp_client(cls):
        """Creates and returns an MCP client."""
        return MultiServerMCPClient(
            {"mcp-graphql": {"url": LIF_SEMANTIC_SEARCH_MCP_SERVER_URL, "transport": "streamable_http"}}
        )

    @classmethod
    def create_agent_with_memory(cls, task_name, tools, checkpointer, config=None):
        """Creates and returns a LangChain agent with conversation memory."""
        model = ChatOpenAI(model_name=LLM_MODEL_NAME, temperature=0.0)

        base_dir = os.path.dirname(__file__)
        prompt_path = os.path.join(base_dir, "prompts", f"{task_name}.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_text = f.read()

        if task_name == "save_interaction_summary":
            prompt = PromptTemplate.from_template(template=prompt_text).format(
                tools=tools,
                identifier_type=config["user_identifier_type"],
                identifier=config["user_identifier"],
                interaction_id=uuid.uuid4().hex,
                channel=CHANNEL,
                channel_identifier=CHANNEL_IDENTIFIER,
                channel_identifier_type=CHANNEL_IDENTIFIER_TYPE,
                agent_interaction_type=AGENT_INTERACTION_TYPE,
                interaction_start_time=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            )
        else:
            prompt = PromptTemplate.from_template(template=prompt_text).format(tools=tools)

        summarization_node = create_summarization_node(model, MAX_CONVERSATION_SIZE, MAX_SUMMARY_SIZE)
        pre_model_hook = make_pre_model_hook(summarization_node, MESSAGES_TO_KEEP, logger)

        return create_react_agent(
            model,
            tools,
            prompt=prompt,
            state_schema=ChatState,
            pre_model_hook=pre_model_hook,
            checkpointer=checkpointer,
            # debug=True
        )

    async def ask_agent(self, task, message: str) -> dict:
        """Sends a message to the agent and returns its response.

        Args:
            task (str): The task type.
            message (str): The input user message.

        Returns:
            dict: Agent response containing content, tokens, and cost.
        """
        logger.info(f"Query: {message}")

        identifier = self.user_identifier
        identifier_type = self.user_identifier_type
        greeting = self.user_greeting
        config = self.memory_config

        agent = self.agents[task]
        if not agent:
            raise RuntimeError("Agent not initialized! Call setup() first.")

        total_tokens = 0
        total_cost = 0.0

        message = message.strip()
        response = self.reframe_query_with_identifiers(message, identifier, identifier_type, greeting)
        message = response.get("content", "").strip()

        # Add tokens and cost from the reframed query generation
        total_tokens += response.get("tokens", 0)
        total_cost += response.get("cost", 0.0)

        logger.info(f"Reframed query: {message}")

        result = await agent.ainvoke({"messages": [{"role": "user", "content": message}]}, config=config)
        messages = result.get("messages", [])
        self.messages = messages
        final_message = messages[-1] if messages else None

        if not final_message:
            logger.error("No response from agent.")
            return {"content": "", "tokens": 0, "cost": 0.0}

        # Calculate tokens and cost from the agent's response
        tokens, cost = self.calculate_tokens_and_cost(messages)

        # Add tokens and cost from the agent's response
        total_tokens += tokens
        total_cost += cost

        final_response = final_message.content

        response = {"content": final_response, "tokens": total_tokens, "cost": total_cost}
        logger.info(f"Response: {response}")
        return response

    def calculate_tokens_and_cost(self, messages: list) -> tuple:
        """
        Calculates the total token usage and estimated cost for a list of messages.
        Only processes AIMessage instances that have usage_metadata.
        """
        total_input_tokens = 0
        total_output_tokens = 0
        total_cached_tokens = 0

        for message in messages:
            # Check if the message is an AIMessage and has usage_metadata
            if type(message).__name__ == "AIMessage" and hasattr(message, "usage_metadata"):
                usage = message.usage_metadata
                input_token_details = usage.get("input_token_details", {})
                cache_read = input_token_details.get("cache_read", 0)

                total_input_tokens += usage.get("input_tokens", 0) - cache_read
                total_output_tokens += usage.get("output_tokens", 0)
                total_cached_tokens += cache_read

        total_tokens = total_input_tokens + total_output_tokens
        cost = (
            (LLM_INPUT_TOKEN_COST * total_input_tokens) / 1_000_000
            + (LLM_OUTPUT_TOKEN_COST * total_output_tokens) / 1_000_000
            + (LLM_CACHED_TOKEN_COST * total_cached_tokens) / 1_000_000
        )

        logger.info(f"Tokens: {total_input_tokens + total_output_tokens + total_cached_tokens} Cost: {cost}")
        return total_tokens, cost

    def reframe_query_with_identifiers(self, query: str, identifier: str, identifier_type: str, greeting: str) -> str:
        """Reframes the query with identifier info."""
        try:
            base_dir = os.path.dirname(__file__)
            prompt_path = os.path.join(base_dir, "prompts", "prompt_template_query.txt")
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_text = f.read()
            prompt = PromptTemplate.from_template(template=prompt_text).format(
                personal_query=query, identifier_value=identifier, identifier_type=identifier_type, greeting=greeting
            )
            llm = ChatOpenAI(model=LLM_MODEL_NAME)
            response = llm.invoke(prompt)
            tokens, cost = self.calculate_tokens_and_cost([response])
            return {"content": response.content, "tokens": tokens, "cost": cost}
        except Exception:
            logger.exception("Failed to reframe query.")
            raise
