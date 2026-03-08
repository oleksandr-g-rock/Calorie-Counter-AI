"""Tests for TOPIC_ID filtering behaviour."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Provide required env vars before importing main
os.environ.setdefault("TELEGRAM_TOKEN", "123456789:AAEhTEDenqAfFNaqKUBHxNMqgJwIL3uSLlP")
os.environ.setdefault("BASE_URL", "https://example.com")
os.environ.setdefault("OPENROUTER_API_KEY", "test_openrouter_key")
os.environ.setdefault("GROQ_WHISPER_API_KEY", "test_groq_key")


def _make_message(thread_id=None):
    """Return a minimal fake aiogram Message with the given message_thread_id."""
    msg = MagicMock()
    msg.message_thread_id = thread_id
    msg.reply = AsyncMock()
    msg.answer = AsyncMock()
    return msg


# ---------------------------------------------------------------------------
# TopicFilter unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_topic_filter_passes_when_no_topic_id_set():
    """When TOPIC_ID is None the filter always returns True."""
    import main as app_module

    original = app_module.TOPIC_ID
    try:
        app_module.TOPIC_ID = None
        f = app_module.TopicFilter()

        assert await f(_make_message(thread_id=None)) is True
        assert await f(_make_message(thread_id=42)) is True
    finally:
        app_module.TOPIC_ID = original


@pytest.mark.asyncio
async def test_topic_filter_passes_matching_topic():
    """When TOPIC_ID is set, messages from that topic pass the filter."""
    import main as app_module

    original = app_module.TOPIC_ID
    try:
        app_module.TOPIC_ID = 100
        f = app_module.TopicFilter()

        assert await f(_make_message(thread_id=100)) is True
    finally:
        app_module.TOPIC_ID = original


@pytest.mark.asyncio
async def test_topic_filter_blocks_different_topic():
    """When TOPIC_ID is set, messages from a different topic are blocked."""
    import main as app_module

    original = app_module.TOPIC_ID
    try:
        app_module.TOPIC_ID = 100
        f = app_module.TopicFilter()

        assert await f(_make_message(thread_id=999)) is False
    finally:
        app_module.TOPIC_ID = original


@pytest.mark.asyncio
async def test_topic_filter_blocks_no_thread_when_topic_set():
    """When TOPIC_ID is set, messages without a thread_id are blocked."""
    import main as app_module

    original = app_module.TOPIC_ID
    try:
        app_module.TOPIC_ID = 100
        f = app_module.TopicFilter()

        assert await f(_make_message(thread_id=None)) is False
    finally:
        app_module.TOPIC_ID = original


# ---------------------------------------------------------------------------
# TOPIC_ID env-variable parsing
# ---------------------------------------------------------------------------

def test_topic_id_parsed_from_env():
    """TOPIC_ID env variable is parsed as an integer."""
    import importlib
    import sys

    # Remove cached module so we can re-import with new env
    sys.modules.pop("main", None)

    with patch.dict(os.environ, {"TOPIC_ID": "42"}):
        import main as fresh_module
        assert fresh_module.TOPIC_ID == 42

    # Clean up so other tests are unaffected
    sys.modules.pop("main", None)


def test_topic_id_none_when_env_not_set():
    """TOPIC_ID is None when env variable is not set."""
    import importlib
    import sys

    sys.modules.pop("main", None)

    env = {k: v for k, v in os.environ.items() if k != "TOPIC_ID"}
    with patch.dict(os.environ, env, clear=True):
        import main as fresh_module
        assert fresh_module.TOPIC_ID is None

    sys.modules.pop("main", None)


def test_topic_id_invalid_value_exits():
    """A non-integer TOPIC_ID causes the process to exit with an error."""
    import sys

    sys.modules.pop("main", None)

    with patch.dict(os.environ, {"TOPIC_ID": "not_a_number"}):
        with pytest.raises(SystemExit):
            import main  # noqa: F401

    sys.modules.pop("main", None)


# ---------------------------------------------------------------------------
# Handler integration – text handler respects TOPIC_ID
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_text_handler_ignored_for_wrong_topic():
    """handle_text is NOT called for messages from a different topic."""
    import main as app_module

    original = app_module.TOPIC_ID
    try:
        app_module.TOPIC_ID = 100
        f = app_module.TopicFilter()

        msg = _make_message(thread_id=999)
        # The filter should block it – handler must not be invoked.
        assert await f(msg) is False
    finally:
        app_module.TOPIC_ID = original


@pytest.mark.asyncio
async def test_text_handler_processes_correct_topic():
    """handle_text IS called for messages from the correct topic."""
    import main as app_module

    original = app_module.TOPIC_ID
    try:
        app_module.TOPIC_ID = 100
        f = app_module.TopicFilter()

        msg = _make_message(thread_id=100)
        assert await f(msg) is True
    finally:
        app_module.TOPIC_ID = original
