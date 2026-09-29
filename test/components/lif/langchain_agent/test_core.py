import asyncio
import time
from unittest import mock

from langchain_core.messages import AIMessage

from lif.langchain_agent import core

LLM_DELAY_SECONDS = 0.2
_USAGE = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}


def test_sample():
    assert core is not None


class _FakeChatOpenAI:
    """Stands in for ChatOpenAI. The blocking and the async call take the same time, so the
    test measures whether the reframe blocks the event loop, not which call it makes."""

    def __init__(self, **_kwargs):
        pass

    def invoke(self, _prompt):
        time.sleep(LLM_DELAY_SECONDS)
        return AIMessage("reframed question", usage_metadata=_USAGE)

    async def ainvoke(self, _prompt):
        await asyncio.sleep(LLM_DELAY_SECONDS)
        return AIMessage("reframed question", usage_metadata=_USAGE)


class _FakeAgent:
    async def ainvoke(self, _input, config=None):
        return {"messages": [AIMessage("answer", usage_metadata=_USAGE)]}


def _agent() -> core.LIFAIAgent:
    config = {
        "user_identifier": "100001",
        "user_identifier_type": "School-assigned number",
        "user_identifier_type_enum": "SCHOOL_ASSIGNED_NUMBER",
        "user_greeting": "Hi",
        "memory_config": {},
    }
    return core.LIFAIAgent({"chat": _FakeAgent()}, tools=[], config=config)


async def test_concurrent_turns_do_not_wait_on_each_others_reframe():
    """Issue #1106: the reframe ran a blocking `llm.invoke` on the event loop. The Advisor
    runs one uvicorn worker, so every conversation waited for every other conversation's
    reframe, and since #1154 a logout's background summary blocked them too."""
    with mock.patch.object(core, "ChatOpenAI", _FakeChatOpenAI):
        start = time.perf_counter()
        results = await asyncio.gather(*(_agent().ask_agent("chat", "What courses did I take?") for _ in range(3)))
        elapsed = time.perf_counter() - start

    assert [r["content"] for r in results] == ["answer"] * 3
    # One after another, three turns take three times the delay; concurrently, about one.
    assert elapsed < 2 * LLM_DELAY_SECONDS, f"3 concurrent turns took {elapsed:.2f}s"
