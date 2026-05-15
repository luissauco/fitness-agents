"""Handler del comando /status."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Final

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.telegram_bot.handlers.auth import require_whitelist
from src.telegram_bot.messages import status as status_msgs

_logger: Final[logging.Logger] = logging.getLogger(__name__)


def _recent_output_files(user_name: str, output_dir: Path, max_files: int = 3) -> list[str]:
    """Devuelve los nombres de los archivos generados más recientes para el usuario."""
    if not output_dir.exists():
        return []
    safe_name = user_name.replace(" ", "_")
    matching = sorted(
        (f for f in output_dir.iterdir() if f.is_file() and safe_name in f.name),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return [f.name for f in matching[:max_files]]


def _next_checkin_date(user_id: str, container: object) -> date | None:
    """Calcula la fecha del próximo check-in a partir del último progress_log."""
    logs = container.repos.progress_log.list_for_user(user_id)
    if logs:
        return logs[0].date + timedelta(days=14)
    # Si no hay logs, el próximo check-in es 14 días desde el inicio del mesociclo.
    mesocycle = container.repos.mesocycle.get_current(user_id)
    if mesocycle:
        return mesocycle.start_date + timedelta(days=14)
    return None


@require_whitelist
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el estado actual del usuario: mesociclo, próximo check-in, archivos."""
    chat_id = update.effective_chat.id
    user_id: str = context.bot_data["user_mapping"].resolve_user_id(chat_id)
    container = context.bot_data["container"]

    profile = container.repos.user_profile.get(user_id)
    if not profile:
        await update.message.reply_text(status_msgs.no_profile_yet())
        return

    mesocycle = container.repos.mesocycle.get_current(user_id)

    mesocycle_name: str | None = mesocycle.name if mesocycle else None
    microcycle_current: int | None = None
    microcycle_total: int | None = None
    if mesocycle:
        current_micro = mesocycle.current_microcycle
        if current_micro:
            microcycle_current = current_micro.number
        microcycle_total = len(mesocycle.microcycles)

    next_checkin = _next_checkin_date(user_id, container)

    output_dir = Path("output")
    user_name: str = profile.personal.name
    recent_files = _recent_output_files(user_name, output_dir)

    text = status_msgs.status_message(
        name=user_name,
        mesocycle_name=mesocycle_name,
        microcycle_current=microcycle_current,
        microcycle_total=microcycle_total,
        next_checkin=next_checkin,
        recent_files=recent_files,
    )

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Hacer check-in", callback_data="action:checkin")],
            [InlineKeyboardButton("Exportar archivos", callback_data="export:menu")],
        ]
    )

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
    _logger.info("status_command chat_id=%s user_id=%s", chat_id, user_id)
