from unittest.mock import Mock

from lif.langchain_agent import core


def test_sample():
    assert core is not None


def test_trimmed_messages_size_wired_into_pre_model_hook(monkeypatch):
    assert core.TRIMMED_MESSAGES_SIZE == 384

    fake_summarizer = Mock()
    fake_hook = Mock()

    monkeypatch.setattr(core, "ChatOpenAI", lambda **kwargs: Mock())
    monkeypatch.setattr(
        core, "create_summarization_node", lambda model, max_conversation_size, max_summary_size: fake_summarizer
    )
    monkeypatch.setattr(core, "make_pre_model_hook", Mock(return_value=fake_hook))
    monkeypatch.setattr(core, "create_react_agent", lambda *args, **kwargs: Mock())

    core.LIFAIAgent.create_agent_with_memory("load_profile", [], Mock(), None)

    core.make_pre_model_hook.assert_called_once_with(
        fake_summarizer, core.MESSAGES_TO_KEEP, core.TRIMMED_MESSAGES_SIZE, core.logger
    )
