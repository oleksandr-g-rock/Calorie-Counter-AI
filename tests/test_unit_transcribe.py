"""Unit tests for transcribe_audio using Groq Whisper API."""
import os
import sys
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Provide required env vars before importing main
# Token must match aiogram format: <int>:<string>
os.environ.setdefault("TELEGRAM_TOKEN", "123456789:AAEhTEDenqAfFNaqKUBHxNMqgJwIL3uSLlP")
os.environ.setdefault("BASE_URL", "https://example.com")
os.environ.setdefault("OPENROUTER_API_KEY", "test_openrouter_key")
os.environ.setdefault("GROQ_WHISPER_API_KEY", "test_groq_key")


def _make_mock_groq_client(text="Hello world"):
    """Return a mock AsyncGroq client whose transcriptions.create returns `text`."""
    transcription_result = MagicMock()
    transcription_result.text = text

    create_mock = AsyncMock(return_value=transcription_result)
    audio_mock = MagicMock()
    audio_mock.transcriptions = MagicMock()
    audio_mock.transcriptions.create = create_mock

    groq_mock = MagicMock()
    groq_mock.audio = audio_mock
    return groq_mock, create_mock


def _make_aiohttp_session(status=200, body=b"audio_bytes"):
    """Return a mock aiohttp.ClientSession context manager."""
    mock_response = AsyncMock()
    mock_response.status = status
    mock_response.read = AsyncMock(return_value=body)

    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_get = AsyncMock(return_value=mock_response)
    mock_get.__aenter__ = AsyncMock(return_value=mock_response)
    mock_get.__aexit__ = AsyncMock(return_value=False)

    session_mock = MagicMock()
    session_mock.get = MagicMock(return_value=mock_response)
    session_mock.__aenter__ = AsyncMock(return_value=session_mock)
    session_mock.__aexit__ = AsyncMock(return_value=False)
    return session_mock, mock_response


@pytest.mark.asyncio
async def test_transcribe_audio_success():
    """transcribe_audio returns the transcription text on success."""
    import main as app_module

    groq_mock, create_mock = _make_mock_groq_client("Привіт, як справи?")
    session_mock, mock_response = _make_aiohttp_session(status=200, body=b"ogg_audio")

    with patch.object(app_module, "groq_client", groq_mock), \
         patch("aiohttp.ClientSession", return_value=session_mock):
        result = await app_module.transcribe_audio("https://api.telegram.org/file/botTOKEN/voice.ogg")

    assert result == "Привіт, як справи?"
    create_mock.assert_awaited_once()
    call_kwargs = create_mock.call_args.kwargs
    assert call_kwargs["model"] == "whisper-large-v3"
    assert call_kwargs["temperature"] == 0
    assert call_kwargs["response_format"] == "verbose_json"
    filename, audio_bytes = call_kwargs["file"]
    assert filename == "voice.ogg"
    assert audio_bytes == b"ogg_audio"


@pytest.mark.asyncio
async def test_transcribe_audio_http_error():
    """transcribe_audio returns an error string when download returns non-200."""
    import main as app_module

    session_mock, mock_response = _make_aiohttp_session(status=404)

    with patch("aiohttp.ClientSession", return_value=session_mock):
        result = await app_module.transcribe_audio("https://api.telegram.org/file/botTOKEN/voice.ogg")

    assert result == "Error: 404"


@pytest.mark.asyncio
async def test_transcribe_audio_download_connection_error():
    """transcribe_audio returns Connection Error when download raises an exception."""
    import main as app_module

    session_mock = MagicMock()
    session_mock.__aenter__ = AsyncMock(return_value=session_mock)
    session_mock.__aexit__ = AsyncMock(return_value=False)
    session_mock.get = MagicMock(side_effect=Exception("timeout"))

    with patch("aiohttp.ClientSession", return_value=session_mock):
        result = await app_module.transcribe_audio("https://api.telegram.org/file/botTOKEN/voice.ogg")

    assert result.startswith("Connection Error:")


@pytest.mark.asyncio
async def test_transcribe_audio_groq_error():
    """transcribe_audio returns unavailable message when Groq raises an exception."""
    import main as app_module

    groq_mock = MagicMock()
    groq_mock.audio = MagicMock()
    groq_mock.audio.transcriptions = MagicMock()
    groq_mock.audio.transcriptions.create = AsyncMock(side_effect=Exception("API error"))

    session_mock, _ = _make_aiohttp_session(status=200, body=b"audio")

    with patch.object(app_module, "groq_client", groq_mock), \
         patch("aiohttp.ClientSession", return_value=session_mock):
        result = await app_module.transcribe_audio("https://api.telegram.org/file/botTOKEN/voice.ogg")

    assert result == "Groq Whisper Service Unavailable."


@pytest.mark.asyncio
async def test_transcribe_audio_english_text():
    """transcribe_audio works for English transcription result."""
    import main as app_module

    groq_mock, create_mock = _make_mock_groq_client("What should I eat for lunch?")
    session_mock, _ = _make_aiohttp_session(status=200, body=b"audio_en")

    with patch.object(app_module, "groq_client", groq_mock), \
         patch("aiohttp.ClientSession", return_value=session_mock):
        result = await app_module.transcribe_audio("https://api.telegram.org/file/botTOKEN/en.ogg")

    assert result == "What should I eat for lunch?"
