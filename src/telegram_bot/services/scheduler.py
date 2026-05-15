"""Scheduler de recordatorios de check-in bisemanal."""

import logging
from datetime import date, datetime, time, timedelta
from typing import Final

from telegram.ext import ContextTypes, JobQueue

from cli.commands.factory import Repositories
from src.telegram_bot.messages import checkin as checkin_msgs

_logger: Final[logging.Logger] = logging.getLogger(__name__)


class CheckinReminderScheduler:
    """
    Gestiona el recordatorio bisemanal de check-in usando el JobQueue
    de python-telegram-bot (APScheduler).

    Solo gestiona UN tipo de notificación: el recordatorio de check-in.
    """

    def __init__(self, job_queue: JobQueue, repos: Repositories) -> None:
        self._job_queue = job_queue
        self._repos = repos

    def schedule_checkin_reminder(
        self,
        user_id: str,
        chat_id: int,
        checkin_date: date,
    ) -> None:
        """
        Programa un job único que manda el recordatorio en checkin_date a las 10:00.
        Si ya existe un job para este user_id, lo cancela primero.
        """
        run_at = datetime.combine(checkin_date, time(10, 0))
        job_name = f"checkin_reminder_{user_id}"

        # Cancelar job previo si existe
        for job in self._job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()

        self._job_queue.run_once(
            self._send_reminder,
            when=run_at,
            chat_id=chat_id,
            name=job_name,
            data={"user_id": user_id},
        )
        _logger.info("Recordatorio de check-in programado para user_id=%s en %s", user_id, run_at)

    async def _send_reminder(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Callback de APScheduler que envía el recordatorio al usuario."""
        chat_id = context.job.chat_id
        user_id = context.job.data["user_id"]
        _logger.info("Enviando recordatorio de check-in a user_id=%s", user_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text=checkin_msgs.checkin_reminder(),
            parse_mode="HTML",
        )

    async def restore_scheduled_reminders(self) -> None:
        """
        Al arrancar el bot, reprograma los recordatorios pendientes de todos
        los usuarios registrados. El JobQueue NO persiste entre reinicios.

        Para cada usuario en telegram_users:
        1. Busca su user_id
        2. Obtiene el último progress_log para saber next_checkin_date
        3. Si hay fecha futura: reprograma el recordatorio
        """
        telegram_users = self._repos.telegram_user.list_all()  # list[tuple[int, str]]

        for chat_id, user_id in telegram_users:
            try:
                logs = self._repos.progress_log.list_for_user(user_id)
                next_date: date | None = None

                if logs:
                    # list_for_user devuelve los logs más recientes primero
                    latest = logs[0]
                    next_date = latest.date + timedelta(days=14)

                if next_date and next_date > date.today():
                    self.schedule_checkin_reminder(user_id, chat_id, next_date)
                    _logger.info(
                        "Recordatorio restaurado para user_id=%s en %s", user_id, next_date
                    )
            except Exception:
                _logger.exception("Error restaurando recordatorio para user_id=%s", user_id)
