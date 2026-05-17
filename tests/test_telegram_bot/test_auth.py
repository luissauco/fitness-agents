"""Tests para el decorador require_whitelist y el UserMappingService."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config.settings import Settings
from src.db.connection import init_schema
from src.db.repositories import TelegramUserRepository
from src.telegram_bot.handlers.auth import require_whitelist
from src.telegram_bot.services.user_mapping import UserMappingService

# ---------------------------------------------------------------- Fixtures


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.sqlite"
    init_schema(path)
    return path


@pytest.fixture
def telegram_repo(db_path: Path) -> TelegramUserRepository:
    return TelegramUserRepository(db_path=db_path)


@pytest.fixture
def settings_with_whitelist() -> Settings:
    return Settings(
        ANTHROPIC_API_KEY="test-key",
        TELEGRAM_ALLOWED_CHAT_IDS="111,222,333",
        TELEGRAM_ADMIN_CHAT_ID="111",
    )


@pytest.fixture
def mapping_service(
    telegram_repo: TelegramUserRepository, settings_with_whitelist: Settings
) -> UserMappingService:
    return UserMappingService(repo=telegram_repo, settings=settings_with_whitelist)


# ------------------------------------------------- Tests require_whitelist


def _make_update(chat_id: int) -> MagicMock:
    """Construye un Update mock con el chat_id dado."""
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_message.reply_text = AsyncMock()
    return update


def _make_context(settings: Settings) -> MagicMock:
    ctx = MagicMock()
    ctx.bot_data = {"settings": settings}
    return ctx


@pytest.mark.asyncio
async def test_whitelist_permite_chat_id_autorizado(settings_with_whitelist):
    """El handler se ejecuta cuando el chat_id está en la whitelist."""
    llamado = False

    @require_whitelist
    async def handler(update, context):
        nonlocal llamado
        llamado = True

    update = _make_update(111)
    ctx = _make_context(settings_with_whitelist)
    await handler(update, ctx)

    assert llamado


@pytest.mark.asyncio
async def test_whitelist_bloquea_chat_id_no_autorizado(settings_with_whitelist):
    """El handler NO se ejecuta y se envía mensaje de rechazo."""
    llamado = False

    @require_whitelist
    async def handler(update, context):
        nonlocal llamado
        llamado = True

    update = _make_update(999)
    ctx = _make_context(settings_with_whitelist)
    await handler(update, ctx)

    assert not llamado
    update.effective_message.reply_text.assert_awaited_once()
    mensaje = update.effective_message.reply_text.call_args[0][0]
    assert "acceso" in mensaje.lower()


# ------------------------------------------------- Tests UserMappingService


def test_primer_start_crea_user_id(mapping_service, telegram_repo):
    """El primer resolve genera un user_id único y lo registra."""
    user_id = mapping_service.resolve_user_id(111)

    assert user_id.startswith("tg_")
    assert telegram_repo.is_registered(111)
    assert telegram_repo.get_by_chat_id(111)[0] == user_id


def test_segundo_start_devuelve_mismo_user_id(mapping_service):
    """Llamadas repetidas al mismo chat_id devuelven el mismo user_id."""
    uid1 = mapping_service.resolve_user_id(222)
    uid2 = mapping_service.resolve_user_id(222)

    assert uid1 == uid2


def test_dos_chat_ids_distintos_dan_user_ids_distintos(mapping_service):
    """Dos usuarios distintos tienen user_ids distintos (aislamiento)."""
    uid1 = mapping_service.resolve_user_id(111)
    uid2 = mapping_service.resolve_user_id(222)

    assert uid1 != uid2


def test_admin_chat_id_registrado_como_admin(mapping_service, telegram_repo):
    """El chat_id admin_chat_id se registra con is_admin=True."""
    mapping_service.resolve_user_id(111)  # 111 es el admin_chat_id en el fixture

    _, is_admin = telegram_repo.get_by_chat_id(111)
    assert is_admin


def test_chat_id_no_admin_registrado_sin_admin(mapping_service, telegram_repo):
    """Un chat_id no admin se registra con is_admin=False."""
    mapping_service.resolve_user_id(222)

    _, is_admin = telegram_repo.get_by_chat_id(222)
    assert not is_admin


def test_is_admin_devuelve_false_para_chat_no_registrado(mapping_service):
    assert not mapping_service.is_admin(999)


def test_is_admin_devuelve_true_para_admin(mapping_service):
    mapping_service.resolve_user_id(111)
    assert mapping_service.is_admin(111)
