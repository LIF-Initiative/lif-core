"""
The Advisor agent keeps learner identifiers and record content out of its logs (#1319).

A turn logs the user's question, the question reframed with the learner's identifier, and the
answer, which describes the learner's record. The test asserts that the turn logged, and that
neither the identifier nor a field value from the answer appears in the captured output.
"""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from lif.langchain_agent import core

IDENTIFIER = "SENTINEL-ID-4471"
FIELD_VALUE = "Marigold"


async def test_ask_agent_logs_no_learner_data(monkeypatch, caplog):
    react_agent = Mock()
    react_agent.ainvoke = AsyncMock(
        return_value={"messages": [SimpleNamespace(content=f"Your family name is {FIELD_VALUE}.")]}
    )
    agent = core.LIFAIAgent(
        agents={"chat": react_agent},
        tools=[],
        config={
            "user_identifier": IDENTIFIER,
            "user_identifier_type": "School-assigned number",
            "user_identifier_type_enum": None,
            "user_greeting": "Hi",
            "memory_config": {},
        },
    )
    monkeypatch.setattr(
        agent,
        "reframe_query_with_identifiers",
        Mock(return_value={"content": f"What is the family name of learner {IDENTIFIER}?", "tokens": 3, "cost": 0.1}),
    )

    with caplog.at_level(logging.INFO, logger="lif.langchain_agent.core"):
        response = await agent.ask_agent("chat", f"Hi, I am {FIELD_VALUE}. What is my family name?")

    assert FIELD_VALUE in response["content"]
    assert "Reframed query" in caplog.text
    assert "Response" in caplog.text
    assert IDENTIFIER not in caplog.text
    assert FIELD_VALUE not in caplog.text
