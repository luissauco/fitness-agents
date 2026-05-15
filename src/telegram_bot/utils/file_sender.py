"""Utilidad para enviar archivos generados como documentos de Telegram."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

from telegram import Bot

_logger: Final[logging.Logger] = logging.getLogger(__name__)


async def send_document(bot: Bot, chat_id: int, file_path: Path) -> None:
    """Envía un archivo como documento de Telegram. Maneja xlsx y pdf."""
    _logger.info("enviando_documento chat_id=%s archivo=%s", chat_id, file_path.name)
    with file_path.open("rb") as fh:
        await bot.send_document(chat_id=chat_id, document=fh, caption=file_path.name)
