"""Handler del comando /start."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from src.telegram_bot.handlers.auth import require_whitelist
from src.telegram_bot.messages import intake as intake_msgs
from src.telegram_bot.services.workflow_runner import WorkflowInput, WorkflowRunner

_logger: Final[logging.Logger] = logging.getLogger(__name__)


@asynccontextmanager
async def _typing_indicator(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> AsyncIterator[None]:
    """Envía la acción «escribiendo» cada 4 s mientras el context manager está activo."""
    stop_event = asyncio.Event()

    async def _loop() -> None:
        while not stop_event.is_set():
            try:
                await context.bot.send_chat_action(
                    chat_id=update.effective_chat.id,
                    action=ChatAction.TYPING,
                )
            except Exception:  # noqa: BLE001
                pass
            try:
                await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=4.0)
            except TimeoutError:
                pass

    task = asyncio.create_task(_loop())
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@require_whitelist
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start — si el usuario es nuevo: onboarding. Si ya existe: muestra estado."""
    from src.telegram_bot.handlers.intake_flow import _send_workflow_output  # evitar ciclo

    chat_id = update.effective_chat.id
    user_mapping = context.bot_data["user_mapping"]
    container = context.bot_data["container"]

    user_id: str = user_mapping.resolve_user_id(chat_id)  # síncrono

    profile = container.repos.user_profile.get(user_id)
    if profile:
        mesocycle = container.repos.mesocycle.get_current(user_id)
        if mesocycle:
            await update.message.reply_text(
                intake_msgs.welcome_back(profile.personal.name),
                parse_mode="HTML",
            )
            return
        # Perfil existe pero sin mesociclo activo → regenerar plan sin intake.
        _logger.info("start.regenerate_plan user_id=%s", user_id)
        runner = WorkflowRunner(container.workflow, container.repos)
        async with _typing_indicator(update, context):
            output = await runner.invoke(WorkflowInput(user_id=user_id, regenerate_plan=True))
        await _send_workflow_output(update, context, output, user_id)
        return

    await update.message.reply_text(intake_msgs.onboarding_intro(), parse_mode="HTML")

    runner = WorkflowRunner(container.workflow, container.repos)
    async with _typing_indicator(update, context):
        output = await runner.invoke(WorkflowInput(user_id=user_id, phase_hint="onboarding"))

    await _send_workflow_output(update, context, output, user_id)
