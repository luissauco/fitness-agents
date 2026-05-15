"""Tests del flujo de intake: handlers y _send_workflow_output."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.questionnaire import Question, QuestionType
from src.telegram_bot.keyboards.question_keyboard import keyboard_for_question
from src.telegram_bot.services.workflow_runner import WorkflowInput, WorkflowOutput

# ---------------------------------------------------------------- Helpers


def _make_output(**kwargs) -> WorkflowOutput:
    """WorkflowOutput mínimo para tests."""
    defaults = dict(
        current_phase="onboarding",
        assistant_message=None,
        current_question=None,
        needs_user_input=True,
        expecting_images=False,
        generated_files=[],
        next_checkin_date=None,
        warnings=[],
        errors=[],
        is_complete=False,
    )
    defaults.update(kwargs)
    return WorkflowOutput(**defaults)


def _make_question(qt: QuestionType, options: list[str] | None = None) -> Question:
    """Crea una pregunta de test con el tipo dado."""
    needs_opts = qt in (QuestionType.SELECT, QuestionType.MULTI_SELECT)
    return Question(
        id="q_test",
        block="test",
        text="¿Pregunta de test?",
        question_type=qt,
        options=options or (["A", "B"] if needs_opts else None),
    )


def _make_update(text: str = "hola") -> MagicMock:
    """Update mock con texto."""
    update = MagicMock()
    update.effective_chat.id = 123
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    update.message = MagicMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def _make_context(user_id: str = "tg_abc") -> MagicMock:
    """Context mock con bot_data mínimo."""
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.send_chat_action = AsyncMock()

    user_mapping = MagicMock()
    user_mapping.resolve_user_id = MagicMock(return_value=user_id)

    container = MagicMock()
    container.repos = MagicMock()
    container.workflow = MagicMock()

    ctx.bot_data = {
        "settings": MagicMock(allowed_chat_ids=[123]),
        "user_mapping": user_mapping,
        "container": container,
        "scheduler": MagicMock(),
    }
    return ctx


# ------------------------------------------------- Tests handlers


@pytest.mark.asyncio
async def test_handle_text_sends_correct_input():
    """Texto libre → WorkflowRunner.invoke recibe WorkflowInput con user_message correcto."""
    update = _make_update("mi mensaje")
    context = _make_context()

    output = _make_output(assistant_message="respuesta")
    runner_mock = MagicMock()
    runner_mock.invoke = AsyncMock(return_value=output)

    with patch("src.telegram_bot.handlers.intake_flow.WorkflowRunner", return_value=runner_mock):
        from src.telegram_bot.handlers.intake_flow import handle_text

        await handle_text(update, context)

    runner_mock.invoke.assert_awaited_once()
    wf_input: WorkflowInput = runner_mock.invoke.call_args[0][0]
    assert wf_input.user_message == "mi mensaje"
    assert wf_input.user_id == "tg_abc"


@pytest.mark.asyncio
async def test_handle_callback_extracts_value():
    """Callback «intake:M» → WorkflowInput con user_message='M'."""
    update = MagicMock()
    update.effective_chat.id = 123
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    update.callback_query = MagicMock()
    update.callback_query.data = "intake:M"
    update.callback_query.answer = AsyncMock()

    context = _make_context()

    output = _make_output(assistant_message="ok")
    runner_mock = MagicMock()
    runner_mock.invoke = AsyncMock(return_value=output)

    with patch("src.telegram_bot.handlers.intake_flow.WorkflowRunner", return_value=runner_mock):
        from src.telegram_bot.handlers.intake_flow import handle_callback

        await handle_callback(update, context)

    wf_input: WorkflowInput = runner_mock.invoke.call_args[0][0]
    assert wf_input.user_message == "M"


# ------------------------------------------ Tests _send_workflow_output


@pytest.mark.asyncio
async def test_send_workflow_output_yes_no_question():
    """Output con pregunta YES_NO → mensaje con teclado de 2 botones."""
    update = _make_update()
    context = _make_context()

    question = _make_question(QuestionType.YES_NO)
    output = _make_output(assistant_message="¿Sí o no?", current_question=question)

    from src.telegram_bot.handlers.intake_flow import _send_workflow_output

    await _send_workflow_output(update, context, output, "tg_abc")

    update.effective_message.reply_text.assert_awaited()
    call_kwargs = update.effective_message.reply_text.call_args_list[0][1]
    markup = call_kwargs.get("reply_markup")
    assert markup is not None
    # InlineKeyboardMarkup tiene inline_keyboard
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert len(buttons) == 2


@pytest.mark.asyncio
async def test_send_workflow_output_no_keyboard_for_text():
    """Output con pregunta TEXT → mensaje sin teclado (reply_markup=None)."""
    update = _make_update()
    context = _make_context()

    question = _make_question(QuestionType.TEXT)
    output = _make_output(assistant_message="Escribe algo", current_question=question)

    from src.telegram_bot.handlers.intake_flow import _send_workflow_output

    await _send_workflow_output(update, context, output, "tg_abc")

    call_kwargs = update.effective_message.reply_text.call_args_list[0][1]
    assert call_kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_send_workflow_output_scale_keyboard():
    """Output con pregunta SCALE → teclado con 10 botones en 2 filas."""
    update = _make_update()
    context = _make_context()

    question = _make_question(QuestionType.SCALE)
    output = _make_output(assistant_message="Del 1 al 10", current_question=question)

    from src.telegram_bot.handlers.intake_flow import _send_workflow_output

    await _send_workflow_output(update, context, output, "tg_abc")

    call_kwargs = update.effective_message.reply_text.call_args_list[0][1]
    markup = call_kwargs.get("reply_markup")
    assert markup is not None
    assert len(markup.inline_keyboard) == 2
    total_buttons = sum(len(row) for row in markup.inline_keyboard)
    assert total_buttons == 10


@pytest.mark.asyncio
async def test_send_workflow_output_sends_files():
    """Output con generated_files → send_document llamado por cada archivo."""
    update = _make_update()
    context = _make_context()

    files = [Path("output/Mesociclo.xlsx"), Path("output/Dieta.pdf")]
    output = _make_output(generated_files=files)

    with patch("src.telegram_bot.handlers.intake_flow.send_document") as mock_send:
        mock_send.return_value = None

        from src.telegram_bot.handlers.intake_flow import _send_workflow_output

        await _send_workflow_output(update, context, output, "tg_abc")

    assert mock_send.call_count == 2


@pytest.mark.asyncio
async def test_send_workflow_output_schedules_reminder():
    """Output con is_complete=True y next_checkin_date → schedule_checkin_reminder llamado."""
    update = _make_update()
    context = _make_context()

    checkin_date = date(2026, 5, 29)
    output = _make_output(is_complete=True, next_checkin_date=checkin_date)

    from src.telegram_bot.handlers.intake_flow import _send_workflow_output

    await _send_workflow_output(update, context, output, "tg_abc")

    scheduler = context.bot_data["scheduler"]
    scheduler.schedule_checkin_reminder.assert_called_once_with("tg_abc", 123, checkin_date)


# ------------------------------------------ Tests keyboard_for_question directo


def test_keyboard_yes_no_tiene_dos_botones():
    """keyboard_for_question para YES_NO devuelve teclado con 2 botones."""
    q = _make_question(QuestionType.YES_NO)
    markup = keyboard_for_question(q)
    assert markup is not None
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert len(buttons) == 2
    callbacks = {btn.callback_data for btn in buttons}
    assert callbacks == {"intake:yes", "intake:no"}


def test_keyboard_select_una_opcion_por_fila():
    """keyboard_for_question para SELECT devuelve una opción por fila."""
    q = _make_question(QuestionType.SELECT, options=["fat_loss", "muscle_gain", "maintenance"])
    markup = keyboard_for_question(q)
    assert markup is not None
    assert len(markup.inline_keyboard) == 3
    for row in markup.inline_keyboard:
        assert len(row) == 1


def test_keyboard_scale_dos_filas_diez_botones():
    """keyboard_for_question para SCALE devuelve 2 filas con 10 botones totales."""
    q = _make_question(QuestionType.SCALE)
    markup = keyboard_for_question(q)
    assert markup is not None
    assert len(markup.inline_keyboard) == 2
    total = sum(len(row) for row in markup.inline_keyboard)
    assert total == 10


def test_keyboard_text_devuelve_none():
    """keyboard_for_question para TEXT devuelve None."""
    q = _make_question(QuestionType.TEXT)
    assert keyboard_for_question(q) is None


def test_keyboard_multi_select_devuelve_none():
    """keyboard_for_question para MULTI_SELECT devuelve None."""
    q = _make_question(QuestionType.MULTI_SELECT, options=["A", "B"])
    assert keyboard_for_question(q) is None
