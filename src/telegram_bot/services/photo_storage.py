"""Servicio para descargar y guardar fotos de Telegram en disco."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Final, Literal

from telegram import Bot

_logger: Final[logging.Logger] = logging.getLogger(__name__)


class PhotoStorageService:
    """Descarga fotos de Telegram y las guarda en disco."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        base_dir.mkdir(parents=True, exist_ok=True)

    async def save_photo(
        self,
        bot: Bot,
        photo_file_id: str,
        user_id: str,
        category: Literal["body", "gym", "checkin"],
    ) -> Path:
        """Descarga la foto y la guarda en {base_dir}/{user_id}/{category}/{timestamp}.jpg."""
        dest_dir = self.base_dir / user_id / category
        dest_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        dest_path = dest_dir / f"{timestamp}.jpg"

        tg_file = await bot.get_file(photo_file_id)
        await tg_file.download_to_drive(dest_path)

        _logger.info("foto_guardada user_id=%s categoria=%s path=%s", user_id, category, dest_path)
        return dest_path
