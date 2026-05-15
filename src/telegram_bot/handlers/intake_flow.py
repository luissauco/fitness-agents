"""Handlers para el flujo de intake (onboarding) del bot de Telegram."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

from telegram import Update
from telegram.ext import ContextTypes

from src.telegram_bot.handlers.auth import require_whitelist
from src.telegram_bot.handlers.start import _typing_indicator
from src.telegram_bot.keyboards.question_keyboard import keyboard_for_question
from src.telegram_bot.messages import intake as intake_msgs
from src.telegram_bot.messages.errors import error_block
from src.telegram_bot.services.photo_storage import PhotoStorageService
from src.telegram_bot.services.workflow_runner import WorkflowInput, WorkflowOutput, WorkflowRunner
from src.telegram_bot.utils.file_sender import send_document

_logger: Final[logging.Logger] = logging.getLogger(__name__)

_PHOTO_BASE_DIR = Path("data/photos")


async def _send_workflow_output(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    output: WorkflowOutput,
    user_id: str,
) -> None:
    """Traduce un WorkflowOutput a mensajes de Telegram.

    1. Si hay errores: envía bloque de error.
    2. Si hay assistant_message: envía con teclado si hay current_question.
    3. Para cada archivo generado: envía como documento.
    4. Si is_complete y next_checkin_date: programa recordatorio de check-in.
    """
    chat_id = update.effective_chat.id
    message = update.effective_message

    if output.errors:
        await message.reply_text(error_block(output.errors), parse_mode="HTML")

    if output.assistant_message:
        keyboard = None
        if output.current_question is not None:
            keyboard = keyboard_for_question(output.current_question)
        await message.reply_text(
            output.assistant_message,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

        # Pista para MULTI_SELECT
        if output.current_question is not None and output.current_question.options:
            from src.models.questionnaire import QuestionType

            if output.current_question.question_type == QuestionType.MULTI_SELECT:
                await message.reply_text(
                    intake_msgs.multi_select_hint(output.current_question.options),
                    parse_mode="HTML",
                )

    for file_path in output.generated_files:
        try:
            await send_document(context.bot, chat_id, file_path)
        except Exception:
            _logger.exception("error_enviando_documento archivo=%s", file_path)

    if output.is_complete and output.next_checkin_date:
        scheduler = context.bot_data.get("scheduler")
        if scheduler is not None:
            scheduler.schedule_checkin_reminder(user_id, chat_id, output.next_checkin_date)


@require_whitelist
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Texto libre durante el flujo de intake."""
    chat_id = update.effective_chat.id
    user_mapping = context.bot_data["user_mapping"]
    container = context.bot_data["container"]

    user_id: str = user_mapping.resolve_user_id(chat_id)
    user_message: str = update.message.text or ""

    runner = WorkflowRunner(container.workflow, container.repos)
    async with _typing_indicator(update, context):
        output = await runner.invoke(WorkflowInput(user_id=user_id, user_message=user_message))

    await _send_workflow_output(update, context, output, user_id)


@require_whitelist
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Foto enviada durante el flujo de intake."""
    chat_id = update.effective_chat.id
    user_mapping = context.bot_data["user_mapping"]
    container = context.bot_data["container"]

    user_id: str = user_mapping.resolve_user_id(chat_id)

    photo_storage = PhotoStorageService(_PHOTO_BASE_DIR)
    # Usar la foto de mayor resolución disponible
    photo = update.message.photo[-1]
    saved_path = await photo_storage.save_photo(
        bot=context.bot,
        photo_file_id=photo.file_id,
        user_id=user_id,
        category="body",
    )

    runner = WorkflowRunner(container.workflow, container.repos)
    async with _typing_indicator(update, context):
        output = await runner.invoke(WorkflowInput(user_id=user_id, image_paths=[saved_path]))

    await _send_workflow_output(update, context, output, user_id)


@require_whitelist
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback query con patrón ^intake: generado por los teclados inline."""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    user_mapping = context.bot_data["user_mapping"]
    container = context.bot_data["container"]

    user_id: str = user_mapping.resolve_user_id(chat_id)
    value: str = query.data.split(":", 1)[1]

    runner = WorkflowRunner(container.workflow, container.repos)
    async with _typing_indicator(update, context):
        output = await runner.invoke(WorkflowInput(user_id=user_id, user_message=value))

    await _send_workflow_output(update, context, output, user_id)
