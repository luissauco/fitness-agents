"""Tests del flujo de check-in: checkin_command y handlers de checkin_flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.checkin_input import CheckinInput
from src.telegram_bot.handlers.checkin import _empty_checkin_data
from src.telegram_bot.handlers.checkin_flow import _build_checkin_input

# ---------------------------------------------------------------- Helpers


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


def _make_context(
    user_id: str = "tg_abc",
    allowed_ids: list[int] | None = None,
    mesocycle=None,
) -> MagicMock:
    """Context mock con bot_data y user_data mínimos."""
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.send_chat_action = AsyncMock()

    user_mapping = MagicMock()
    user_mapping.resolve_user_id = MagicMock(return_value=user_id)

    container = MagicMock()
    container.repos = MagicMock()
    container.repos.mesocycle.get_current = MagicMock(return_value=mesocycle)
    container.workflow = MagicMock()

    ctx.bot_data = {
        "settings": MagicMock(allowed_chat_ids=allowed_ids if allowed_ids is not None else [123]),
        "user_mapping": user_mapping,
        "container": container,
        "scheduler": MagicMock(),
    }
    ctx.user_data = {}
    return ctx


def _make_mesocycle(name: str = "Hipertrofia 4 semanas") -> MagicMock:
    """Mesociclo mock con nombre."""
    m = MagicMock()
    m.name = name
    return m


# ------------------------------------------------- Tests checkin_command


@pytest.mark.asyncio
async def test_checkin_command_sin_mesociclo():
    """Sin mesociclo activo → mensaje de error, user_data no modificado."""
    update = _make_update()
    context = _make_context(mesocycle=None)

    from src.telegram_bot.handlers.checkin import checkin_command

    await checkin_command(update, context)

    update.message.reply_text.assert_awaited_once()
    # user_data no debe tener checkin_in_progress
    assert context.user_data.get("checkin_in_progress") is None


@pytest.mark.asyncio
async def test_checkin_command_inicia_flujo():
    """Con mesociclo activo → checkin_in_progress=True, step='weights'."""
    update = _make_update()
    mesocycle = _make_mesocycle("Hipertrofia Upper/Lower")
    context = _make_context(mesocycle=mesocycle)

    # Patch _ask_checkin_field para no depender del mensaje real
    with patch(
        "src.telegram_bot.handlers.checkin._ask_checkin_field", new_callable=AsyncMock
    ) as mock_ask:
        from src.telegram_bot.handlers.checkin import checkin_command

        await checkin_command(update, context)

    assert context.user_data["checkin_in_progress"] is True
    assert context.user_data["checkin_step"] == "weights"
    assert isinstance(context.user_data["checkin_data"], dict)
    mock_ask.assert_awaited_once_with(update, context, "weights")


# ------------------------------------------------- Tests handle_text


@pytest.mark.asyncio
async def test_handle_text_peso_invalido():
    """Texto 'abc' en step weights → mensaje de error, step no avanza."""
    update = _make_update("abc")
    context = _make_context()
    context.user_data = {
        "checkin_in_progress": True,
        "checkin_step": "weights",
        "checkin_data": _empty_checkin_data(),
    }

    from src.telegram_bot.handlers.checkin_flow import handle_text

    await handle_text(update, context)

    update.message.reply_text.assert_awaited_once()
    # El step no debe haber avanzado
    assert context.user_data["checkin_step"] == "weights"
    # Los pesos no deben haberse guardado
    assert context.user_data["checkin_data"]["weights"] is None


@pytest.mark.asyncio
async def test_handle_text_peso_valido():
    """Texto '82.5, 83.0' → guarda weights en checkin_data, avanza step."""
    update = _make_update("82.5, 83.0")
    context = _make_context()
    context.user_data = {
        "checkin_in_progress": True,
        "checkin_step": "weights",
        "checkin_data": _empty_checkin_data(),
    }

    with patch("src.telegram_bot.handlers.checkin_flow._ask_checkin_field", new_callable=AsyncMock):
        from src.telegram_bot.handlers.checkin_flow import handle_text

        await handle_text(update, context)

    data = context.user_data["checkin_data"]
    assert data["weights"] == [82.5, 83.0]
    # El step debe haber avanzado (no seguir en "weights")
    assert context.user_data["checkin_step"] != "weights"


# ------------------------------------------------- Tests handle_callback


@pytest.mark.asyncio
async def test_handle_callback_adherencia():
    """Callback 'checkin:adherence:8' → guarda 8 en adherence, avanza step."""
    update = MagicMock()
    update.effective_chat.id = 123
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    update.callback_query = MagicMock()
    update.callback_query.data = "checkin:adherence:8"
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_reply_markup = AsyncMock()

    context = _make_context()
    context.user_data = {
        "checkin_in_progress": True,
        "checkin_step": "adherence",
        "checkin_data": _empty_checkin_data(),
    }

    with patch("src.telegram_bot.handlers.checkin_flow._ask_checkin_field", new_callable=AsyncMock):
        from src.telegram_bot.handlers.checkin_flow import handle_callback

        await handle_callback(update, context)

    data = context.user_data["checkin_data"]
    assert data["adherence"] == 8
    assert context.user_data["checkin_step"] != "adherence"


@pytest.mark.asyncio
async def test_handle_callback_skip_photos():
    """Callback 'checkin:skip_photos' → photos queda None, avanza step."""
    update = MagicMock()
    update.effective_chat.id = 123
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    update.callback_query = MagicMock()
    update.callback_query.data = "checkin:skip_photos"
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_reply_markup = AsyncMock()

    context = _make_context()
    context.user_data = {
        "checkin_in_progress": True,
        "checkin_step": "photos",
        "checkin_data": _empty_checkin_data(),
    }

    with patch("src.telegram_bot.handlers.checkin_flow._ask_checkin_field", new_callable=AsyncMock):
        from src.telegram_bot.handlers.checkin_flow import handle_callback

        await handle_callback(update, context)

    data = context.user_data["checkin_data"]
    assert data["photos"] is None
    assert context.user_data["checkin_step"] != "photos"


# ------------------------------------------------- Tests _build_checkin_input


def test_build_checkin_input_correctamente():
    """Dado un dict completo → CheckinInput construido correctamente."""
    data = _empty_checkin_data()
    data["weights"] = [82.5, 83.0, 82.8]
    data["waist_cm"] = 80.0
    data["hip_cm"] = 95.0
    data["arm_cm"] = 35.0
    data["adherence"] = 8
    data["cheat_meals"] = 2
    data["steps"] = 8500
    data["energy"] = 7
    data["sleep"] = 6
    data["hunger"] = 5
    data["motivation"] = 8
    data["stress"] = 4
    data["doms"] = 3
    data["mood"] = 7
    data["pain"] = False
    data["pain_description"] = None
    data["notes"] = "Todo bien"

    result = _build_checkin_input(data)

    assert isinstance(result, CheckinInput)
    assert result.weights == [82.5, 83.0, 82.8]
    assert result.measurements.waist_cm == 80.0
    assert result.measurements.hip_cm == 95.0
    assert result.measurements.arm_left_cm == 35.0
    # adherencia: 8/10 = 0.8
    assert result.nutrition_adherence_self_estimate == 0.8
    assert result.cheat_meals_count == 2
    assert result.daily_steps_avg == 8500
    assert result.subjective.energy_level == 7
    assert result.subjective.sleep_quality == 6
    assert result.subjective.mood == 7
    assert result.user_notes == "Todo bien"
