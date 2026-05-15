"""Handler de fallback para mensajes fuera de cualquier flujo activo."""

from __future__ import annotations

import logging
from typing import Final

from telegram import Update
from telegram.ext import ContextTypes

from src.telegram_bot.messages import errors as error_msgs

_logger: Final[logging.Logger] = logging.getLogger(__name__)


async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responde a mensajes que no encajan en ningún flujo activo."""
    # Si el flujo de check-in está en curso, el checkin_flow lo gestiona; ignoramos.
    if context.user_data.get("checkin_in_progress"):
        return

    _logger.debug(
        "mensaje_no_reconocido chat_id=%s texto=%r",
        update.effective_chat.id,
        update.effective_message.text if update.effective_message else None,
    )
    await update.effective_message.reply_text(error_msgs.not_understood())
