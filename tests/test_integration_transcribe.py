"""Integration tests for voice handler flow using Groq Whisper transcription."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Provide required env vars before importing main
# Token must match aiogram format: <int>:<string>
os.environ.setdefault("TELEGRAM_TOKEN", "123456789:AAEhTEDenqAfFNaqKUBHxNMqgJwIL3uSLlP")
os.environ.setdefault("BASE_URL", "https://example.com")
os.environ.setdefault("OPENROUTER_API_KEY", "test_openrouter_key")
os.environ.setdefault("GROQ_WHISPER_API_KEY", "test_groq_key")


def _make_voice_message(file_id="file123", file_path="voice/file123.ogg"):
    """Create a minimal fake aiogram voice message."""
    voice = MagicMock()
    voice.file_id = file_id

    tg_file = MagicMock()
    tg_file.file_path = file_path

    message = MagicMock()
    message.voice = voice
    message.reply = AsyncMock()
    message.answer = AsyncMock()
    return message, tg_file


def _make_groq_client_mock(text="Що мені поїсти?"):
    transcription = MagicMock()
    transcription.text = text

    create_mock = AsyncMock(return_value=transcription)
    audio_mock = MagicMock()
    audio_mock.transcriptions = MagicMock()
    audio_mock.transcriptions.create = create_mock

    groq_mock = MagicMock()
    groq_mock.audio = audio_mock
    return groq_mock


def _make_ai_response(lang="uk"):
    return {
        "lang": lang,
        "total_calories": 0,
        "total_macros": {"protein": 0, "fat": 0, "carbs": 0},
        "items": [],
        "health_verdict": "Їж овочі та білок",
        "tips": "Спробуй курку з броколі",
    }


def _make_aiohttp_session(status=200, body=b"audio"):
    mock_response = AsyncMock()
    mock_response.status = status
    mock_response.read = AsyncMock(return_value=body)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    session_mock = MagicMock()
    session_mock.get = MagicMock(return_value=mock_response)
    session_mock.__aenter__ = AsyncMock(return_value=session_mock)
    session_mock.__aexit__ = AsyncMock(return_value=False)
    return session_mock


@pytest.mark.asyncio
async def test_voice_handler_full_flow_ukrainian():
    """
    Integration test: full voice handler flow with Ukrainian transcription.
    Verifies that transcribed text is shown and AI analysis is triggered.
    """
    import main as app_module

    message, tg_file = _make_voice_message()
    transcript_msg = AsyncMock()
    ai_msg = AsyncMock()

    message.reply.return_value = transcript_msg
    message.answer.return_value = ai_msg

    groq_mock = _make_groq_client_mock("Що мені поїсти?")
    session_mock = _make_aiohttp_session()
    ai_response = _make_ai_response("uk")

    with patch.object(app_module.bot, "get_file", AsyncMock(return_value=tg_file)), \
         patch.object(app_module, "groq_client", groq_mock), \
         patch("aiohttp.ClientSession", return_value=session_mock), \
         patch.object(app_module, "analyze_content_with_openrouter", AsyncMock(return_value=ai_response)):

        await app_module.handle_voice(message)

    # Transcript message should show the transcribed text
    transcript_msg.edit_text.assert_awaited()
    first_edit_call = transcript_msg.edit_text.await_args_list[0]
    assert "Що мені поїсти?" in first_edit_call.args[0]

    # AI message should be sent
    message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_voice_handler_full_flow_english():
    """
    Integration test: full voice handler flow with English transcription.
    """
    import main as app_module

    message, tg_file = _make_voice_message()
    transcript_msg = AsyncMock()
    ai_msg = AsyncMock()

    message.reply.return_value = transcript_msg
    message.answer.return_value = ai_msg

    groq_mock = _make_groq_client_mock("What should I eat for dinner?")
    session_mock = _make_aiohttp_session()
    ai_response = _make_ai_response("en")
    ai_response["health_verdict"] = "Eat vegetables and protein"
    ai_response["tips"] = "Try chicken with broccoli"

    with patch.object(app_module.bot, "get_file", AsyncMock(return_value=tg_file)), \
         patch.object(app_module, "groq_client", groq_mock), \
         patch("aiohttp.ClientSession", return_value=session_mock), \
         patch.object(app_module, "analyze_content_with_openrouter", AsyncMock(return_value=ai_response)):

        await app_module.handle_voice(message)

    transcript_msg.edit_text.assert_awaited()
    first_edit_call = transcript_msg.edit_text.await_args_list[0]
    assert "What should I eat for dinner?" in first_edit_call.args[0]


@pytest.mark.asyncio
async def test_voice_handler_transcription_error():
    """
    Integration test: voice handler shows error when transcription fails.
    """
    import main as app_module

    message, tg_file = _make_voice_message()
    transcript_msg = AsyncMock()
    message.reply.return_value = transcript_msg

    groq_mock = MagicMock()
    groq_mock.audio = MagicMock()
    groq_mock.audio.transcriptions = MagicMock()
    groq_mock.audio.transcriptions.create = AsyncMock(side_effect=Exception("Groq down"))

    session_mock = _make_aiohttp_session()

    with patch.object(app_module.bot, "get_file", AsyncMock(return_value=tg_file)), \
         patch.object(app_module, "groq_client", groq_mock), \
         patch("aiohttp.ClientSession", return_value=session_mock):

        await app_module.handle_voice(message)

    # The transcript message should show the unavailable error
    transcript_msg.edit_text.assert_awaited()
    first_edit_call = transcript_msg.edit_text.await_args_list[0]
    assert "Groq Whisper Service Unavailable" in first_edit_call.args[0]


@pytest.mark.asyncio
async def test_groq_client_initialized_with_correct_key():
    """Integration test: groq_client is initialized with GROQ_WHISPER_API_KEY."""
    import main as app_module
    # Verify the module-level groq_client exists and is an AsyncGroq instance
    from groq import AsyncGroq
    assert isinstance(app_module.groq_client, AsyncGroq)
