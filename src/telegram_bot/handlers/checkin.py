"""Handler del comando /checkin."""

from __future__ import annotations

import logging
from typing import Final

from telegram import Update
from telegram.ext import ContextTypes

from src.telegram_bot.handlers.auth import require_whitelist
from src.telegram_bot.messages import checkin as checkin_msgs

_logger: Final[logging.Logger] = logging.getLogger(__name__)

# Orden de los pasos del flujo de check-in
CHECKIN_STEPS: Final[list[str]] = [
    "weights",
    "waist",
    "hips",
    "arm",
    "photos",
    "adherence",
    "cheat_meals",
    "steps",
    "subjective",
    "pain",
    "training_logs",
    "notes",
]

# Sub-pasos del paso subjective
SUBJECTIVE_FIELDS: Final[list[str]] = [
    "energy",
    "sleep",
    "hunger",
    "motivation",
    "stress",
    "doms",
    "mood",
]


def _empty_checkin_data() -> dict:
    """Inicializa el dict de datos del check-in con todos los campos a None.

    Los campos corresponden a los del modelo CheckinInput y sus sub-modelos.
    """
    return {
        # CheckinInput.weights
        "weights": None,
        # CheckinInput.measurements (BodyMeasurements)
        "waist_cm": None,
        "hip_cm": None,
        "arm_cm": None,
        # CheckinInput.photos
        "photos": None,
        # CheckinInput.nutrition_adherence_self_estimate (0-1 float)
        "adherence": None,
        # CheckinInput.cheat_meals_count
        "cheat_meals": None,
        # CheckinInput.daily_steps_avg
        "steps": None,
        # CheckinInput.subjective (SubjectiveFeedback)
        "energy": None,
        "sleep": None,
        "hunger": None,
        "motivation": None,
        "stress": None,
        "doms": None,
        "mood": None,
        "subjective_step": "energy",  # sub-state de subjective
        # CheckinInput.subjective.pain_or_discomfort
        "pain": None,
        "pain_description": None,
        # CheckinInput.training_logs
        "training_logs": None,
        # CheckinInput.user_notes
        "notes": None,
    }


async def _ask_checkin_field(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step: str,
) -> None:
    """Envía el mensaje y teclado correspondiente al paso del check-in."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    message = update.effective_message

    if step == "weights":
        await message.reply_text(checkin_msgs.ask_weights(), parse_mode="HTML")

    elif step == "waist":
        skip_kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Saltar", callback_data="checkin:skip:waist")]]
        )
        await message.reply_text(
            checkin_msgs.ask_measurement("cintura"),
            parse_mode="HTML",
            reply_markup=skip_kb,
        )

    elif step == "hips":
        skip_kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Saltar", callback_data="checkin:skip:hips")]]
        )
        await message.reply_text(
            checkin_msgs.ask_measurement("cadera"),
            parse_mode="HTML",
            reply_markup=skip_kb,
        )

    elif step == "arm":
        skip_kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Saltar", callback_data="checkin:skip:arm")]]
        )
        await message.reply_text(
            checkin_msgs.ask_measurement("brazo"),
            parse_mode="HTML",
            reply_markup=skip_kb,
        )

    elif step == "photos":
        skip_kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Sin fotos", callback_data="checkin:skip_photos")]]
        )
        await message.reply_text(
            checkin_msgs.ask_photos(),
            parse_mode="HTML",
            reply_markup=skip_kb,
        )

    elif step == "adherence":
        scale_kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(str(n), callback_data=f"checkin:adherence:{n}")
                    for n in range(1, 6)
                ],
                [
                    InlineKeyboardButton(str(n), callback_data=f"checkin:adherence:{n}")
                    for n in range(6, 11)
                ],
            ]
        )
        await message.reply_text(
            checkin_msgs.ask_adherence(),
            parse_mode="HTML",
            reply_markup=scale_kb,
        )

    elif step == "cheat_meals":
        cheat_kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("0", callback_data="checkin:cheat:0"),
                    InlineKeyboardButton("1", callback_data="checkin:cheat:1"),
                    InlineKeyboardButton("2", callback_data="checkin:cheat:2"),
                    InlineKeyboardButton("3+", callback_data="checkin:cheat:3"),
                ]
            ]
        )
        await message.reply_text(
            checkin_msgs.ask_cheat_meals(),
            parse_mode="HTML",
            reply_markup=cheat_kb,
        )

    elif step == "steps":
        await message.reply_text(checkin_msgs.ask_steps(), parse_mode="HTML")

    elif step == "subjective":
        data = context.user_data.get("checkin_data") or {}
        sub_field = data.get("subjective_step", "energy")
        scale_kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        str(n), callback_data=f"checkin:subjective:{sub_field}:{n}"
                    )
                    for n in range(1, 6)
                ],
                [
                    InlineKeyboardButton(
                        str(n), callback_data=f"checkin:subjective:{sub_field}:{n}"
                    )
                    for n in range(6, 11)
                ],
            ]
        )
        await message.reply_text(
            checkin_msgs.ask_subjective(sub_field),
            parse_mode="HTML",
            reply_markup=scale_kb,
        )

    elif step == "pain":
        pain_kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Sí", callback_data="checkin:pain:yes"),
                    InlineKeyboardButton("No", callback_data="checkin:pain:no"),
                ]
            ]
        )
        await message.reply_text(
            checkin_msgs.ask_pain(),
            parse_mode="HTML",
            reply_markup=pain_kb,
        )

    elif step == "pain_description":
        await message.reply_text(checkin_msgs.ask_pain_description(), parse_mode="HTML")

    elif step == "training_logs":
        skip_kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Sin logs", callback_data="checkin:skip_logs")]]
        )
        await message.reply_text(
            checkin_msgs.ask_training_logs(),
            parse_mode="HTML",
            reply_markup=skip_kb,
        )

    elif step == "notes":
        skip_kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Sin notas", callback_data="checkin:skip_notes")]]
        )
        await message.reply_text(
            checkin_msgs.ask_notes(),
            parse_mode="HTML",
            reply_markup=skip_kb,
        )


@require_whitelist
async def checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inicia el check-in bisemanal."""
    chat_id = update.effective_chat.id
    user_mapping = context.bot_data["user_mapping"]
    container = context.bot_data["container"]

    user_id: str = user_mapping.resolve_user_id(chat_id)  # síncrono, sin await

    # Verificar mesociclo activo
    mesocycle = container.repos.mesocycle.get_current(user_id)
    if not mesocycle:
        await update.message.reply_text(checkin_msgs.no_active_mesocycle())
        return

    # Iniciar flujo
    context.user_data["checkin_in_progress"] = True
    context.user_data["checkin_data"] = _empty_checkin_data()
    context.user_data["checkin_step"] = "weights"

    await update.message.reply_text(checkin_msgs.checkin_intro(mesocycle.name), parse_mode="HTML")
    await _ask_checkin_field(update, context, "weights")
