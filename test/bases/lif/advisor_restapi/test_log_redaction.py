"""
The Advisor's logout summary is not logged as text (#1319).

The summary describes the learner's conversation, and it was logged next to the username.
"""

import logging
from unittest.mock import AsyncMock, Mock

from lif.advisor_restapi import core

FIELD_VALUE = "Marigold"


async def test_summarization_logs_no_learner_content(caplog):
    agent = Mock()
    agent.ask_agent = AsyncMock(
        return_value={"content": f"The learner {FIELD_VALUE} asked about courses.", "tokens": 10, "cost": 0.5}
    )

    with caplog.at_level(logging.INFO, logger="lif.advisor_restapi.core"):
        await core._safe_summarize(agent, "chat", "learner@example.edu")

    assert "Summarization" in caplog.text
    assert FIELD_VALUE not in caplog.text
