"""Tests del scheduler de recordatorios de check-in bisemanal."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.telegram_bot.services.scheduler import CheckinReminderScheduler

# ---------------------------------------------------------------- Helpers


def _make_scheduler(
    jobs_by_name: list | None = None,
    telegram_users: list[tuple[int, str]] | None = None,
    progress_logs: list | None = None,
) -> tuple[CheckinReminderScheduler, MagicMock, MagicMock]:
    """
    Construye un CheckinReminderScheduler con mocks.

    Retorna (scheduler, job_queue_mock, repos_mock).
    """
    job_queue = MagicMock()
    job_queue.get_jobs_by_name.return_value = jobs_by_name or []

    repos = MagicMock()
    repos.telegram_user.list_all.return_value = telegram_users or []
    repos.progress_log.list_for_user.return_value = progress_logs or []

    scheduler = CheckinReminderScheduler(job_queue=job_queue, repos=repos)
    return scheduler, job_queue, repos


def _make_progress_log(log_date: date) -> MagicMock:
    """Mock de ProgressLog con un campo .date."""
    log = MagicMock()
    log.date = log_date
    return log


# ---------------------------------------------------------------- Tests schedule_checkin_reminder


def test_schedule_checkin_reminder_llama_run_once():
    """schedule_checkin_reminder llama a job_queue.run_once con args correctos."""
    scheduler, job_queue, _ = _make_scheduler()

    checkin_date = date(2026, 6, 1)
    scheduler.schedule_checkin_reminder(
        user_id="user_abc",
        chat_id=123456,
        checkin_date=checkin_date,
    )

    job_queue.run_once.assert_called_once()
    call_kwargs = job_queue.run_once.call_args[1]

    assert call_kwargs["when"] == datetime(2026, 6, 1, 10, 0)
    assert call_kwargs["chat_id"] == 123456
    assert call_kwargs["name"] == "checkin_reminder_user_abc"
    assert call_kwargs["data"] == {"user_id": "user_abc"}


def test_schedule_checkin_reminder_cancela_previo():
    """Si ya existe un job con el mismo nombre, lo cancela antes de crear uno nuevo."""
    existing_job = MagicMock()
    scheduler, job_queue, _ = _make_scheduler(jobs_by_name=[existing_job])

    scheduler.schedule_checkin_reminder(
        user_id="user_xyz",
        chat_id=999,
        checkin_date=date(2026, 6, 1),
    )

    existing_job.schedule_removal.assert_called_once()
    job_queue.run_once.assert_called_once()


# ---------------------------------------------------------------- Tests _send_reminder


@pytest.mark.asyncio
async def test_send_reminder_envia_mensaje():
    """_send_reminder envía mensaje de recordatorio al chat_id correcto."""
    scheduler, _, _ = _make_scheduler()

    context = MagicMock()
    context.job.chat_id = 555
    context.job.data = {"user_id": "user_test"}
    context.bot.send_message = AsyncMock()

    await scheduler._send_reminder(context)

    context.bot.send_message.assert_called_once()
    call_kwargs = context.bot.send_message.call_args[1]
    assert call_kwargs["chat_id"] == 555
    assert call_kwargs["parse_mode"] == "HTML"
    assert isinstance(call_kwargs["text"], str)
    assert len(call_kwargs["text"]) > 0


# ---------------------------------------------------------------- Tests restore_scheduled_reminders


@pytest.mark.asyncio
async def test_restore_sin_usuarios():
    """restore_scheduled_reminders no falla si no hay usuarios registrados."""
    scheduler, job_queue, _ = _make_scheduler(telegram_users=[])

    await scheduler.restore_scheduled_reminders()

    job_queue.run_once.assert_not_called()


@pytest.mark.asyncio
async def test_restore_con_usuario_con_logs():
    """restore_scheduled_reminders programa recordatorio si hay logs y fecha futura."""
    # Última fecha de check-in hace 1 día → next_date = hoy + 13 días (futuro)
    log_date = date.today() - timedelta(days=1)
    log = _make_progress_log(log_date)

    scheduler, job_queue, _ = _make_scheduler(
        telegram_users=[(100, "user_1")],
        progress_logs=[log],
    )

    await scheduler.restore_scheduled_reminders()

    job_queue.run_once.assert_called_once()
    call_kwargs = job_queue.run_once.call_args[1]
    expected_next = log_date + timedelta(days=14)
    assert call_kwargs["when"] == datetime.combine(expected_next, time(10, 0))
    assert call_kwargs["chat_id"] == 100


@pytest.mark.asyncio
async def test_restore_con_usuario_sin_logs():
    """restore_scheduled_reminders no programa si no hay logs."""
    scheduler, job_queue, _ = _make_scheduler(
        telegram_users=[(200, "user_2")],
        progress_logs=[],
    )

    await scheduler.restore_scheduled_reminders()

    job_queue.run_once.assert_not_called()


@pytest.mark.asyncio
async def test_restore_no_programa_si_fecha_pasada():
    """restore_scheduled_reminders no programa si next_date ya pasó."""
    # Último check-in hace 20 días → next_date hace 6 días (pasado)
    log_date = date.today() - timedelta(days=20)
    log = _make_progress_log(log_date)

    scheduler, job_queue, _ = _make_scheduler(
        telegram_users=[(300, "user_3")],
        progress_logs=[log],
    )

    await scheduler.restore_scheduled_reminders()

    job_queue.run_once.assert_not_called()


@pytest.mark.asyncio
async def test_restore_continua_si_un_usuario_falla():
    """restore_scheduled_reminders continúa con el resto si un usuario lanza excepción."""
    # Primer usuario: lanza excepción en list_for_user
    # Segundo usuario: tiene log futuro y debe programarse
    log_date = date.today() - timedelta(days=1)
    log = _make_progress_log(log_date)

    job_queue = MagicMock()
    job_queue.get_jobs_by_name.return_value = []

    repos = MagicMock()
    repos.telegram_user.list_all.return_value = [(400, "user_bad"), (500, "user_ok")]
    repos.progress_log.list_for_user.side_effect = [Exception("fallo"), [log]]

    scheduler = CheckinReminderScheduler(job_queue=job_queue, repos=repos)

    # No debe propagar la excepción
    await scheduler.restore_scheduled_reminders()

    # El segundo usuario debe haberse procesado
    job_queue.run_once.assert_called_once()
    call_kwargs = job_queue.run_once.call_args[1]
    assert call_kwargs["chat_id"] == 500
