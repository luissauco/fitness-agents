"""Servicio que resuelve chat_id de Telegram a user_id interno del sistema."""

from __future__ import annotations

import logging
import uuid
from typing import Final

from src.config.settings import Settings
from src.db.repositories import TelegramUserRepository

_logger: Final[logging.Logger] = logging.getLogger(__name__)


class UserMappingService:
    """Resuelve chat_id de Telegram a user_id del sistema.

    Cada chat_id autorizado tiene su propio user_id, garantizando aislamiento
    total de estado entre usuarios distintos en el checkpointer LangGraph.
    """

    def __init__(self, repo: TelegramUserRepository, settings: Settings) -> None:
        self._repo = repo
        self._settings = settings

    def resolve_user_id(self, chat_id: int) -> str:
        """Devuelve el user_id para el chat_id.

        Si es la primera vez, genera un user_id único y lo registra.
        """
        result = self._repo.get_by_chat_id(chat_id)
        if result is not None:
            user_id, _ = result
            return user_id

        is_admin = str(chat_id) == self._settings.telegram_admin_chat_id
        user_id = f"tg_{uuid.uuid4().hex[:10]}"
        self._repo.register(chat_id=chat_id, user_id=user_id, is_admin=is_admin)
        _logger.info("nuevo_usuario chat_id=%s user_id=%s", chat_id, user_id)
        return user_id

    def is_admin(self, chat_id: int) -> bool:
        """True si el chat_id tiene rol administrador."""
        result = self._repo.get_by_chat_id(chat_id)
        if result is None:
            return False
        _, admin = result
        return admin
