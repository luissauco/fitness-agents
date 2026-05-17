"""Aplicación principal del bot de Telegram."""

from __future__ import annotations

import logging
from typing import Final

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from cli.commands.factory import build_container
from src.config.settings import get_settings
from src.graph.checkpoints import get_state_db_path
from src.graph.workflow import build_workflow
from src.telegram_bot.handlers import checkin, checkin_flow, export, intake_flow, start, status
from src.telegram_bot.handlers import help as help_cmd
from src.telegram_bot.handlers.fallback import unknown_message
from src.telegram_bot.services.scheduler import CheckinReminderScheduler
from src.telegram_bot.services.user_mapping import UserMappingService

_logger: Final[logging.Logger] = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """Inicializa dependencias compartidas en bot_data tras construir la Application."""
    settings = get_settings()
    container = build_container()

    # Abrir checkpointer SQLite y recompilar el workflow con persistencia.
    db_path = get_state_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn: aiosqlite.Connection = await aiosqlite.connect(str(db_path))
    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    container.workflow = build_workflow(container.bundle, checkpointer=saver)
    application.bot_data["_checkpointer_conn"] = conn

    application.bot_data["settings"] = settings
    application.bot_data["container"] = container
    application.bot_data["user_mapping"] = UserMappingService(
        repo=container.repos.telegram_user,
        settings=settings,
    )

    scheduler = CheckinReminderScheduler(application.job_queue, container.repos)
    application.bot_data["scheduler"] = scheduler
    await scheduler.restore_scheduled_reminders()

    _logger.info(
        "Bot inicializado. Whitelist: %s chat IDs",
        len(settings.allowed_chat_ids),
    )


async def post_shutdown(application: Application) -> None:
    """Cierra la conexión del checkpointer SQLite al detener el bot."""
    conn: aiosqlite.Connection | None = application.bot_data.get("_checkpointer_conn")
    if conn is not None:
        await conn.close()


def build_application() -> Application:
    """Construye la Application con todos los handlers registrados."""
    settings = get_settings()

    app = (
        ApplicationBuilder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # --- Comandos ---
    app.add_handler(CommandHandler("start", start.start_command))
    app.add_handler(CommandHandler("checkin", checkin.checkin_command))
    app.add_handler(CommandHandler("status", status.status_command))
    app.add_handler(CommandHandler("export", export.export_command))
    app.add_handler(CommandHandler("help", help_cmd.help_command))

    # --- Callbacks por prefijo (el orden importa) ---
    app.add_handler(CallbackQueryHandler(intake_flow.handle_callback, pattern="^intake:"))
    app.add_handler(CallbackQueryHandler(checkin_flow.handle_callback, pattern="^checkin:"))
    app.add_handler(CallbackQueryHandler(export.handle_callback, pattern="^export:"))

    # --- Mensajes: foto y texto → routing según flujo activo ---
    app.add_handler(MessageHandler(filters.PHOTO, _route_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _route_text))

    # --- Fallback para mensajes no reconocidos ---
    app.add_handler(MessageHandler(filters.ALL, unknown_message))

    # --- Error handler global ---
    app.add_error_handler(_global_error_handler)

    return app


async def _route_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enruta fotos a checkin o intake según el flujo activo."""
    if context.user_data.get("checkin_in_progress"):
        await checkin_flow.handle_photo(update, context)
    else:
        await intake_flow.handle_photo(update, context)


async def _route_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enruta texto a checkin o intake según el flujo activo."""
    if context.user_data.get("checkin_in_progress"):
        await checkin_flow.handle_text(update, context)
    else:
        await intake_flow.handle_text(update, context)


async def _global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Loggea excepciones y notifica al administrador del bot si está configurado."""
    _logger.exception("Error procesando update", exc_info=context.error)

    settings = context.bot_data.get("settings")
    if settings is None:
        return

    admin_chat_id_str: str = settings.TELEGRAM_ADMIN_CHAT_ID
    if not admin_chat_id_str:
        return

    try:
        admin_chat_id = int(admin_chat_id_str)
        error_text = (
            "<b>Error en el bot</b>\n\n"
            f"<code>{type(context.error).__name__}: {context.error}</code>"
        )
        await context.bot.send_message(
            chat_id=admin_chat_id,
            text=error_text,
            parse_mode="HTML",
        )
    except Exception:
        _logger.exception("No se pudo notificar al admin sobre el error")


def run_bot() -> None:
    """Punto de entrada llamado desde la CLI para arrancar el bot con polling."""
    logging.basicConfig(level=logging.INFO)
    app = build_application()
    _logger.info("Bot arrancando con polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
