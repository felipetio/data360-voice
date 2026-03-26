"""Unit tests for streaming Claude API integration in app/chat.py."""

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def set_required_env_vars(monkeypatch):
    """Provide required env vars so Settings and app/chat load without a .env file."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@localhost:5432/testdb")
    monkeypatch.setenv("MCP_SERVER_URL", "http://localhost:8001")
    monkeypatch.setenv("CONVERSATION_HISTORY_LIMIT", "10")


class FakeStream:
    """Fake async context manager simulating anthropic streaming response."""

    def __init__(self, tokens=None):
        self._tokens = tokens or ["Hello", ", ", "world", "!"]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    @property
    def text_stream(self):
        async def _gen():
            for token in self._tokens:
                yield token

        return _gen()


class FakeStreamError:
    """Fake async context manager that raises on entry."""

    def __init__(self, exc):
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, *_):
        pass


def _make_fake_cl_message():
    """Build a mock cl.Message that accumulates tokens into .content."""
    msg = AsyncMock()
    accumulated = []

    async def stream_token(text):
        accumulated.append(text)
        msg.content = "".join(accumulated)

    msg.stream_token = stream_token
    msg.content = ""
    msg.update = AsyncMock()
    msg.send = AsyncMock()
    msg.remove = AsyncMock()
    return msg


@pytest.fixture()
def reload_chat():
    """Reload app.chat after env vars are patched so settings is re-instantiated."""
    import app.chat
    import app.config

    importlib.reload(app.config)
    importlib.reload(app.chat)
    return app.chat


class TestStreamingResponse:
    async def test_normal_streaming_assembles_correct_content(self, reload_chat):
        """Happy-path: tokens are streamed and message content is assembled."""
        tokens = ["Hello", ", ", "world", "!"]
        msg_mock = _make_fake_cl_message()

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", return_value=FakeStream(tokens)),
        ):
            session_mock.get.return_value = []
            session_mock.set = MagicMock()

            incoming = MagicMock()
            incoming.content = "What is the GDP of Kenya?"

            await reload_chat.on_message(incoming)

        assert msg_mock.content == "Hello, world!"
        msg_mock.update.assert_awaited_once()

    async def test_assistant_reply_appended_to_history(self, reload_chat):
        """After a successful response, the assistant message is stored in history."""
        tokens = ["Hello"]
        msg_mock = _make_fake_cl_message()

        captured_history = []

        def fake_set(key, value):
            if key == "history":
                captured_history.clear()
                captured_history.extend(value)

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", return_value=FakeStream(tokens)),
        ):
            session_mock.get.return_value = []
            session_mock.set.side_effect = fake_set

            incoming = MagicMock()
            incoming.content = "Hi"

            await reload_chat.on_message(incoming)

        assert len(captured_history) == 2
        assert captured_history[0] == {"role": "user", "content": "Hi"}
        assert captured_history[1]["role"] == "assistant"

    async def test_history_trimmed_to_limit(self, reload_chat):
        """History is trimmed to conversation_history_limit before each API call."""
        tokens = ["ok"]
        msg_mock = _make_fake_cl_message()

        # Pre-populate history with 20 messages (well above any limit)
        pre_history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"} for i in range(20)]

        captured_messages = []

        def fake_stream(**kwargs):
            # Deep-copy messages at call time to avoid mutation after stream
            import copy

            captured_messages.extend(copy.deepcopy(kwargs.get("messages", [])))
            return FakeStream(tokens)

        limit = 4
        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
            patch("app.chat.settings") as settings_mock,
        ):
            settings_mock.conversation_history_limit = limit
            session_mock.get.return_value = pre_history.copy()
            session_mock.set = MagicMock()

            incoming = MagicMock()
            incoming.content = "new message"

            await reload_chat.on_message(incoming)

        # messages passed to stream should be trimmed to last `limit`
        assert len(captured_messages) <= limit

    async def test_system_prompt_included_in_every_call(self, reload_chat):
        """system=SYSTEM_PROMPT must be present in every API call."""
        from app.prompts import SYSTEM_PROMPT

        tokens = ["response"]
        msg_mock = _make_fake_cl_message()
        captured_call_args = {}

        def fake_stream(**kwargs):
            captured_call_args.update(kwargs)
            return FakeStream(tokens)

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
        ):
            session_mock.get.return_value = []
            session_mock.set = MagicMock()

            incoming = MagicMock()
            incoming.content = "test"

            await reload_chat.on_message(incoming)

        assert captured_call_args.get("system") == SYSTEM_PROMPT

    async def test_conversation_history_passed_to_api(self, reload_chat):
        """Prior conversation turns are included in the messages list."""
        tokens = ["second response"]
        msg_mock = _make_fake_cl_message()
        captured_messages = []

        def fake_stream(**kwargs):
            # Deep-copy to capture snapshot before any post-stream mutation
            import copy

            captured_messages.extend(copy.deepcopy(kwargs.get("messages", [])))
            return FakeStream(tokens)

        existing_history = [
            {"role": "user", "content": "first message"},
            {"role": "assistant", "content": "first response"},
        ]

        with (
            patch("app.chat.cl.Message", return_value=msg_mock),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", side_effect=fake_stream),
        ):
            session_mock.get.return_value = existing_history.copy()
            session_mock.set = MagicMock()

            incoming = MagicMock()
            incoming.content = "second message"

            await reload_chat.on_message(incoming)

        roles = [m["role"] for m in captured_messages]
        assert "user" in roles
        assert "assistant" in roles
        # new user message should be last in the snapshot passed to the API
        assert captured_messages[-1]["role"] == "user"
        assert captured_messages[-1]["content"] == "second message"


class TestErrorHandling:
    async def test_api_error_surfaces_as_ui_message(self, reload_chat):
        """Any exception during the API call must produce a visible error message."""
        error_msg_mock = AsyncMock()
        error_msg_mock.send = AsyncMock()
        streaming_msg_mock = AsyncMock()
        streaming_msg_mock.send = AsyncMock()
        streaming_msg_mock.remove = AsyncMock()
        streaming_msg_mock.content = ""

        call_count = 0

        def make_message(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return streaming_msg_mock
            return error_msg_mock

        exc = Exception("Simulated Anthropic authentication failure")

        with (
            patch("app.chat.cl.Message", side_effect=make_message),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", return_value=FakeStreamError(exc)),
        ):
            session_mock.get.return_value = []
            session_mock.set = MagicMock()

            incoming = MagicMock()
            incoming.content = "trigger error"

            await reload_chat.on_message(incoming)

        # The streaming placeholder must be removed
        streaming_msg_mock.remove.assert_awaited_once()
        # An error message must have been sent
        error_msg_mock.send.assert_awaited_once()

    async def test_network_error_surfaces_as_ui_message(self, reload_chat):
        """httpx connection errors must also be surfaced, not silently swallowed."""
        import httpx

        error_msg_mock = AsyncMock()
        error_msg_mock.send = AsyncMock()
        streaming_msg_mock = AsyncMock()
        streaming_msg_mock.send = AsyncMock()
        streaming_msg_mock.remove = AsyncMock()
        streaming_msg_mock.content = ""

        call_count = 0

        def make_message(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return streaming_msg_mock
            return error_msg_mock

        exc = httpx.ConnectError("Connection refused")

        with (
            patch("app.chat.cl.Message", side_effect=make_message),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", return_value=FakeStreamError(exc)),
        ):
            session_mock.get.return_value = []
            session_mock.set = MagicMock()

            incoming = MagicMock()
            incoming.content = "trigger network error"

            await reload_chat.on_message(incoming)

        streaming_msg_mock.remove.assert_awaited_once()
        error_msg_mock.send.assert_awaited_once()

    async def test_error_message_contains_warning_text(self, reload_chat):
        """The error message content must start with the expected warning emoji."""
        sent_messages = []

        streaming_msg_mock = AsyncMock()
        streaming_msg_mock.send = AsyncMock()
        streaming_msg_mock.remove = AsyncMock()
        streaming_msg_mock.content = ""

        class CapturingMessage:
            def __init__(self, content="", **kwargs):
                self.content = content
                sent_messages.append(self)

            async def send(self):
                pass

        call_count = 0

        def make_message(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return streaming_msg_mock
            return CapturingMessage(**kwargs)

        exc = RuntimeError("Some error")

        with (
            patch("app.chat.cl.Message", side_effect=make_message),
            patch("app.chat.cl.user_session") as session_mock,
            patch("app.chat.client.messages.stream", return_value=FakeStreamError(exc)),
        ):
            session_mock.get.return_value = []
            session_mock.set = MagicMock()

            incoming = MagicMock()
            incoming.content = "trigger error"

            await reload_chat.on_message(incoming)

        assert len(sent_messages) == 1
        assert sent_messages[0].content.startswith("⚠️")


class TestConfig:
    def test_config_loads_conversation_history_limit(self, monkeypatch):
        """CONVERSATION_HISTORY_LIMIT env var is read correctly."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        monkeypatch.setenv("CONVERSATION_HISTORY_LIMIT", "5")

        from app.config import Settings

        settings = Settings(_env_file=None)
        assert settings.conversation_history_limit == 5

    def test_config_default_history_limit_is_10(self, monkeypatch):
        """Default conversation_history_limit is 10 when env var is not set."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        monkeypatch.delenv("CONVERSATION_HISTORY_LIMIT", raising=False)

        from app.config import Settings

        settings = Settings(_env_file=None)
        assert settings.conversation_history_limit == 10
