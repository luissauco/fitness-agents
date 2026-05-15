"""Handler del comando /help."""

from __future__ import annotations

import logging
from typing import Final

from telegram import Update
from telegram.ext import ContextTypes

from src.telegram_bot.handlers.auth import require_whitelist

_logger: Final[logging.Logger] = logging.getLogger(__name__)

_HELP_TEXT: Final[str] = (
    "<b>Comandos disponibles</b>\n\n"
    "/start — Inicia el onboarding o muestra tu estado actual\n"
    "/checkin — Realiza el check-in bisemanal de progreso\n"
    "/status — Muestra el estado de tu plan (mesociclo, próximo check-in)\n"
    "/export — Reenvía tus archivos (mesociclo Excel, dieta PDF, progreso PDF)\n"
    "/help — Muestra esta ayuda\n\n"
    "<i>Si tienes algún problema, usa /start para reiniciar.</i>"
)


@require_whitelist
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra la lista de comandos disponibles."""
    await update.message.reply_text(_HELP_TEXT, parse_mode="HTML")
    _logger.debug("help_command chat_id=%s", update.effective_chat.id)
