"""Decorador de whitelist para handlers de Telegram."""

from __future__ import annotations

import logging
from functools import wraps
from typing import Final

from telegram import Update
from telegram.ext import ContextTypes

_logger: Final[logging.Logger] = logging.getLogger(__name__)


def require_whitelist(func):
    """Bloquea acceso a chat_ids no incluidos en la whitelist de settings."""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        settings = context.bot_data["settings"]

        if chat_id not in settings.allowed_chat_ids:
            _logger.warning("acceso_denegado chat_id=%s", chat_id)
            await update.effective_message.reply_text(
                "No tienes acceso a este bot. Contacta con el administrador."
            )
            return

        return await func(update, context)

    return wrapper
