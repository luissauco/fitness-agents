"""Handler del comando /export y callbacks de exportación."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.generators.pdf_nutrition import NutritionPDFGenerator
from src.generators.pdf_progress import ProgressPDFGenerator
from src.generators.xlsx_mesocycle import MesocycleExcelGenerator
from src.telegram_bot.handlers.auth import require_whitelist
from src.telegram_bot.messages import errors as error_msgs
from src.telegram_bot.utils.file_sender import send_document

_logger: Final[logging.Logger] = logging.getLogger(__name__)

_OUTPUT_DIR: Final[Path] = Path("output")

_EXPORT_MENU_TEXT: Final[str] = (
    "<b>Exportar archivos</b>\n\nSelecciona el archivo que quieres recibir:"
)


@require_whitelist
async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el submenú de exportación con botones inline."""
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Mesociclo (Excel)", callback_data="export:mesocycle")],
            [InlineKeyboardButton("Plan nutricional (PDF)", callback_data="export:nutrition")],
            [
                InlineKeyboardButton(
                    "Último informe de progreso (PDF)", callback_data="export:progress"
                )
            ],
        ]
    )
    await update.message.reply_text(_EXPORT_MENU_TEXT, parse_mode="HTML", reply_markup=keyboard)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Procesa los callbacks de export: export:mesocycle, export:nutrition, export:progress."""
    query = update.callback_query
    await query.answer()

    data: str = query.data or ""

    if data == "export:menu":
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Mesociclo (Excel)", callback_data="export:mesocycle")],
                [InlineKeyboardButton("Plan nutricional (PDF)", callback_data="export:nutrition")],
                [
                    InlineKeyboardButton(
                        "Último informe de progreso (PDF)", callback_data="export:progress"
                    )
                ],
            ]
        )
        await query.message.reply_text(_EXPORT_MENU_TEXT, parse_mode="HTML", reply_markup=keyboard)
        return

    chat_id = update.effective_chat.id
    user_id: str = context.bot_data["user_mapping"].resolve_user_id(chat_id)
    container = context.bot_data["container"]

    profile = container.repos.user_profile.get(user_id)
    if not profile:
        await query.message.reply_text(error_msgs.generic_error())
        return

    user_name: str = profile.personal.name

    if data == "export:mesocycle":
        await _export_mesocycle(query, container, user_id, user_name, context)
    elif data == "export:nutrition":
        await _export_nutrition(query, container, user_id, user_name, context)
    elif data == "export:progress":
        await _export_progress(query, container, user_id, user_name, context)


async def _export_mesocycle(
    query: object,
    container: object,
    user_id: str,
    user_name: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Genera y envía el Excel del mesociclo actual."""
    mesocycle = container.repos.mesocycle.get_current(user_id)
    if not mesocycle:
        await query.message.reply_text(
            "No tienes ningún mesociclo activo. Usa /start para crear tu plan.",
            parse_mode="HTML",
        )
        return

    await query.message.reply_text("<i>Generando Excel del mesociclo...</i>", parse_mode="HTML")
    try:
        generator = MesocycleExcelGenerator(output_dir=_OUTPUT_DIR)
        file_path = generator.generate(mesocycle, user_name)
        await send_document(bot=context.bot, chat_id=query.message.chat_id, file_path=file_path)
        _logger.info("export_mesocycle enviado chat_id=%s", query.message.chat_id)
    except Exception:
        _logger.exception("error_export_mesocycle chat_id=%s", query.message.chat_id)
        await query.message.reply_text(error_msgs.generic_error())


async def _export_nutrition(
    query: object,
    container: object,
    user_id: str,
    user_name: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Genera y envía el PDF del plan nutricional."""
    plan = container.repos.nutrition_plan.get_current(user_id)
    if not plan:
        await query.message.reply_text(
            "No tienes ningún plan nutricional activo. Usa /start para crear tu plan.",
            parse_mode="HTML",
        )
        return

    await query.message.reply_text(
        "<i>Generando PDF del plan nutricional...</i>", parse_mode="HTML"
    )
    try:
        generator = NutritionPDFGenerator(output_dir=_OUTPUT_DIR)
        file_path = generator.generate(plan, user_name)
        await send_document(bot=context.bot, chat_id=query.message.chat_id, file_path=file_path)
        _logger.info("export_nutrition enviado chat_id=%s", query.message.chat_id)
    except Exception:
        _logger.exception("error_export_nutrition chat_id=%s", query.message.chat_id)
        await query.message.reply_text(error_msgs.generic_error())


async def _export_progress(
    query: object,
    container: object,
    user_id: str,
    user_name: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Genera y envía el PDF del último informe de progreso."""
    logs = container.repos.progress_log.list_for_user(user_id)
    if not logs:
        await query.message.reply_text(
            "Todavía no tienes ningún informe de progreso. Realiza tu primer /checkin.",
            parse_mode="HTML",
        )
        return

    await query.message.reply_text(
        "<i>Generando PDF del informe de progreso...</i>", parse_mode="HTML"
    )
    try:
        latest_log = logs[0]
        previous_logs = logs[1:]
        generator = ProgressPDFGenerator(output_dir=_OUTPUT_DIR)
        file_path = generator.generate(latest_log, user_name, previous_logs=previous_logs)
        await send_document(bot=context.bot, chat_id=query.message.chat_id, file_path=file_path)
        _logger.info("export_progress enviado chat_id=%s", query.message.chat_id)
    except Exception:
        _logger.exception("error_export_progress chat_id=%s", query.message.chat_id)
        await query.message.reply_text(error_msgs.generic_error())
