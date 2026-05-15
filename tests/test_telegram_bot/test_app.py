"""Tests de la app principal del bot de Telegram."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import CommandHandler

from src.telegram_bot.app import _global_error_handler, _route_photo, _route_text

# ------------------------------------------------------------------ Fixtures


def _make_settings(admin_chat_id: str = "") -> MagicMock:
    """Crea un mock de Settings con los campos necesarios."""
    settings = MagicMock()
    settings.telegram_bot_token = "123:ABC"
    settings.allowed_chat_ids = set()
    settings.telegram_admin_chat_id = admin_chat_id
    return settings


# ------------------------------------------------------------------ build_application


def test_build_application_registra_handlers() -> None:
    """build_application registra handlers para los 5 comandos principales."""
    mock_settings = _make_settings()

    with (
        patch("src.telegram_bot.app.get_settings", return_value=mock_settings),
        patch("src.telegram_bot.app.post_init", new=AsyncMock()),
    ):
        from src.telegram_bot.app import build_application

        app = build_application()

    # Recoge todos los CommandHandlers registrados en todos los grupos
    command_handlers: list[CommandHandler] = []
    for group_handlers in app.handlers.values():
        for h in group_handlers:
            if isinstance(h, CommandHandler):
                command_handlers.append(h)

    registered_commands = {cmd for h in command_handlers for cmd in h.commands}
    assert "start" in registered_commands
    assert "checkin" in registered_commands
    assert "status" in registered_commands
    assert "export" in registered_commands
    assert "help" in registered_commands


# ------------------------------------------------------------------ _route_photo


@pytest.mark.asyncio
async def test_route_photo_va_a_checkin_si_activo() -> None:
    """Con checkin_in_progress=True las fotos se enrutan a checkin_flow."""
    update = MagicMock()
    context = MagicMock()
    context.user_data = {"checkin_in_progress": True}

    with patch("src.telegram_bot.app.checkin_flow.handle_photo", new=AsyncMock()) as mock_checkin:
        with patch("src.telegram_bot.app.intake_flow.handle_photo", new=AsyncMock()) as mock_intake:
            await _route_photo(update, context)

    mock_checkin.assert_awaited_once_with(update, context)
    mock_intake.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_photo_va_a_intake_si_no_activo() -> None:
    """Con checkin_in_progress=False (o ausente) las fotos se enrutan a intake_flow."""
    update = MagicMock()
    context = MagicMock()
    context.user_data = {}

    with patch("src.telegram_bot.app.checkin_flow.handle_photo", new=AsyncMock()) as mock_checkin:
        with patch("src.telegram_bot.app.intake_flow.handle_photo", new=AsyncMock()) as mock_intake:
            await _route_photo(update, context)

    mock_intake.assert_awaited_once_with(update, context)
    mock_checkin.assert_not_awaited()


# ------------------------------------------------------------------ _route_text


@pytest.mark.asyncio
async def test_route_text_va_a_checkin_si_activo() -> None:
    """Con checkin_in_progress=True los mensajes de texto se enrutan a checkin_flow."""
    update = MagicMock()
    context = MagicMock()
    context.user_data = {"checkin_in_progress": True}

    with patch("src.telegram_bot.app.checkin_flow.handle_text", new=AsyncMock()) as mock_checkin:
        with patch("src.telegram_bot.app.intake_flow.handle_text", new=AsyncMock()) as mock_intake:
            await _route_text(update, context)

    mock_checkin.assert_awaited_once_with(update, context)
    mock_intake.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_text_va_a_intake_si_no_activo() -> None:
    """Con checkin_in_progress=False (o ausente) el texto se enruta a intake_flow."""
    update = MagicMock()
    context = MagicMock()
    context.user_data = {}

    with patch("src.telegram_bot.app.checkin_flow.handle_text", new=AsyncMock()) as mock_checkin:
        with patch("src.telegram_bot.app.intake_flow.handle_text", new=AsyncMock()) as mock_intake:
            await _route_text(update, context)

    mock_intake.assert_awaited_once_with(update, context)
    mock_checkin.assert_not_awaited()


# ------------------------------------------------------------------ _global_error_handler


@pytest.mark.asyncio
async def test_global_error_handler_notifica_admin() -> None:
    """Con telegram_admin_chat_id configurado, envía mensaje al admin."""
    update = MagicMock()
    context = MagicMock()
    context.error = ValueError("error de prueba")
    context.bot.send_message = AsyncMock()

    settings = _make_settings(admin_chat_id="999")
    context.bot_data = {"settings": settings}

    await _global_error_handler(update, context)

    context.bot.send_message.assert_awaited_once()
    call_kwargs = context.bot.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == 999
    assert call_kwargs["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_global_error_handler_sin_admin_no_envia() -> None:
    """Sin telegram_admin_chat_id no se intenta enviar mensaje."""
    update = MagicMock()
    context = MagicMock()
    context.error = ValueError("error de prueba")
    context.bot.send_message = AsyncMock()

    settings = _make_settings(admin_chat_id="")
    context.bot_data = {"settings": settings}

    await _global_error_handler(update, context)

    context.bot.send_message.assert_not_awaited()
